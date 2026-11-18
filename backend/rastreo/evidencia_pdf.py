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


def _fragmentos(pages, version_id, relation):
    rows = []
    truncated = False
    for page in pages:
        if page['estado'] != 'texto':
            continue
        # No extender una categoría a otra página sin un nuevo encabezado explícito.
        category = ''
        section = ''
        alternatives = False
        for raw in page['texto'].splitlines():
            line = ' '.join(raw.split())[:350]
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
                         'seccion': section or None, 'condicion': condition,
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
    return result
