"""Candidatos del llenado automático a partir de las bases en PDF de la misma versión (funciones puras).

Recibe los documentos ya leídos por `evidencia_pdf.leer_evidencia_pdf` (con sus párrafos reconstruidos y la
sección de las bases de cada uno) y aplica a cada sección el extractor que ya se usa con la ficha:
- requisitos: elementos numerados de la sección de requisitos (sin documentación opcional ni requisitos
  específicos por componente), solo la condición (primera frase), interpretados con `interpretar_requisitos`;
- beneficios: párrafos de financiamiento y cobertura con importe o porcentaje, con `candidatos_adicionales`;
- obligaciones de la persona becaria: elementos de su sección, para el campo de obligaciones del beneficiario;
- cronograma: se conserva como evidencia; no se escribe en el borrador.
Cada candidato conserva documento, página y sección como procedencia. Lo ambiguo lo descarta el extractor.
"""
import re
import unicodedata

from .estructura_semantica import candidatos_adicionales, interpretar_requisitos

MAX_OBLIGACIONES = 4000
_SUBSECCION_EXCLUIDA = re.compile(r'(?:opcional|especific|componente|baremo|prioriz)')
_NUMERADO = re.compile(r'^\d{1,2}[.)]\s+')
_LITERAL = re.compile(r'^[a-z][.)]\s+')


def _normal(text):
    text = unicodedata.normalize('NFD', str(text or '').casefold())
    return ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')


def clave(text):
    """Comparación robusta a espacios y signos que el PDF parte o añade («req uisitos», punto final)."""
    return re.sub(r'\W+', '', _normal(text))


_VACIAS = {'para', 'como', 'sobre', 'entre', 'desde', 'hasta', 'segun', 'este', 'esta', 'estos', 'estas', 'dicha', 'dicho',
           'tener', 'contar', 'estar', 'haber', 'sido', 'persona', 'personas'}


def _palabras(text):
    return {w for w in re.findall(r'[a-z0-9]+', _normal(text)) if len(w) > 3 and w not in _VACIAS}


def misma_condicion(a, b):
    """La misma condición redactada distinto en la ficha y en las bases: mismo texto o casi las mismas palabras."""
    ka, kb = clave(a), clave(b)
    if not ka or not kb:
        return False
    if ka in kb or kb in ka:
        return True
    pa, pb = _palabras(a), _palabras(b)
    return bool(pa and pb) and len(pa & pb) / min(len(pa), len(pb)) >= 0.7


def _documentos_con_parrafos(documentos):
    return [d for d in documentos or [] if d.get('estado') in ('extraido', 'limite_paginas') and d.get('parrafos')]


def _primera_frase(text):
    """La condición termina en su primer punto final; lo que sigue en la celda es la documentación de respaldo."""
    match = re.search(r'(?<=[a-záéíóúñ)\d])\.(?=\s+[A-ZÁÉÍÓÚÑ]|\s*$)', text)
    return text[:match.end()] if match else text


def requisitos_de_bases(documentos, version_id):
    """Candidatos de requisito con procedencia de documento y página."""
    out = []
    for documento in _documentos_con_parrafos(documentos):
        for parrafo in documento['parrafos']:
            if parrafo['seccion_bases'] != 'requisitos' or parrafo['encabezado'] or not _NUMERADO.match(parrafo['texto']):
                continue
            if _SUBSECCION_EXCLUIDA.search(_normal(parrafo.get('subseccion'))):
                continue
            condicion = _primera_frase(_NUMERADO.sub('', parrafo['texto'])).strip()
            if not 15 <= len(condicion) <= 600:
                continue
            for candidato in interpretar_requisitos(condicion, version_id=version_id, url=documento.get('url'),
                                                    documento_id=documento['documento_id']):
                candidato['procedencia'] = {**candidato['procedencia'], 'pagina': parrafo['pagina'],
                                            'seccion': 'Bases en PDF · Requisitos', 'documento_id': documento['documento_id']}
                out.append(candidato)
    return out


def beneficios_de_bases(documentos, version_id):
    """Candidatos de beneficio de la sección de financiamiento y cobertura (con importe o porcentaje)."""
    out = []
    for documento in _documentos_con_parrafos(documentos):
        for parrafo in documento['parrafos']:
            texto = parrafo['texto']
            if parrafo['seccion_bases'] != 'financiamiento' or parrafo['encabezado']:
                continue
            if not re.search(r'\bUSD\s*[\d.,]+|\d\s*%', texto, re.I):
                continue
            for candidato in candidatos_adicionales({'beneficio': {'texto_original': texto}}, version_id=version_id,
                                                     documento_id=documento['documento_id'])['beneficios']:
                candidato['procedencia'] = {**candidato['procedencia'], 'pagina': parrafo['pagina'],
                                            'seccion': 'Bases en PDF · Financiamiento'}
                out.append(candidato)
    return out


def obligaciones_de_bases(documentos):
    """Texto literal de las obligaciones de la persona becaria y su procedencia, o None."""
    for documento in _documentos_con_parrafos(documentos):
        elementos = [p for p in documento['parrafos'] if p['seccion_bases'] == 'obligaciones' and not p['encabezado']
                     and (_NUMERADO.match(p['texto']) or _LITERAL.match(p['texto']))]
        if elementos:
            texto = '\n'.join(p['texto'] for p in elementos)[:MAX_OBLIGACIONES].strip()
            return {'texto': texto, 'documento_id': documento['documento_id'], 'pagina': elementos[0]['pagina']}
    return None


def cronograma_de_bases(documentos):
    """Párrafos del cronograma o la convocatoria, solo como evidencia."""
    return [{'texto': p['texto'], 'documento_id': d['documento_id'], 'pagina': p['pagina']}
            for d in _documentos_con_parrafos(documentos) for p in d['parrafos']
            if p['seccion_bases'] == 'cronograma' and not p['encabezado']]


def fragmentos_para_entidad(documentos):
    """Párrafos de las bases en el formato que usa la asignación de entidad (`entidad_en_documentos`)."""
    return {'documentos': [{'documento_id': d['documento_id'], 'fragmentos': [
        {'texto_original': p['texto'], 'procedencia': {'documento_id': d['documento_id'], 'pagina': p['pagina']}}
        for p in d['parrafos'] if not p['encabezado']]} for d in _documentos_con_parrafos(documentos)]}
