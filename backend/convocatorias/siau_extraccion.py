"""Contrato de observación, no serializer de negocio ni intérprete de requisitos."""
import hashlib
import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin

EXTRACTOR_VERSION = 'siau-html/2'


class FichaHTML(HTMLParser):
    """Lee solo la sección que contiene entry-title; no ejecuta HTML/JS."""
    blocks = {'p', 'li', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'td', 'tr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.links, self.buffer = [], [], []
        self.section_depth = 0
        self.active = False
        self.finished = False
        self.skip = 0
        self.anchor = None
        self.requirements_seen = False

    def flush(self):
        text = ' '.join(''.join(self.buffer).split())
        if text:
            self.lines.append(text)
            if 'Requisitos generales para aplicar' in text or 'REQUISITOS GENERALES' in text:
                self.requirements_seen = True
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {'script', 'style', 'noscript'}:
            self.skip += 1
        if self.skip:
            return
        if tag == 'section':
            self.section_depth += 1
        if 'entry-title' in attrs.get('class', '').split() and not self.finished:
            self.active = True
        if not self.active:
            return
        if tag in self.blocks:
            self.flush()
        if tag == 'a':
            self.anchor = {'url_original': attrs.get('href', ''), 'text': []}

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'noscript'}:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if self.active and tag in self.blocks:
            self.flush()
        if tag == 'a' and self.anchor:
            self.anchor['texto'] = ' '.join(''.join(self.anchor.pop('text')).split())
            self.links.append(self.anchor)
            self.anchor = None
        if tag == 'section':
            self.section_depth -= 1
            if self.active and self.section_depth == 0 and self.requirements_seen:
                self.flush()
                self.active, self.finished = False, True

    def handle_data(self, data):
        if self.active and not self.skip:
            self.buffer.append(data)
            if self.anchor:
                self.anchor['text'].append(data)


MONTHS = dict(zip(('enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre').split(), range(1, 13)))


def fecha(original):
    match = re.fullmatch(r'\s*(\d{1,2}) de (\w+)(?:,?\s+(?:de\s+)?)(\d{4})\s*', original, re.I)
    normalized = None
    if match and match[2].lower() in MONTHS:
        try:
            normalized = date(int(match[3]), MONTHS[match[2].lower()], int(match[1])).isoformat()
        except ValueError:
            pass
    return {'original': original, 'fecha': normalized, 'precision': 'dia' if normalized else None,
            'hora': None, 'zona_horaria': None}


def evidencia(texto, url):
    return {'texto_original': texto, 'url': url}


def menciones_academicas(description, requirements, url):
    """Menciones léxicas contextualizadas, no homologación de niveles ni reglas."""
    pattern = re.compile(r'\b(?:maestrías?(?:\s+(?:tecnológicas?|académicas?))?|especializaciones|especialización|tercer nivel técnico tecnológico universitario|tecnológicos?(?:\s+superior(?:es)?(?:\s+universitarios?)?)?|técnicos?|posgrado|grado)\b', re.I)
    result = []
    for section, text in (('objetivo', description), ('requisitos', requirements)):
        for sentence in re.split(r'[\n.!?]+', text):
            for match in pattern.finditer(sentence):
                before = sentence[:match.start()].casefold()
                # El contexto local evita que el inicio de la oración gobierne
                # una institución o una titulación previa citada después.
                local = before[-100:]
                if match[0].casefold() == 'posgrado':
                    role = 'contexto_por_revisar'
                elif match[0].casefold() == 'grado' and re.match(r'\s+académico', sentence[match.end():], re.I):
                    role = 'incidental'
                elif re.search(r'(?:institutos?|instituciones)\s+(?:superiores?\s+)?$', before):
                    role = 'incidental'
                elif section == 'requisitos' and 'para cursar' in local:
                    role = 'contexto_por_revisar'
                elif re.search(r'(?:contar con|título.{0,35}previo|haber obtenido|ya registrado)', local):
                    role = 'formacion_previa'
                elif re.search(r'(?:programas? de|estudios de|cursando estudios|en los niveles)', before) and section == 'objetivo':
                    role = 'oferta_mencionada'
                else:
                    role = 'contexto_por_revisar'
                result.append({'expresion_original': match[0], 'contexto_original': sentence.strip(),
                               'seccion': section, 'funcion': role, 'nivel_normalizado': None, 'url': url})
    return result


def extract_html(download):
    raw, url = download['contenido'], download['url']
    parser = FichaHTML()
    # Las dos fichas declaran UTF-8; un cambio de codificación no se disimula.
    parser.feed(raw.decode('utf-8', errors='strict'))
    parser.flush()
    lines = parser.lines
    def section(start, end=None):
        begin = next((i for i, line in enumerate(lines) if start.casefold() in line.casefold()), None)
        if begin is None:
            return ''
        stop = next((i for i in range(begin + 1, len(lines)) if end and end.casefold() in lines[i].casefold()), len(lines))
        return '\n'.join(lines[begin + 1:stop])
    def after(label):
        inline = next((line.split(':', 1)[1].strip() for line in lines if line.casefold().startswith(label.casefold() + ':') and line.split(':', 1)[1].strip()), '')
        if inline:
            return inline
        index = next((i for i, line in enumerate(lines) if line.casefold().rstrip(':') == label.casefold()), None)
        return lines[index + 1] if index is not None and index + 1 < len(lines) else ''
    deadline_index = next((i for i, line in enumerate(lines) if line.casefold().rstrip(':') == 'postula hasta'), None)
    deadlines_by_modality = []
    if deadline_index is not None:
        for line in lines[deadline_index + 1:deadline_index + 5]:
            if line.casefold().startswith(('país:', 'pais:', 'idioma:', 'modalidad:', 'aplicar ahora')):
                break
            if ':' in line:
                label, literal = line.split(':', 1)
                parsed = fecha(literal.strip())
                if parsed['fecha'] and re.search(r'presencial|h[ií]brid[ao]|en l[ií]nea|virtual', label, re.I):
                    deadlines_by_modality.append({'modalidad_original': label.strip(), **parsed, 'url': url})
    description = (section('¿Quiénes pueden aplicar?', '¿Cuál es la cobertura')
                   or section('dirigida esta convocatoria', 'Requisitos para aplicar'))
    coverage = section('¿Cuál es la cobertura', '¿Cómo postular')
    requirements = (section('Requisitos generales para aplicar')
                    or section('REQUISITOS GENERALES', 'Preguntas frecuentes'))
    instructions = (section('¿Cómo postular?', 'Requisitos generales para aplicar')
                    or section('Lugar de presentación de postulaciones'))
    # No confundir un nombre de portal ni una mención de pie de página con oferente.
    entity = re.search(r'Ministerio de Educación, Deporte y Cultura\s*[–-]\s*MINEDEC', description)
    amounts = []
    for match in re.finditer(r'(USD\s*|\$\s*)(\d+(?:[.,]\d+)*)', coverage):
        before = coverage[max(0, match.start() - 35):match.start()].casefold()
        amounts.append({'original': match[0], 'valor_literal': match[2],
                        'moneda': 'USD' if 'USD' in match[1] else None,
                        'tipo': 'tope' if 'hasta' in before else 'monto_mencionado'})
    percentages = [m[0] for m in re.finditer(r'\d+(?:[.,]\d+)?\s*%', coverage)]
    concepts = [concept for concept in ('manutención', 'matrícula', 'aranceles') if concept in coverage.casefold()]
    mentions = menciones_academicas(description, requirements, url)
    levels = list(dict.fromkeys(m['expresion_original'] for m in mentions if m['funcion'] == 'oferta_mencionada'))
    links = [{**item, 'url': urljoin(url, item['url_original'])} for item in parser.links]
    return {'url': url, 'consulta_utc': download['consulta_utc'], 'sha256': hashlib.sha256(raw).hexdigest(),
            'version_extractor': EXTRACTOR_VERSION,
            'titulo': evidencia(lines[0] if lines else '', url), 'descripcion': evidencia(description, url),
            'entidad_html': evidencia(entity[0] if entity else '', url),
            'beneficio': {**evidencia(coverage, url), 'conceptos': concepts, 'cantidades': amounts,
                          'porcentajes': percentages, 'ambito': 'sin_asignar_a_opciones'},
            'estudios': {'niveles_mencionados': levels, 'menciones_academicas': mentions, 'evidencia_niveles': evidencia(description, url),
                         'modalidad': evidencia(after('Modalidad'), url), 'destino': evidencia(after('País'), url)},
            'opciones': [], 'requisitos': {**evidencia(requirements, url), 'estado': 'pendientes_de_estructuracion'},
            'postulacion_y_documentos': evidencia(instructions, url),
            'cierre': {**fecha(after('POSTULA HASTA')), 'url': url},
            'cierres_por_modalidad': deadlines_by_modality, 'fecha_publicacion': None,
            'enlaces_bases': [link for link in links if link['texto'].upper() == 'BASES'],
            'enlaces_postulacion': [link for link in links if link['texto'].upper() == 'POSTULA'],
            'texto_ficha': '\n'.join(lines), 'seccion_completa': parser.finished}


def validate_observation(item, reference_date):
    """Anota ausencias; nunca valida publicación ni escribe en el modelo."""
    warnings = ['Vista previa: no aprobada para publicar.',
                'Requisitos sin estructurar; documentos y certificados requieren verificación externa.',
                'Niveles/modalidades/destinos no forman opciones cartesianas. Revisar agrupación y catálogos.',
                'Fecha de publicación desconocida; consulta y ruta del PDF no la sustituyen.']
    for field in ('titulo', 'descripcion', 'requisitos'):
        if not item[field]['texto_original']:
            warnings.append('Estructura inesperada o campo ausente: ' + field)
    if not item['seccion_completa']:
        warnings.append('No se confirmó el final de la sección HTML; revisión manual obligatoria.')
    if not item['entidad_html']['texto_original']:
        warnings.append('Entidad no identificada explícitamente en la descripción HTML; no inferir del portal.')
    for field in ('modalidad', 'destino'):
        if not item['estudios'][field]['texto_original']:
            warnings.append('Dato de estudios ausente: ' + field)
    closure = item['cierre']['fecha']
    item['vigencia_observada'] = ('vencida' if date.fromisoformat(closure) < reference_date else 'cierre_no_anterior_al_dia_de_consulta') if closure else 'desconocida'
    if not closure:
        warnings.append('Fecha de cierre ausente o ambigua; no inferir permanencia.')
    if len({row['fecha'] for row in item.get('cierres_por_modalidad', [])}) > 1:
        warnings.append('Cierres diferentes por modalidad; verificar cada opción antes de considerarla abierta.')
    if item['vigencia_observada'] == 'vencida':
        warnings.append('Cierre vencido según la fecha publicada; no es una oferta abierta.')
    for amount in item['beneficio']['cantidades']:
        if amount['moneda'] is None:
            warnings.append('Símbolo $ sin código monetario explícito: moneda pendiente.')
        if amount['tipo'] == 'tope':
            warnings.append('Conservar tope junto al porcentaje: no equivale a monto concedido ni a cobertura de todos los gastos.')
    if not item['enlaces_bases']:
        warnings.append('No se encontró enlace BASES con el contrato esperado.')
    for link in item['enlaces_postulacion']:
        if link['url'].endswith('.'):
            warnings.append('Enlace POSTULA termina en punto: conservado sin corregir ni visitar; requiere revisión.')
    item['advertencias'] = warnings
    return item
