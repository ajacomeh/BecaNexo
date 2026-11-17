"""Conectores HTML de universidades ecuatorianas; configuración cerrada e inactiva por defecto.

Los índices se revisan en cada ciclo. Ningún enlace descubierto amplía el host permitido.
La evidencia literal se conserva; las inferencias académicas quedan para revisión editorial.
"""
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, parse_qsl
from zoneinfo import ZoneInfo

from convocatorias.siau_extraccion import evidencia, fecha
from convocatorias.siau_red import AccessError
from .models import FRECUENCIA_MINIMA_MIN


@dataclass(frozen=True)
class Portal:
    clave: str
    nombre: str
    institucion: str
    host: str
    indice: str
    patron_ficha: str
    max_fichas: int = 12
    secciones_en_indice: bool = False
    generico: bool = False
    max_paginas: int = 1
    max_profundidad: int = 0
    acceso_verificado: bool = False

    @property
    def robots(self):
        return f'https://{self.host}/robots.txt'

    @property
    def politica(self):
        policy = {'host': self.host, 'indice': self.indice, 'patron_ficha': self.patron_ficha,
                'max_fichas': self.max_fichas, 'max_documentos': 2,
                'secciones_en_indice': self.secciones_en_indice,
                'bytes_html': 2097152, 'bytes_pdf': 8388608, 'reintentos': 1}
        if self.generico:
            policy.update(max_paginas=self.max_paginas, max_profundidad=self.max_profundidad,
                          acceso_verificado=self.acceso_verificado)
        return policy


PORTALES = {
    'utpl': Portal('utpl', 'Becas UTPL', 'Universidad Técnica Particular de Loja',
                   'becas.utpl.edu.ec', 'https://becas.utpl.edu.ec/tipos-de-becas',
                   r'/tipos-de-becas/[a-z0-9-]+/?'),
    'ups': Portal('ups', 'Becas UPS', 'Universidad Politécnica Salesiana',
                  'www.ups.edu.ec', 'https://www.ups.edu.ec/es/bienestar/becasups',
                  r'/es/bienestar/becasups/[a-z0-9-]+/?', secciones_en_indice=True),
}
POLITICA_VERSION = 'portal-ec/2'
GENERIC_POLICY_VERSION = 'portal-ec-generico/1'


@dataclass(frozen=True)
class Section:
    identidad: str
    titulo: str
    texto: str
    enlaces: tuple


def portal_for_source(source):
    if source.adaptador == 'portal_ec:generico':
        data = source.politica_acceso
        if not isinstance(data, dict):
            raise AccessError('Política genérica inválida.')
        try:
            portal = generic_portal(source.nombre, source.url_base, data['host'],
                data['max_paginas'], data['max_profundidad'], data['max_fichas'],
                data['acceso_verificado'])
        except (KeyError, TypeError, ValueError) as exc:
            raise AccessError('Política genérica inválida.') from exc
        if (source.politica_version != GENERIC_POLICY_VERSION or data != portal.politica
                or source.aprobada_publicacion_automatica or source.frecuencia_min < FRECUENCIA_MINIMA_MIN
                or (source.activa and not portal.acceso_verificado)):
            raise AccessError('Fuente genérica fuera del contrato auditado.')
        return portal
    portal = PORTALES.get(source.adaptador.removeprefix('portal_ec:')) if source.adaptador.startswith('portal_ec:') else None
    if (not portal or source.url_base != portal.indice or source.politica_version != POLITICA_VERSION
            or source.politica_acceso != portal.politica or source.aprobada_publicacion_automatica):
        raise AccessError('Fuente institucional fuera del contrato auditado.')
    return portal


def generic_portal(name, seed, host, max_pages=8, max_depth=2, max_cards=8, verified=False):
    if not isinstance(seed, str):
        raise ValueError('Fuente genérica o límites inválidos.')
    """Contrato cerrado: misma autoridad HTTPS, límites pequeños y verificación externa explícita."""
    parts = urlsplit(seed)
    if (not isinstance(name, str) or not 2 <= len(name.strip()) <= 120
            or not isinstance(host, str) or not re.fullmatch(r'[a-z0-9.-]{4,180}', host)
            or '..' in host or not host.endswith(('.edu.ec', '.gob.ec', '.org.ec', '.com.ec'))
            or parts.scheme != 'https' or parts.hostname != host or parts.port not in (None, 443)
            or parts.username or parts.password or parts.query or parts.fragment or not parts.path.startswith('/')
            or '%' in parts.path or any(segment in ('.', '..') for segment in parts.path.split('/'))
            or len(seed) > 500 or type(verified) is not bool
            or type(max_pages) is not int or not 1 <= max_pages <= 12
            or type(max_depth) is not int or not 0 <= max_depth <= 2
            or type(max_cards) is not int or not 1 <= max_cards <= 12):
        raise ValueError('Fuente genérica o límites inválidos.')
    return Portal('generico', name.strip(), '', host, seed, r'/[A-Za-z0-9_./%-]+',
                  max_cards, True, True, max_pages, max_depth, verified)


def admitted_url(portal, url, kind='ficha'):
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    if (parts.scheme != 'https' or parts.hostname != portal.host or port not in (None, 443)
            or parts.username or parts.password or parts.query or parts.fragment):
        return False
    if portal.generico and ('%' in parts.path or any(segment in ('.', '..') for segment in parts.path.split('/'))):
        return False
    if kind == 'ficha':
        return bool(re.fullmatch(portal.patron_ficha, parts.path))
    if kind == 'documento':
        return bool(re.fullmatch(r'/[\w./%-]+\.pdf', parts.path, re.I))
    return False


def public_document_reference(portal, base, href):
    """Conserva referencias PDF públicas; solo las URL sin consulta pueden descargarse."""
    url = urljoin(base, href)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if (parts.scheme != 'https' or parts.hostname != portal.host or port not in (None, 443)
            or parts.username or parts.password or parts.fragment or len(url) > 2048
            or not re.search(r'\.pdf(?:/[^/]+)?$', parts.path, re.I)):
        return None
    if parts.query and not (len(parse_qsl(parts.query)) == 1 and
                            parse_qsl(parts.query)[0][0] == 't' and
                            parse_qsl(parts.query)[0][1].isdigit()):
        return None
    return url


def postulation_reference(portal, base, href):
    url = urljoin(base, href)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    institutional_domain = (portal.host if portal.generico else
                            'utpl.edu.ec' if portal.clave == 'utpl' else 'ups.edu.ec')
    if (parts.scheme != 'https' or not parts.hostname or
            not (parts.hostname == institutional_domain or parts.hostname.endswith('.' + institutional_domain))
            or parts.username or parts.password or port not in (None, 443)
            or parts.query or parts.fragment or len(url) > 2048):
        return None
    return url


class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs = []
        self.anchors = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.hrefs.append(href)
                self.current_href, self.current_text = href, []

    def handle_data(self, data):
        if self.current_href:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.current_href:
            self.anchors.append((self.current_href, ' '.join(''.join(self.current_text).split())))
            self.current_href = None
            self.current_text = []


def links(content, base, portal, kind='ficha'):
    parser = Links()
    try:
        parser.feed(content.decode('utf-8-sig'))
    except (UnicodeError, ValueError) as exc:
        raise AccessError('Índice HTML no interpretable.') from exc
    found = []
    for href in parser.hrefs:
        url = urljoin(base, href)
        if admitted_url(portal, url, kind) and url not in found:
            found.append(url)
    return found


class ScholarshipSections(HTMLParser):
    """Separa becas de una página común sin convertir la portada en convocatoria."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.category = ''
        self.current = None
        self.heading = None
        self.heading_text = []
        self.heading_links = []
        self.current_level = None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'footer'):
            self.skip += 1
            return
        if self.skip:
            return
        if tag in ('h2', 'h3', 'h4', 'h5'):
            self.heading, self.heading_text, self.heading_links = tag, [], []
        elif self.heading and tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.heading_links.append(href)
        elif self.current and self.heading is None and tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.current['links'].append(href)
        elif self.current and tag in ('p', 'li', 'br'):
            self.current['text'].append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'footer') and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag == self.heading:
            title = ' '.join(''.join(self.heading_text).split())
            if self.current and self.current_level and int(tag[1]) > self.current_level:
                self.current['text'].append('\n' + title + '\n')
                self.current['links'].extend(self.heading_links)
            elif (re.match(r'^beca\b', title, re.I) or
                  (re.search(r'\bconvocatoria de becas?\b', title, re.I) and
                   (re.search(r'\b20\d{2}\b', title) or re.match(r'^\s*\d{1,3}[ªºa.]?\s+', title, re.I)))):
                self.current = {'title': title, 'category': self.category, 'text': [], 'links': self.heading_links[:],
                                'heading_tag': tag}
                self.blocks.append(self.current)
                self.current_level = int(tag[1])
            else:
                if (re.search(r'becas?\s+de\s+(grado|posgrado|tecnolog)', title, re.I)
                        or re.fullmatch(r'estudiantes (?:de nuevo ingreso|actuales)', title, re.I)):
                    self.category = title
                self.current = None
                self.current_level = None
            self.heading = None
        elif self.current and tag in ('p', 'li'):
            self.current['text'].append('\n')

    def handle_data(self, data):
        if self.skip:
            return
        if self.heading:
            self.heading_text.append(data)
        elif self.current:
            value = ' '.join(data.split())
            if value:
                self.current['text'].append(value + ' ')


def sections(content, portal, base=None):
    if not portal.secciones_en_indice:
        return []
    parser = ScholarshipSections()
    try:
        parser.feed(content.decode('utf-8-sig'))
    except (UnicodeError, ValueError) as exc:
        raise AccessError('Secciones del índice no interpretables.') from exc
    result = []
    seen = set()
    for block in parser.blocks:
        title = block['title']
        text = '\n'.join(line.strip() for line in ''.join(block['text']).splitlines() if line.strip())[:15000]
        if not text:
            continue
        key = (block['category'].casefold(), title.casefold())
        if key in seen:
            continue
        seen.add(key)
        digest = hashlib.sha256(('\n'.join(key)).encode('utf-8')).hexdigest()[:20]
        result.append(Section((base or portal.indice) + '#becanexo-' + digest, title, text, tuple(block['links'])))
    return result


def choose_candidates(candidates, last_seen, limit):
    """Nuevas primero; luego las más antiguas, sin repetir enlaces del índice."""
    unique = list(dict.fromkeys(candidates))
    unique.sort(key=lambda value: (value in last_seen, last_seen.get(value) or ''))
    return unique[:limit], len(unique) > limit


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.current = None
        self.parts = []
        self.headings = []
        self.title = ''
        self.closed = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'footer'):
            self.skip += 1
        if not self.skip and tag in ('h1', 'h2', 'h3', 'p', 'li'):
            self.current = tag
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'footer') and self.skip:
            self.skip -= 1
        if tag == 'html':
            self.closed = True
        if not self.skip and tag in ('h1', 'h2', 'h3', 'p', 'li'):
            self.parts.append('\n')
            self.current = None

    def handle_data(self, data):
        if self.skip:
            return
        value = ' '.join(data.split())
        if value:
            if self.current == 'h1' and not self.title:
                self.title = value
            if self.current in ('h1', 'h2', 'h3'):
                self.headings.append(value)
            self.parts.append(value + ' ')


def extract_portal(download, portal):
    """No deriva vigencia ni elegibilidad de etiquetas generales del portal."""
    url = download['url']
    if not admitted_url(portal, url):
        raise AccessError('Ficha fuera de la fuente cerrada.')
    raw = download['contenido']
    parser = Text()
    try:
        parser.feed(raw.decode('utf-8-sig'))
    except (UnicodeError, ValueError) as exc:
        raise AccessError('Ficha HTML no interpretable.') from exc
    text = '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())[:60000]
    if not parser.title or not re.search(r'\bbeca', (parser.title + ' ' + text).casefold()):
        raise AccessError('No hay evidencia suficiente de una beca.')
    base_links = links(raw, url, portal, 'documento')[:portal.politica['max_documentos']]
    anchors = Links()
    anchors.feed(raw.decode('utf-8-sig'))
    postulation = []
    for href, label in anchors.anchors:
        if re.search(r'\bpostular|postulaci[oó]n|renovar\b', label, re.I):
            candidate = postulation_reference(portal, url, href)
            if candidate and candidate not in postulation:
                postulation.append(candidate)
    return _item(url, download['consulta_utc'], parser.title[:250], text, base_links, parser.closed, postulation)


def extract_section(download, portal, section):
    if not portal.secciones_en_indice or not section.identidad.startswith(download['url'] + '#becanexo-'):
        raise AccessError('Sección fuera del índice institucional.')
    references = []
    for href in section.enlaces:
        url = public_document_reference(portal, download['url'], href)
        if url and url not in references:
            references.append(url)
    return _item(download['url'], download['consulta_utc'], section.titulo, section.texto,
                 references[:portal.politica['max_documentos']], True)


def _item(url, consultation, title, text, base_links, complete, postulation=()):
    lines = text.splitlines()
    def section(words):
        for pos, line in enumerate(lines):
            if any(word in line.casefold() for word in words):
                return '\n'.join(lines[pos:pos + 7])[:5000]
        return ''
    requirements = section(('requisito', 'condiciones'))
    coverage = section(('porcentaje', 'cobertura', 'financiamiento', 'monto de la beca')) or section(('beneficio',))
    modality = section(('modalidad',))
    destination = section(('país de estudio', 'destino'))
    close = ''
    for line in lines:
        if re.search(r'\b(cierre|postula hasta|fecha límite)\b', line, re.I):
            close = line[:500]
            break
        if re.search(r'\b(?:convocatoria|postulaciones?)\b.*\bhasta el\b', line, re.I):
            close = line[line.casefold().rfind('hasta el'):][:500]
            break
    date_match = re.search(r'(\d{1,2} de [a-záéíóú]+(?: de)? \d{4})', close, re.I)
    parsed_date = fecha(date_match.group(1)) if date_match else {'original': close, 'fecha': None, 'precision': None, 'hora': None, 'zona_horaria': None}
    opening = ''
    for line in lines:
        if re.search(r'\b(?:postulaciones? abiertas? desde el|(?:convocatoria|postulaciones?)\s+abierta desde el)\b', line, re.I):
            opening = line[:500]
            break
    opening_match = re.search(r'(\d{1,2} de [a-záéíóú]+(?: de)? \d{4})', opening, re.I)
    parsed_opening = fecha(opening_match.group(1)) if opening_match else None
    kind = 'convocatoria_con_cierre' if parsed_date['fecha'] else (
        'convocatoria_con_apertura' if parsed_opening and parsed_opening['fecha'] else
        'programa_permanente' if re.search(r'\b(?:programa|vigencia|postulaci[oó]n|convocatoria) permanente\b', text, re.I)
        else 'tipo_de_beca_vigencia_desconocida')
    observed_status = 'desconocida'
    consulted = datetime.fromisoformat(consultation.replace('Z', '+00:00')).astimezone(ZoneInfo('America/Guayaquil')).date()
    if parsed_date['fecha'] and date.fromisoformat(parsed_date['fecha']) < consulted:
        observed_status = 'vencida'
    elif parsed_opening and parsed_opening['fecha'] and date.fromisoformat(parsed_opening['fecha']) > consulted:
        observed_status = 'proxima'
    elif parsed_date['fecha']:
        observed_status = 'abierta'
    instructions = section(('cómo postular', 'proceso de postulación', 'postular/renovar'))
    return {'url': url, 'consulta_utc': consultation, 'version_extractor': POLITICA_VERSION,
            'titulo': evidencia(title, url), 'descripcion': evidencia(text[:15000], url),
            'tipo_oportunidad': kind, 'vigencia_al_consultar': observed_status,
            'entidad_html': evidencia('', url),
            'beneficio': {**evidencia(coverage, url), 'conceptos': [], 'cantidades': [], 'porcentajes': [], 'ambito': 'sin_asignar_a_opciones'},
            'estudios': {'niveles_mencionados': [], 'menciones_academicas': [], 'evidencia_niveles': evidencia('', url),
                         'modalidad': evidencia(modality, url), 'destino': evidencia(destination, url)},
            'opciones': [], 'requisitos': {**evidencia(requirements, url), 'estado': 'pendientes_de_estructuracion'},
            'postulacion_y_documentos': evidencia(instructions, url), 'cierre': {**parsed_date, 'url': url},
            'apertura': {**parsed_opening, 'url': url} if parsed_opening else None,
            'fecha_publicacion': None,
            'enlaces_bases': [{'url': link, 'url_original': link, 'texto': 'Documento público'} for link in base_links],
            'enlaces_postulacion': [{'url': link, 'url_original': link, 'texto': 'Postulación institucional'} for link in postulation],
            'texto_ficha': text, 'seccion_completa': complete}
