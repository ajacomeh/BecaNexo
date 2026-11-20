"""Opciones de estudio candidatas a partir de lo que la ficha enumera explícitamente.

Funciones puras, sin red ni base de datos. Criterio aprobado: una opción por cada nivel y por cada
modalidad enumerados, tomando los niveles de un único enunciado de oferta y las modalidades del
mismo valor del campo, sin combinar enunciados distintos. Lo que no tiene equivalente exacto en el
catálogo, o lo que la ficha no enumera («Todas las modalidades»), no se deduce: queda como
pendiente con su motivo.
"""
import re

from .estructura_semantica import normal

# Expresión completa (normalizada, sin acentos) → nivel del catálogo. Solo nombres exactos:
# «técnico» o «tecnológico» sueltos, «posgrado» o «tecnológico superior universitario» no se deducen.
NIVEL_EXPRESIONES = (
    (r'maestrias? tecnologicas?', 'maestria_tecnologica'),
    (r'maestrias?', 'maestria'),
    (r'especializacion(?:es)?', 'especializacion'),
    (r'doctorados?', 'doctorado'),
    (r'bachillerato', 'bachillerato'),
    (r'grado|tercer nivel de grado', 'grado'),
    (r'tecnico superior', 'tecnico_superior'),
    (r'tecnologico superior', 'tecnologico_superior'),
)
MODALIDAD_EXPRESIONES = {'presencial': 'presencial', 'semipresencial': 'semipresencial', 'virtual': 'virtual',
                         'en linea': 'virtual', 'online': 'virtual', 'hibrida': 'hibrida', 'hibrido': 'hibrida'}


def campo_de_ficha(texto, etiqueta):
    """Valor de «Etiqueta: valor» en el texto de la ficha, con sus líneas de continuación.

    Una línea continúa el valor cuando empieza en minúscula o con «(» y el valor aún no cerró la frase.
    """
    lines = [line.strip() for line in (texto or '').splitlines()]
    for index, line in enumerate(lines):
        match = re.match(rf'^{etiqueta}\s*:\s*(.*)$', line, re.I)
        if not match:
            continue
        value = match.group(1).strip()
        for following in lines[index + 1:]:
            if not following or not (following[0].islower() or following[0] == '(') or re.search(r'[.;:?!]\s*$', value):
                break
            value = f'{value} {following}'
        return value
    return ''


def completar(valor, texto, etiqueta):
    """Completa un valor ya extraído con sus líneas de continuación, solo si el texto lo confirma."""
    valor = (valor or '').strip()
    completo = campo_de_ficha(texto, etiqueta)
    if valor and completo and normal(completo).startswith(normal(valor)):
        return completo
    return valor


def nivel_de_expresion(expresion):
    """Nivel del catálogo que nombra exactamente una expresión, o None."""
    n = ' '.join(normal(str(expresion)).split())
    for pattern, level in NIVEL_EXPRESIONES:
        if re.fullmatch(pattern, n):
            return level
    return None


def modalidades_de_texto(texto):
    """(modalidades del catálogo enumeradas, expresiones sin equivalente, «todas» sin enumerar)."""
    n = normal(texto or '')
    sin_enumerar = bool(re.search(r'\btodas las modalidades\b', n))
    n = re.sub(r'\btodas las modalidades\b', ' ', n)
    mapped, unmapped = [], []
    for part in re.split(r',|;|\(|\)|\s+y\s+|\s+e\s+|\s+o\s+', n):
        part = re.sub(r'^modalidad\s+', '', part.strip(' .:'))
        if not part:
            continue
        value = MODALIDAD_EXPRESIONES.get(part)
        if value and value not in mapped:
            mapped.append(value)
        elif not value and part not in unmapped:
            unmapped.append(part)
    return mapped, unmapped, sin_enumerar


def _niveles_de_oferta(studies):
    """(expresiones de nivel, enunciado, enunciados distintos) del único enunciado de oferta."""
    mentions = [m for m in studies.get('menciones_academicas') or []
                if isinstance(m, dict) and m.get('funcion') == 'oferta_mencionada']
    if not mentions:
        return [x for x in studies.get('niveles_mencionados') or [] if isinstance(x, str)], '', []
    statements = list(dict.fromkeys((m.get('contexto_original') or '').strip() for m in mentions))
    if len(statements) > 1:
        return [], '', statements
    expressions = list(dict.fromkeys(str(m.get('expresion_original') or '').strip() for m in mentions))
    return [x for x in expressions if x], statements[0], []


def opciones_candidatas(data, texto, version_id, niveles_catalogo, modalidades_catalogo=()):
    """Opciones de estudio candidatas y pendientes (con motivo) para una ficha."""
    studies = data.get('estudios') or {}

    def literal(key):
        value = studies.get(key)
        return (value.get('texto_original') or '').strip() if isinstance(value, dict) else ''
    modality_text = completar(literal('modalidad'), texto, 'Modalidad')
    destination = completar(literal('destino'), texto, r'Pa[ií]s')
    expressions, statement, distinct = _niveles_de_oferta(studies)
    pending = []
    if distinct:
        pending.append({'campo': 'nivel', 'texto_original': ' | '.join(item[:120] for item in distinct[:3]),
                        'motivo': 'Los niveles se mencionan en enunciados de oferta distintos; no se combinan. '
                                  'Confirma en las bases cuáles corresponden.'})
    levels = []
    for expression in expressions:
        level = nivel_de_expresion(expression)
        if level in niveles_catalogo:
            if level not in levels:
                levels.append(level)
        else:
            pending.append({'campo': 'nivel', 'texto_original': expression,
                            'motivo': f'Nivel «{expression}» sin equivalente exacto en el catálogo de niveles; '
                                      'confírmalo en las bases antes de crear la opción.'})
    modalities, unmapped, unspecified = modalidades_de_texto(modality_text)
    for expression in unmapped:
        pending.append({'campo': 'modalidad', 'texto_original': expression,
                        'motivo': f'Modalidad «{expression}» sin equivalente exacto en el catálogo de modalidades.'})
    todas = False
    if unspecified and not modalities and levels and modalidades_catalogo:
        # «Todas las modalidades» junto a niveles enumerados: una opción por nivel y por cada modalidad del catálogo.
        modalities, todas = list(modalidades_catalogo), True
    elif unspecified and not modalities:
        pending.append({'campo': 'modalidad', 'texto_original': modality_text,
                        'motivo': 'La ficha indica «Todas las modalidades» sin enumerarlas; no se deducen modalidades.'})
    options = []
    if levels and modalities and not destination:
        pending.append({'campo': 'destino', 'texto_original': '',
                        'motivo': 'La ficha no indica el destino de estudio; no se propone ninguna opción.'})
    elif levels and modalities:
        for level in levels:
            for modality in modalities:
                options.append({
                    'nivel': level, 'modalidad': modality, 'destino_original': destination, 'validado': False,
                    'procedencia': {'version_id': version_id, 'enunciado': statement[:300],
                                    'modalidad_original': modality_text[:200], 'todas_las_modalidades': todas,
                                    'campos': ['estudios.niveles_mencionados', 'estudios.modalidad', 'estudios.destino']}})
    return options, pending
