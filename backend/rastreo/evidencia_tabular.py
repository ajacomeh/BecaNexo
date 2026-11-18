"""Vista editorial de tablas HTML ya archivadas; no valida ni modifica convocatorias."""
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


def _texto(parts, limit=300):
    return ' '.join(''.join(parts).split())[:limit]


def _fecha_literal(value):
    match = re.search(r'\b(\d{1,2}/\d{1,2}/20\d{2})\b|\b(\d{1,2}\s+de\s+[a-záéíóú]+\s+(?:de\s+)?20\d{2})\b', value, re.I)
    if not match:
        return None, None
    literal = match[0]
    if match[1]:
        try:
            parsed = datetime.strptime(literal, '%d/%m/%Y').date().isoformat()
        except ValueError:
            parsed = None
    else:
        from convocatorias.siau_extraccion import fecha
        parsed = fecha(literal)['fecha']
    return literal, parsed


def _enlace(base, href):
    if not href or len(href) > 2048:
        return None
    try:
        url = urljoin(base, href)
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != 'https' or not parts.netloc or parts.username or parts.password:
        return None
    return url


class TablasHTML(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.heading = ''
        self.heading_parts = None
        self.table = None
        self.cell = None
        self.caption = None
        self.row = None
        self.skip = 0
        self.anchor = None
        self.tables = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
        if self.skip:
            return
        if tag in ('h1', 'h2', 'h3', 'h4') and self.table is None:
            self.heading_parts = []
        elif tag == 'table' and len(self.tables) < 6:
            self.table = {'encabezado': self.heading, 'titulo': '', 'filas': []}
        elif self.table is not None:
            if tag == 'caption':
                self.caption = []
            elif tag == 'tr':
                self.row = []
            elif tag in ('th', 'td') and self.row is not None:
                self.cell = []
        if tag == 'a':
            self.anchor = {'href': attrs.get('href', ''), 'texto': []}

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript') and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag in ('h1', 'h2', 'h3', 'h4') and self.heading_parts is not None:
            self.heading = _texto(self.heading_parts, 180)
            self.heading_parts = None
        elif tag == 'caption' and self.table is not None and self.caption is not None:
            self.table['titulo'] = _texto(self.caption, 180)
            self.caption = None
        elif tag in ('th', 'td') and self.cell is not None:
            value = _texto(self.cell)
            if value and self.row is not None and len(self.row) < 8:
                self.row.append(value)
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if self.table is not None and self.row and len(self.table['filas']) < 15:
                self.table['filas'].append(self.row)
            self.row = None
        elif tag == 'table' and self.table is not None:
            if self.table['filas']:
                self.tables.append(self.table)
            self.table = None
        elif tag == 'a' and self.anchor is not None:
            label = _texto(self.anchor['texto'], 180)
            url = _enlace(self.url, self.anchor['href'])
            if url and re.search(r'\b(?:bases?|anexos?|reglamento|formulario|postulaci[oó]n|solicitud)\b', label, re.I):
                entry = {'texto': label, 'url': url, 'estado': 'por_revisar'}
                if entry not in self.documents and len(self.documents) < 30:
                    self.documents.append(entry)
            self.anchor = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.heading_parts is not None:
            self.heading_parts.append(data)
        if self.caption is not None:
            self.caption.append(data)
        if self.cell is not None:
            self.cell.append(data)
        if self.anchor is not None:
            self.anchor['texto'].append(data)


def extraer_tablas(raw, url, *, version_id, documento_id):
    """Conserva filas y contextos; ningún valor se considera requisito aprobado."""
    parser = TablasHTML(url)
    parser.feed(raw.decode('utf-8-sig', errors='strict'))
    tables = []
    for table in parser.tables:
        context = ' '.join(filter(None, (table['encabezado'], table['titulo'])))
        rows = []
        for cells in table['filas']:
            text = ' · '.join(cells)
            local = context + ' ' + text
            if re.search(r'\b(?:renovaci[oó]n|conservaci[oó]n|mantener la beca)\b', local, re.I):
                purpose = 'renovacion'
            elif re.search(r'\b(?:una de las siguientes|cualquiera de|alternativas?|o bien)\b', local, re.I):
                purpose = 'alternativa_por_revisar'
            else:
                purpose = 'inicial_por_revisar'
            if re.search(r'\b(?:cronograma|calendario|fechas?)\b', context, re.I):
                kind = 'cronograma'
            elif re.search(r'\b(?:requisitos?|documentos?|anexos?)\b', context, re.I):
                kind = 'requisito_o_documento'
            elif re.search(r'\b(?:beneficios?|cobertura|financiamiento)\b', context, re.I):
                kind = 'beneficio'
            elif re.search(r'\b(?:programas?|carreras?|oferta acad[eé]mica)\b', context, re.I):
                kind = 'programa'
            else:
                kind = 'sin_clasificar'
            date_literal, date_iso = _fecha_literal(text) if kind == 'cronograma' else (None, None)
            percentages = re.findall(r'(?<!\d)\d{1,3}(?:[.,]\d{1,2})?\s*%', text) if kind == 'beneficio' else []
            rows.append({'celdas': cells, 'tipo': kind, 'condicion': purpose,
                         'fecha_literal': date_literal, 'fecha_sugerida': date_iso,
                         'porcentajes_literales': percentages, 'porcentaje_fijo': None,
                         'estado': 'pendiente_revision'})
        tables.append({'encabezado': table['encabezado'], 'titulo': table['titulo'], 'filas': rows,
                       'procedencia': {'version_id': version_id, 'documento_id': documento_id, 'url': url}})
    return {'tablas': tables, 'enlaces_documentales': [{**entry, 'procedencia': {
        'version_id': version_id, 'documento_id': documento_id, 'url': url}} for entry in parser.documents]}
