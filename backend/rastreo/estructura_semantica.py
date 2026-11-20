"""Candidatos editoriales con evidencia literal; nunca valida ni escribe reglas."""
import re
import unicodedata
from functools import lru_cache

from convocatorias.reglas import CONTRATOS
from convocatorias.semantica import ModeloNoDisponible, similitud, vector


PROTOTIPOS = {
    'NACIONALIDAD': 'Se requiere nacionalidad ecuatoriana o ciudadanía del Ecuador',
    'EDAD': 'La persona postulante debe tener una edad mínima y máxima',
    'FORMACION': 'Debe tener estudios de tercer nivel, grado o maestría',
    'TITULO_AREA': 'Debe poseer título profesional en un área académica específica',
    'PROMEDIO': 'Se exige promedio académico mínimo de notas',
    'IDIOMA': 'Se exige dominio certificado de idioma extranjero',
    'EXPERIENCIA': 'Se requiere experiencia laboral o profesional de varios años',
    'DEDICACION': 'Se exige disponibilidad para estudiar a tiempo completo o parcial',
    'TRASLADO': 'Se requiere disponibilidad para trasladarse a otro país',
    'RESIDENCIA': 'La persona debe residir en una ciudad o provincia',
    'DOCUMENTO': 'Debe presentar documentos y formularios de postulación',
}

PATRONES = {
    'NACIONALIDAD': r'\b(?:ciudadan\w*|nacionalidad)\b.{0,35}\becuatorian\w*\b',
    'EDAD': r'\b(?:edad|a[nñ]os cumplidos|entre\s+\d{1,2}\s+y\s+\d{1,2}\s+a[nñ]os)\b',
    'PROMEDIO': r'\b(?:promedio|nota media|puntaje acad[eé]mico)\b',
    'IDIOMA': r'\b(?:idioma|ingl[eé]s|franc[eé]s|alem[aá]n|portugu[eé]s|nivel\s+[abc][12])\b',
    'EXPERIENCIA': r'\bexperiencia\b',
    'DEDICACION': r'\b(?:dedicaci[oó]n|tiempo completo|tiempo parcial)\b',
    'TRASLADO': r'\b(?:traslado|trasladarse|movilidad geogr[aá]fica)\b',
    'RESIDENCIA': r'\b(?:residir|residencia|domicilio)\b',
    'TITULO_AREA': r'\bt[ií]tulo\b.{0,50}\b(?:en|de)\b',
    'FORMACION': r'\b(?:estudios de|estudios de tercer nivel|bachillerato|bachiller|maestr[ií]a|doctorado|t[ií]tulo de bachiller|matriculad[oa])\b',
    'ACREDITACION': r'\b(?:certificado|certificaci[oó]n)\b',
    'DOCUMENTO': r'\b(?:presentar|adjuntar|entregar)\b.{0,40}\b(?:copia|documento|formulario|solicitud)\b',
}


# Condiciones que no se estructuran con valores propios porque las comprueba la entidad oferente
# (registros administrativos, admisión al programa). Se conservan como texto literal, nunca se
# invierten ni se convierten en un dato que BecaNexo pueda dar por cumplido.
OBLIGACION = re.compile(r'\b(?:persona\s+)?(?:becari[oa]|beneficiari[oa])\s+(?:debera|debe)\b|'
                        r'\bpara\s+(?:mantener|renovar)\s+(?:la\s+)?beca\b|\bse\s+compromete\b')
ECUATORIANO = re.compile(r'\becuatorian\w*|\bnacionalidad\b')
PROHIBICION_ADMINISTRATIVA = re.compile(
    r'\bno\s+(?:contar\s+con|constar|figurar|mantener|'
    r'haber\s+(?:sido|obtenido|recibido|gozado|desistido|incumplido)|'
    r'estar\s+(?:cursando|por\s+iniciar|sujet[oa]|sancionad[oa]|inhabilitad[oa])|'
    r'tener\s+(?:impedimento|sancion|deuda|beca))\b|'
    r'\bque\s+no\s+(?:mantiene|tiene|posee|ha\s+sido|figura|consta)\b')
ADMISION_PROGRAMA = re.compile(
    r'\bhaber\s+sido\s+admitid[oa]\b|\bestar\s+cursando\s+estudios\b|\bestudiante\s+regular\b|'
    r'\btitulo\s+academico\s+previo\b|\bpara\s+cursar\s+un\s+programa\b')


# Categorías externas que la entidad oferente comprueba en sus registros administrativos: tipo propio.
# La admisión o matrícula en el programa sigue como «Otra condición externa».
CATEGORIAS_ADMINISTRATIVAS = {'prohibicion_administrativa', 'elegibilidad_por_verificar'}
TIPO_ADMINISTRATIVO = 'CONDICION_ADMINISTRATIVA'


def tipo_externo(categoria):
    return TIPO_ADMINISTRATIVO if categoria in CATEGORIAS_ADMINISTRATIVAS else 'OTRO'


def categoria_externa(n, negated):
    """Categoría de condición externa de una cláusula normalizada, o None si no corresponde."""
    if ECUATORIANO.search(n):
        return None  # La nacionalidad no se reinterpreta: sigue su propio contrato o queda ambigua.
    if (negated or re.search(r'\bque\s+no\b', n)) and PROHIBICION_ADMINISTRATIVA.search(n):
        return 'prohibicion_administrativa'
    if not negated and ADMISION_PROGRAMA.search(n):
        return 'admision_programa'
    return None


def normal(text):
    return ''.join(char for char in unicodedata.normalize('NFD', text.casefold())
                   if unicodedata.category(char) != 'Mn')


def unir_continuaciones(text):
    """Une las líneas que el maquetado de la ficha partió a mitad de frase.

    Una línea continúa a la anterior cuando la anterior no cerró la frase (., ;, :, ?, !) y la
    nueva empieza en minúscula o con «(» sin viñeta ni número. Las viñetas, los números y las
    líneas que empiezan en mayúscula siempre abren un elemento nuevo.
    """
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        marker = re.match(r'^(?:[-•*]|\d+[.)])\s*', stripped)
        content = stripped[marker.end():].strip() if marker else stripped
        if (lines and not marker and content and not re.search(r'[.;:?!]\s*$', lines[-1])
                and (content[0].islower() or content[0] == '(')):
            lines[-1] = f'{lines[-1]} {content}'
        else:
            lines.append(content)
    return lines


def dividir(text):
    """Solo separa cláusulas con un nuevo verbo de exigencia inequívoco."""
    result = []
    for line in unir_continuaciones(text):
        if not line or len(line) > 1000 or normal(line) in (
                'requisitos', 'requisitos generales', 'condiciones obligatorias'):
            continue
        for part in re.split(r'\s*;\s*|\s+y\s+(?=(?:ser|tener|contar|acreditar|presentar|residir|dominar|haber)\b)', line, flags=re.I):
            if part.strip():
                result.append(part.strip())
    return result[:30]


@lru_cache(maxsize=1)
def _prototipos_vector():
    return {code: vector(text) for code, text in PROTOTIPOS.items()}


def _semantica(text):
    try:
        target = vector(text)
        scores = sorted(((similitud(target, values), code) for code, values in _prototipos_vector().items()), reverse=True)
    except ModeloNoDisponible:
        return None, 'modelo_no_disponible', None
    best, second = scores[0], scores[1]
    if best[0] >= .55 and best[0] - second[0] >= .15:
        return best[1], 'onnx', round(best[0], 3)
    return None, 'ambigua', round(best[0], 3)


def _numero(value):
    return float(value.replace(',', '.'))


def _valores(code, text):
    n = normal(text)
    if code == 'NACIONALIDAD' and re.search(r'\becuatorian\w*\b', n):
        return {'codigos_pais': ['EC']}
    if code == 'EDAD':
        match = re.search(r'\bentre\s+(\d{1,2})\s+y\s+(\d{1,2})\s+anos\b', n)
        if match and int(match[1]) <= int(match[2]):
            return {'minimo': int(match[1]), 'maximo': int(match[2])}
        match = re.search(r'\b(?:minimo|mayor de|desde)\s+(\d{1,2})\s+anos\b', n)
        if match:
            return {'minimo': int(match[1])}
        match = re.search(r'\b(?:maximo|hasta)\s+(\d{1,2})\s+anos\b', n)
        return {'maximo': int(match[1])} if match else {}
    if code == 'PROMEDIO':
        match = re.search(r'\bpromedio\s+(?:minimo\s+(?:de\s+)?|de\s+al\s+menos\s+)(\d{1,2}(?:[.,]\d{1,2})?)\b', n)
        if not match:
            return {}
        result = {'minimo': _numero(match[1])}
        scale = re.search(r'\b(?:sobre|/)\s*(10|20|100)\b', n)
        if scale:
            result.update(escala_min=0, escala_max=int(scale[1]))
        return result
    if code == 'IDIOMA':
        languages = {'ingles': 'en', 'frances': 'fr', 'aleman': 'de', 'portugues': 'pt'}
        found = [value for word, value in languages.items() if re.search(r'\b' + word + r'\b', n)]
        level = re.search(r'\b([abc][12])\b', n)
        return {'codigo_idioma': found[0], 'nivel_minimo': level[1].upper()} if len(found) == 1 and level else {}
    if code == 'FORMACION':
        if n.strip(' .') == 'ser bachiller':
            return {'nivel_minimo': 'bachillerato', 'estado_exigido': 'concluidos', 'titulo_obtenido': True}
        if re.search(r'\bestar matriculad[oa]\b.{0,70}\bcarrera de tercer nivel de grado\b', n):
            return {'niveles_admitidos': ['grado'], 'estado_exigido': 'en_curso', 'titulo_obtenido': False}
        if re.search(r'\b(?:para cursar|para estudiar|estar cursando|ser estudiante|estar matriculad[oa]|haber sido admitid[oa])\b', n):
            return {}
        levels = {'bachillerato': 'bachillerato', 'tercer nivel': 'grado', 'grado': 'grado',
                  'maestria': 'maestria', 'doctorado': 'doctorado'}
        found = {value for phrase, value in levels.items() if re.search(r'\b' + phrase + r'\b', n)}
        if len(found) != 1:
            return {}
        result = {'nivel_minimo': found.pop()}
        if re.search(r'\b(?:haber concluido|estudios concluidos)\b', n):
            result['estado_exigido'] = 'concluidos'
        return result
    if code == 'TITULO_AREA':
        if len(re.findall(r'\bt[ií]tulo\b', text, re.I)) != 1 or re.search(r'\bt[ií]tulo\s+acad[eé]mico\s+previo\b', text, re.I):
            return {}
        match = re.search(r'\bt[ií]tulo\s+(?:universitario\s+)?(?:de|en)\s+(.{3,100})', text, re.I)
        return {'titulos_admitidos': [match[0].strip()]} if match else {}
    if code == 'EXPERIENCIA':
        match = re.search(r'\b(\d{1,2})\s+(anos|meses)\s+de\s+experiencia\b', n)
        return {'meses_minimos': int(match[1]) * (12 if match[2] == 'anos' else 1)} if match else {}
    if code == 'DEDICACION':
        found = [value for phrase, value in (('tiempo completo', 'completa'), ('tiempo parcial', 'parcial')) if phrase in n]
        return {'valores_admitidos': found} if len(found) == 1 else {}
    if code == 'TRASLADO' and re.search(r'\b(?:trasladarse|disponibilidad de traslado)\b', n):
        return {'requerido': True}
    if code == 'RESIDENCIA':
        result = {'codigos_pais': ['EC']} if re.search(r'\b(?:residir|residencia)\b.{0,25}\becuador\b', n) else {}
        province = re.search(r'\bprovincia\s+de\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})', text)
        if province:
            result['provincias'] = [province[1].strip()]
        return result
    if code == 'DOCUMENTO':
        return {'documento': text[:500]} if len(text) <= 500 else {}
    if code == 'ACREDITACION':
        return {'certificados_admitidos': text[:500]} if len(text) <= 500 else {}
    return {}


def interpretar_requisitos(text, *, version_id, url, documento_id=None):
    candidates = []
    for clause in dividir(text):
        n = normal(clause)
        labels = [code for code, pattern in PATRONES.items() if re.search(normal(pattern), n, re.I)]
        if 'IDIOMA' in labels and 'ACREDITACION' in labels:
            labels.remove('ACREDITACION')
        if 'FORMACION' in labels and 'TITULO_AREA' in labels:
            labels.remove('FORMACION')
        negated = bool(re.search(r'\b(?:no|sin|excepto|exclu(?:ido|ida|yen))\b', n))
        if negated:
            code, method, score = (labels[0] if len(labels) == 1 else None), 'negacion_pendiente', None
        elif len(labels) == 1:
            code, method, score = labels[0], 'regla', None
        elif labels:
            code, method, score = None, 'ambigua', None
        elif re.search(r'\b(?:derechos? de participacion|goce de derechos)\b', n):
            code, method, score = None, 'elegibilidad_por_verificar', None
        elif re.search(r'\brequisitos? generales?\b.{0,100}\b(?:convocatoria|bases)\b', n):
            code, method, score = None, 'referencia_externa', None
        else:
            code, method, score = _semantica(clause)
        values = _valores(code, clause) if code and not negated and method == 'regla' else {}
        state = 'ambigua' if negated or len(labels) > 1 or not code else (
            'identificada' if values else 'sugerida')
        if OBLIGACION.search(n):
            # Una obligación posterior de la persona beneficiaria nunca es un requisito de postulación,
            # aunque su redacción coincida con un documento o una formación.
            code, method, score, values, state = 'OTRO', 'obligacion_beneficiario', None, {}, 'obligacion'
        elif state != 'identificada':
            external = method if method == 'elegibilidad_por_verificar' else categoria_externa(n, negated)
            if external:
                # Condición que comprueba la entidad oferente: texto literal, sin valores ni inversión de la negación.
                code, method, score, values, state = tipo_externo(external), external, None, {}, 'externa'
        candidates.append({'texto_original': clause, 'tipo_sugerido': code or 'OTRO',
            'valor_sugerido': values, 'operador_sugerido': CONTRATOS[code][1] if code in CONTRATOS else None,
            'estado': state, 'metodo': method, 'puntuacion': score,
            'negacion_literal': negated, 'validado': False,
            'procedencia': {'version_id': version_id, 'campo': 'requisitos',
                            'url': url, 'documento_id': documento_id}})
    return candidates


def candidatos_adicionales(data, *, version_id, documento_id=None):
    """Campos literales o interpretados; nunca asigna catálogos ni postulación oficial."""
    def literal(key):
        value = data.get(key)
        return (value.get('texto_original') or value.get('original') or '') if isinstance(value, dict) else ''
    benefit = data.get('beneficio') or {}
    text = literal('beneficio')
    percents = re.findall(r'(?<!\d)(\d{1,3}(?:[.,]\d{1,2})?)\s*%', text)
    amount = re.search(r'\bUSD\s*([\d.,]+)\b', text, re.I)
    quantities = benefit.get('cantidades') or []
    quantity = quantities[0] if len(quantities) == 1 and isinstance(quantities[0], dict) else {}
    kind = quantity.get('tipo')
    percent = _numero(percents[0]) if len(percents) == 1 and (not amount or kind == 'tope') and _numero(percents[0]) <= 100 else None
    def money(raw):
        if not isinstance(raw, str) or not re.fullmatch(r'\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:\.\d{1,2})?', raw):
            return None
        if re.fullmatch(r'\d{1,3}(?:\.\d{3})+', raw):
            return _numero(raw.replace('.', ''))
        return _numero(raw.replace('.', '').replace(',', '.')) if ',' in raw else _numero(raw)
    numeric_amount = money(quantity.get('valor_literal')) if quantity.get('moneda') == 'USD' else None
    fixed_amount = numeric_amount if kind == 'monto_mencionado' and re.search(r'\bpor una sola vez\b', normal(text)) else None
    cap_amount = numeric_amount if kind == 'tope' else None
    concepts = benefit.get('conceptos') or []
    concept = ' y '.join(concepts) if concepts and len(concepts) <= 2 and all(isinstance(x, str) for x in concepts) else None
    coverage = re.search(r'\bcobertura\s+(total|parcial|mixta)\b', normal(text))
    description = data.get('descripcion') or {}
    partial_offer = isinstance(description, dict) and bool(re.search(
        r'\bbecas? parciales\b', normal(description.get('texto_original') or '')))
    uncovered = re.search(r'\b(?:gastos? no cubiertos?|no cubre)\b[^.;\n]{1,350}', text, re.I)
    title = literal('titulo')
    type_match = re.search(r'\bbeca\s+(?:de|por)\s+([\wáéíóúñ ]{3,70})', title, re.I)
    studies = data.get('estudios') or {}
    links = {'publicacion': data.get('url'), 'bases': data.get('enlaces_bases') or [],
             'postulacion': data.get('enlaces_postulacion') or []}
    return {'tipo_beca_literal': type_match[1].strip() if type_match else None,
            'cobertura_tipo_sugerida': coverage[1] if coverage else 'parcial' if partial_offer else None,
            'cobertura_procedencia': {'version_id': version_id,
                'campo': 'beneficio' if coverage else 'descripcion',
                'url': (benefit if coverage else description).get('url'),
                'documento_id': documento_id} if coverage or partial_offer else None,
            'gastos_no_cubiertos_literal': uncovered[0] if uncovered else None,
            'beneficios': [{'texto_original': text, 'porcentaje': percent,
                            'monto_literal': amount[0] if amount and kind != 'tope' else None,
                            'monto': fixed_amount, 'moneda': 'USD' if fixed_amount is not None else None,
                            'tope_original': quantity.get('original') if kind == 'tope' else None,
                            'tope_monto': cap_amount, 'tope_moneda': 'USD' if cap_amount is not None else None,
                            'concepto_sugerido': concept,
                            'estado': 'identificada' if percent is not None or amount else 'pendiente',
                            'procedencia': {'version_id': version_id, 'campo': 'beneficio',
                                            'url': benefit.get('url'), 'documento_id': documento_id}}] if text else [],
            'fechas': {'cierre': data.get('cierre'), 'apertura': data.get('apertura'),
                       'publicacion': data.get('fecha_publicacion')},
            'areas_literales': data.get('areas') or [],
            'estudios_literales': studies,
            'enlaces': links}
