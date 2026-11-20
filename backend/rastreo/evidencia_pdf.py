"""Evidencia PDF local y revisable; no crea requisitos ni modifica versiones."""
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from django.conf import settings

from .evidencia_tabular import _fecha_literal
from .storage import StorageError, key_for, root_path, verify_file

MAX_DOCUMENTOS = 3
MAX_FRAGMENTOS = 120
TIMEOUT_SEGUNDOS = 5


def _normal(text):
    return ''.join(ch for ch in unicodedata.normalize('NFD', text.casefold())
                   if unicodedata.category(ch) != 'Mn')


def _tipo(line):
    text = _normal(line)
    if re.search(r'\b(?:fecha|cronograma|apertura|cierre|plazo|hasta el|notificacion|adjudicacion)\b', text):
        return 'cronograma'
    if re.search(r'\b(?:requisito|debera|deberan|presentar|acreditar|ser estudiante|ser ciudadano|no tener|promedio|experiencia)\b', text):
        return 'requisito'
    if re.search(r'\b(?:cedula|curriculum|certificado|solicitud|formulario|carta de|anexo)\b', text):
        return 'documento_exigido'
    if re.search(r'\b(?:beneficio|cobertura|financiamiento|arancel|matricula|becas? completas?|becas? parciales?)\b', text):
        return 'beneficio'
    if re.search(r'\b(?:modalidad|presencial|virtual|en linea|hibrid)\b', text):
        return 'modalidad'
    if re.search(r'\b(?:carrera|programa|curso|maestria|grado|educacion continua|area academica)\b', text):
        return 'programa_o_nivel'
    if re.search(r'\b(?:postulacion|postular|enviar.*correo|inscripcion)\b', text):
        return 'postulacion'
    if re.search(r'\b(?:ofrecida|otorgada|financiada|coofrecida)\s+por\b', text):
        return 'oferente_mencionado'
    return 'contexto'


MAX_CARACTERES_PARRAFO = 1500
# Palabras que, al final de una línea, indican que la frase continúa en la siguiente aunque empiece en mayúscula.
_CONECTORES = {'de', 'del', 'el', 'la', 'los', 'las', 'y', 'e', 'o', 'u', 'en', 'por', 'para', 'con', 'a', 'al', 'que',
               'su', 'sus', 'un', 'una', 'esta', 'este', 'estas', 'estos', 'dicha', 'dicho', 'segun', 'como', 'entre', 'sin', 'sobre'}
_ELEMENTO = re.compile(r'^(?:\d{1,2}[.)]|[a-z][.)]|[•·●▪\-–])\s+')
_ENCABEZADO_MAYOR = re.compile(r'^[A-Z]\.\s+[A-ZÁÉÍÓÚÑ]')
# Encabezado mayor de las bases («E. REQUISITOS PARA LA POSTULACIÓN») → sección reconocida.
_SECCIONES = (('obligaciones', r'^obligaciones\b'), ('seguimiento', r'^seguimiento\b'),
              ('sanciones', r'^(?:suspension|sanciones)\b'), ('informacion', r'^(?:informacion adicional|base legal|disposicion)'),
              ('requisitos', r'^requisitos?\b'),
              # Adjudicación y contrato van antes que «financiamiento»: «Elaboración del contrato de financiamiento».
              ('adjudicacion', r'\b(?:proceso de otorgamiento|adjudicacion)\b'), ('contrato', r'^(?:elaboracion|suscripcion)\b'),
              ('financiamiento', r'\b(?:financiamiento|cobertura|rubros?|beneficios?)\b'),
              ('cronograma', r'\b(?:cronograma|calendario|convocatoria)\b'), ('documentos', r'^document'),
              ('objeto', r'^(?:objetivo|objeto)\b'))


def _mayusculas(line):
    letters = [ch for ch in line if ch.isalpha()]
    return len(letters) >= 4 and sum(ch.isupper() for ch in letters) / len(letters) >= 0.8 and len(line) <= 120


def _seccion_de_encabezado(line):
    titulo = _normal(re.sub(r'^[A-Z]\.\s+', '', line)).strip(' :.')
    for key, pattern in _SECCIONES:
        if re.search(pattern, titulo):
            return key
    return 'otra'


def _parrafos(pages):
    """Reconstruye párrafos y elementos numerados o con viñeta, y la sección de las bases de cada uno.

    Une las líneas que el maquetado del PDF cortó dentro de una frase y las palabras partidas por guion.
    Un encabezado mayor («A. OBJETIVO») cambia la sección; los encabezados en mayúsculas dentro de una
    sección (por ejemplo «REQUISITOS ESPECÍFICOS POR COMPONENTE») delimitan subsecciones.
    """
    paragraphs = []
    section = None
    section_title = ''
    subsection = ''
    for page in pages:
        if page['estado'] != 'texto':
            continue
        current = None

        def close():
            nonlocal current
            if current and current['texto'].strip():
                current['texto'] = ' '.join(current['texto'].split())[:MAX_CARACTERES_PARRAFO]
                paragraphs.append(current)
            current = None
        for raw in page['texto'].splitlines():
            line = ' '.join(raw.split())
            if not line:
                close()
                continue
            heading = bool(_ENCABEZADO_MAYOR.match(line)) or _mayusculas(line)
            if heading:
                if current and current.get('encabezado') and not _ENCABEZADO_MAYOR.match(line):
                    current['texto'] += ' ' + line   # Encabezado partido en dos líneas.
                    continue
                close()
                if _ENCABEZADO_MAYOR.match(line):
                    section, subsection = _seccion_de_encabezado(line), ''
                    section_title = re.sub(r'^[A-Z]\.\s+', '', line).strip(' :.')
                    section_title = re.sub(r'(?<=[A-ZÁÉÍÓÚÑ])\s*\d{1,2}$', '', section_title).strip(' :.')
                else:
                    subsection = line
                current = {'texto': line, 'pagina': page['pagina'], 'seccion_bases': section, 'subseccion': subsection,
                           'titulo_seccion': section_title, 'elemento': False, 'encabezado': True}
                continue
            if current and not current['encabezado'] and not _ELEMENTO.match(line):
                previous = current['texto'].rstrip()
                last = _normal(previous.split()[-1]) if previous.split() else ''
                if re.search(r'[A-Za-zÁÉÍÓÚÑáéíóúñ]-$', previous) and line[:1].islower():
                    current['texto'] = previous[:-1] + line   # Palabra partida por guion.
                    continue
                if line[:1].islower() or previous.endswith(',') or last in _CONECTORES or not re.search(r'[.:;?!)]$', previous) and line[:1] in '(«"“':
                    current['texto'] = previous + ' ' + line
                    continue
            close()
            current = {'texto': line, 'pagina': page['pagina'], 'seccion_bases': section, 'subseccion': subsection,
                       'titulo_seccion': section_title, 'elemento': bool(_ELEMENTO.match(line)), 'encabezado': False}
        close()
    return paragraphs


def _fragmentos(pages, version_id, relation):
    rows = []
    truncated = False
    by_page = {}
    for paragraph in _parrafos(pages):
        by_page.setdefault(paragraph['pagina'], []).append(paragraph)
    for page in pages:
        if page['estado'] != 'texto':
            continue
        # No extender una categoría a otra página sin un nuevo encabezado explícito.
        category = ''
        section = ''
        alternatives = False
        # El límite cuenta párrafos reconstruidos, no líneas del maquetado.
        for paragraph in by_page.get(page['pagina'], []):
            line = paragraph['texto']
            if not line:
                continue
            if len(rows) >= MAX_FRAGMENTOS:
                truncated = True
                continue
            normalized = _normal(line)
            if re.match(r'^(?:categoria|beca (?:por|de|socioeconomica|deportiva|artistica))\b', normalized):
                category = line
                section = ''
                alternatives = False
            if re.match(r'^(?:requisitos?|beneficios?|cronograma|documentos?|renovacion|proceso de postulacion)\b', normalized):
                section = line
                alternatives = False
            if re.search(r'\b(?:una de las siguientes|cualquiera de|alternativas?|o bien)\b', normalized):
                alternatives = True
            if re.search(r'\b(?:renovacion|conservacion|mantener la beca)\b', _normal(section + ' ' + line)):
                condition = 'renovacion'
            elif alternatives:
                condition = 'alternativa_por_revisar'
            elif re.search(r'\s+o\s+', normalized) and _tipo(line) == 'requisito':
                condition = 'alternativa_por_revisar'
            else:
                condition = 'inicial_por_revisar'
            kind = _tipo(line)
            if kind == 'contexto':
                continue
            percentages = re.findall(r'(?<!\d)\d{1,3}(?:[.,]\d{1,2})?\s*%', line) if kind == 'beneficio' else []
            date_literal, date_iso = _fecha_literal(line) if kind == 'cronograma' else (None, None)
            links = [url.rstrip('.,;)') for url in re.findall(r'https?://[^\s<>]+', line)][:3]
            rows.append({'texto_original': line, 'tipo': kind, 'categoria': category or None,
                         'seccion': section or None, 'seccion_bases': paragraph['seccion_bases'], 'condicion': condition,
                         'fecha_literal': date_literal, 'fecha_sugerida': date_iso,
                         'porcentajes_literales': percentages, 'porcentaje_fijo': None,
                         'enlaces_literales': links, 'estado': 'pendiente_revision',
                         'procedencia': {'version_id': version_id, 'documento_id': relation.documento_id,
                                         'pagina': page['pagina'], 'url': relation.url_normalizada}})
    return rows, truncated


def leer_evidencia_pdf(relation, version_id, *, root=None):
    """Verifica SHA-256 y aísla el parser en un proceso con tiempo acotado."""
    document = relation.documento
    result = {'documento_id': document.pk, 'version_id': version_id, 'url': relation.url_normalizada,
              'urls': [relation.url_normalizada],
              'estado': 'no_disponible', 'total_paginas': None, 'paginas': [], 'fragmentos': [],
              'fragmentos_truncados': False}
    if (document.mime != 'application/pdf' or document.tamano_bytes > 2_097_152
            or document.clave_almacenamiento != key_for(document.sha256)):
        result['estado'] = 'fuera_de_limite'
        return result
    try:
        base = Path(root) if root is not None else root_path()
        path = base / document.clave_almacenamiento
        if path.parent.is_symlink() or path.parent.resolve().parent != base.resolve():
            raise StorageError('Ruta documental insegura.')
        verify_file(path, document.sha256, document.tamano_bytes)
        run = subprocess.run([sys.executable, '-m', 'rastreo._pdf_reader_child', str(path)],
                             cwd=settings.BASE_DIR, capture_output=True, timeout=TIMEOUT_SEGUNDOS, check=False)
        if run.returncode != 0 or len(run.stdout) > 500_000:
            result['estado'] = 'no_interpretable'
            return result
        extracted = json.loads(run.stdout.decode('utf-8'))
    except subprocess.TimeoutExpired:
        result['estado'] = 'tiempo_agotado'
        return result
    except (StorageError, OSError, ValueError, UnicodeError):
        return result
    result['estado'] = extracted.get('estado', 'no_interpretable')
    result['total_paginas'] = extracted.get('total_paginas')
    result['paginas'] = [{'pagina': page['pagina'], 'estado': page['estado'],
                          'texto_recortado': page.get('texto_recortado', False)}
                         for page in extracted.get('paginas', [])]
    result['fragmentos'], result['fragmentos_truncados'] = _fragmentos(extracted.get('paginas', []), version_id, relation)
    # Párrafos reconstruidos con su sección de las bases: los usa el llenado automático (rastreo.bases_pdf).
    result['parrafos'] = _parrafos(extracted.get('paginas', []))
    return result
