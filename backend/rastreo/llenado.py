"""Llenado automático del borrador de rastreo con lo que la extracción identificó con claridad.

Al crear el borrador (o al completar uno existente con el comando `completar_borradores`) se escriben,
en sus campos y en las listas normales de requisitos, beneficios y opciones de estudio, solo los datos
con evidencia directa de la ficha. Lo ambiguo no se escribe: queda como evidencia en la publicación.

Reglas:
- Nunca se sobrescribe un campo con valor ni se modifica un registro existente; lo ya procesado se
  registra en un libro (`datos_iniciales['llenado_automatico']`), de modo que un dato que el administrador
  borró o vació no se vuelve a escribir.
- Los requisitos se crean activos y sin validar; este proceso nunca marca nada como validado.
- No crea eventos de auditoría: el proceso automático no tiene actor. La procedencia de cada registro
  (texto literal, documento y sección) queda en el libro, sin migración.
"""
import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from datetime import date
from urllib.parse import urlsplit

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction

from convocatorias import serializers as catalogo_serializers
from convocatorias.models import Beneficio, OpcionEstudio, Requisito, TipoBeca, TipoRequisito
from convocatorias.reglas import EXTERNOS
from convocatorias.services import touch
from perfiles.models import Area, Pais

MODELOS = {'opciones': OpcionEstudio, 'beneficios': Beneficio, 'requisitos': Requisito}
SECCIONES = {'requisitos': 'Requisitos', 'beneficios': 'Beneficio', 'opciones': 'Estudios: nivel, modalidad y destino'}


def _normal(value):
    text = unicodedata.normalize('NFD', str(value or '').casefold())
    return ' '.join(''.join(c for c in text if unicodedata.category(c) != 'Mn').split())


def _huella(modelo, contenido):
    raw = json.dumps({'modelo': modelo, **contenido}, ensure_ascii=False, sort_keys=True, cls=DjangoJSONEncoder)
    return hashlib.sha256(raw.encode()).hexdigest()


def paises_de_destino(literal, paises):
    """Países del catálogo que nombra exactamente un destino literal; [] si alguno no coincide."""
    names = [part.strip() for part in re.split(r',|;|\s+y\s+|\s+e\s+', _normal(literal)) if part.strip()]
    if not names or not paises or any(name not in paises for name in names):
        return []
    return list(dict.fromkeys(paises[name] for name in names))


def filas_de_candidatos(found, tipos, paises=None):
    """Función pura: candidatos editables y catálogos → filas a escribir u omitidas (con su motivo)."""
    filas = []
    for item in found.get('requisitos', []):
        texto = (item.get('texto_original') or '').strip()
        codigo = item.get('tipo_sugerido')
        procedencia = item.get('procedencia') or {}
        base = {'modelo': 'requisitos', 'texto': texto, 'seccion': procedencia.get('seccion') or SECCIONES['requisitos'],
                'documento_id': procedencia.get('documento_id'), 'pagina': procedencia.get('pagina'), 'metodo': item.get('metodo'),
                # Las condiciones externas conservan la huella de siempre (tipo OTRO): cambiar su tipificación no
                # hace reaparecer un requisito que el administrador eliminó.
                'huella': _huella('requisitos', {'texto': _normal(texto), 'tipo': 'OTRO' if item.get('estado') == 'externa' else codigo})}
        if item.get('estado') == 'obligacion':
            filas.append({**base, 'omitido': 'Es una obligación posterior de la persona beneficiaria, no un requisito '
                                             'de postulación; se registra en las obligaciones del beneficiario.'})
            continue
        if item.get('estado') == 'externa':
            # La comprueba la entidad oferente: texto literal, nunca invertido ni evaluado por BecaNexo.
            # Si el tipo propio (p. ej. condición administrativa) aún no está en el catálogo, se usa OTRO.
            tipo = tipos.get(codigo) if codigo in EXTERNOS else None
            tipo = tipo or tipos.get('OTRO')
            if not tipo:
                filas.append({**base, 'omitido': 'Tipo de requisito OTRO no registrado en el catálogo.'})
                continue
            datos = {'tipo_requisito': tipo.pk, 'texto_original': texto, 'valor_estructurado': {'descripcion': texto},
                     'modo_comprobacion': 'entidad_oferente', 'obligatorio': True, 'validado': False, 'activo': True}
            filas.append({**base, 'datos': datos})
            continue
        if item.get('negacion_literal') or item.get('estado') == 'ambigua' or not codigo or codigo == 'OTRO':
            filas.append({**base, 'omitido': 'Interpretación ambigua o con negación; queda como evidencia en la publicación.'})
            continue
        tipo = tipos.get(codigo)
        if not tipo:
            filas.append({**base, 'omitido': f'Tipo de requisito {codigo} no registrado en el catálogo.'})
            continue
        datos = {'tipo_requisito': tipo.pk, 'texto_original': texto, 'valor_estructurado': item.get('valor_sugerido') or {},
                 'modo_comprobacion': 'entidad_oferente' if codigo in EXTERNOS else 'dato_declarado',
                 'obligatorio': True, 'validado': False, 'activo': True}
        filas.append({**base, 'datos': datos})
    for item in (found.get('otros_campos') or {}).get('beneficios', []):
        texto = (item.get('texto_original') or '').strip()
        concepto = (item.get('concepto_sugerido') or '').strip()
        procedencia = item.get('procedencia') or {}
        base = {'modelo': 'beneficios', 'texto': texto, 'seccion': procedencia.get('seccion') or SECCIONES['beneficios'],
                'documento_id': procedencia.get('documento_id'), 'pagina': procedencia.get('pagina'), 'metodo': 'regla',
                'huella': _huella('beneficios', {'texto': _normal(texto), 'concepto': _normal(concepto)})}
        if item.get('estado') != 'identificada' or not concepto:
            filas.append({**base, 'omitido': 'Beneficio sin concepto o cuantía identificados con claridad.'})
            continue
        datos = {'concepto': concepto[:100], 'porcentaje': item.get('porcentaje'), 'monto': item.get('monto'),
                 'moneda': item.get('moneda'), 'tope_original': item.get('tope_original'),
                 'tope_monto': item.get('tope_monto'), 'tope_moneda': item.get('tope_moneda'), 'detalle': texto or None}
        filas.append({**base, 'datos': datos})
    for item in found.get('opciones', []):
        texto = f"{item.get('nivel')} · {item.get('modalidad')} · {item.get('destino_original') or ''}".strip(' ·')
        procedencia = item.get('procedencia') or {}
        base = {'modelo': 'opciones', 'texto': texto, 'seccion': SECCIONES['opciones'],
                'documento_id': procedencia.get('documento_id'), 'metodo': 'enumeracion',
                'huella': _huella('opciones', {'nivel': item.get('nivel'), 'modalidad': item.get('modalidad'),
                                               'destino': _normal(item.get('destino_original'))})}
        # El destino solo pasa a país cuando coincide exactamente con el catálogo.
        datos = {'nivel': item.get('nivel'), 'modalidad': item.get('modalidad'), 'activa': True,
                 'paises': paises_de_destino(item.get('destino_original'), paises)}
        filas.append({**base, 'datos': datos})
    for item in found.get('opciones_pendientes', []):
        texto = f"{item.get('campo')}: {item.get('texto_original') or ''}".strip(' :')[:500]
        filas.append({'modelo': 'opciones', 'texto': texto, 'seccion': SECCIONES['opciones'], 'documento_id': None,
                      'huella': _huella('opciones_pendiente', {'campo': item.get('campo'), 'texto': _normal(item.get('texto_original'))}),
                      'omitido': item.get('motivo') or 'Dato de la opción de estudio sin equivalente exacto en el catálogo.'})
    return filas


def serializador_de_fila(fila, offer):
    """Serializer del catálogo que valida una fila antes de crearla (mismos contratos que el editor)."""
    serializer_type = {'opciones': catalogo_serializers.OpcionSerializer,
                       'beneficios': catalogo_serializers.BeneficioSerializer,
                       'requisitos': catalogo_serializers.RequisitoSerializer}[fila['modelo']]
    return serializer_type(data=fila['datos'], context={'convocatoria': offer})


def _ya_existe(offer, fila):
    datos = fila['datos']
    if fila['modelo'] == 'requisitos':
        return any(_normal(row) == _normal(datos['texto_original'])
                   for row in offer.requisitos.values_list('texto_original', flat=True))
    if fila['modelo'] == 'beneficios':
        return any(_normal(c) == _normal(datos['concepto']) and (_normal(d) == _normal(datos['detalle']) or not datos['detalle'])
                   for c, d in offer.beneficios.values_list('concepto', 'detalle'))
    return offer.opciones.filter(nivel=datos['nivel'], modalidad=datos['modalidad']).exists()


def contenido_de_requisito(requirement):
    """Huella del contenido de un requisito; permite saber si el administrador lo modificó después."""
    return _huella('contenido_requisito', {
        'tipo': requirement.tipo_requisito_id, 'texto': requirement.texto_original,
        'valor': requirement.valor_estructurado, 'obligatorio': requirement.obligatorio,
        'opcion': requirement.opcion_estudio_id, 'destino': requirement.destino_id,
        'documento': requirement.documento_exigido, 'acreditacion': requirement.detalle_acreditacion})


def _https_limpio(url):
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (parts.scheme == 'https' and bool(parts.hostname) and not parts.username and not parts.password
            and not parts.fragment and (not parts.query or bool(re.fullmatch(r't=\d+', parts.query))))


def limpiar_url(url):
    """Quita espacios y la puntuación de frase que suele quedar pegada al final de un enlace."""
    url = (url or '').strip()
    while url and (url[-1] in '.,;:!?»"\'' or (url[-1] == ')' and url.count('(') < url.count(')'))):
        url = url[:-1]
    return url


def _urls(items):
    return list(dict.fromkeys(limpiar_url(row['url']) for row in items or []
                              if isinstance(row, dict) and isinstance(row.get('url'), str) and row['url'].strip()))


def complementar_con_bases(found, bases, version_id):
    """Completa los candidatos de la ficha con las bases en PDF, sin cambiar lo que la ficha ya aporta.

    - Requisitos: se añaden los de las bases que la ficha no recoge (comparación robusta a espacios y signos).
    - Beneficios: solo si la ficha no trae ninguno.
    - Obligaciones de la persona becaria: solo si la ficha no las trae.
    """
    from .bases_pdf import beneficios_de_bases, clave, misma_condicion, obligaciones_de_bases, requisitos_de_bases
    if not bases:
        return found
    vistas = [item.get('texto_original') or '' for item in found.get('requisitos', [])]
    # Mismo tipo estructurado con los mismos valores (p. ej. «Ser ciudadano ecuatoriano» y «Nacionalidad
    # ecuatoriana»): es la misma condición, aunque la redacción no se parezca.
    estructuradas = {(item.get('tipo_sugerido'), json.dumps(item.get('valor_sugerido') or {}, sort_keys=True))
                     for item in found.get('requisitos', []) if item.get('estado') == 'identificada'}
    for item in requisitos_de_bases(bases, version_id):
        nueva = item.get('texto_original') or ''
        firma = (item.get('tipo_sugerido'), json.dumps(item.get('valor_sugerido') or {}, sort_keys=True))
        if item.get('estado') == 'identificada' and firma in estructuradas:
            continue
        if clave(nueva) and not any(misma_condicion(nueva, vista) for vista in vistas):
            vistas.append(nueva)
            if item.get('estado') == 'identificada':
                estructuradas.add(firma)
            found.setdefault('requisitos', []).append(item)
    otros = found.setdefault('otros_campos', {})
    if not otros.get('beneficios'):
        otros['beneficios'] = beneficios_de_bases(bases, version_id)
    if not any(item.get('estado') == 'obligacion' for item in found.get('requisitos', [])):
        otros['obligaciones_bases'] = obligaciones_de_bases(bases)
    return found


def campos_generales(found, evidencia):
    """Campos del formulario con evidencia directa de la ficha: [{campo, valor, literal, seccion}]."""
    data = evidencia['datos']
    extra = found.get('otros_campos') or {}
    out = []

    def add(campo, valor, literal, seccion):
        out.append({'campo': campo, 'valor': valor, 'literal': literal, 'seccion': seccion,
                    'documento_id': evidencia.get('documento_id')})
    # El enlace oficial es la ficha que describe la beca; el enlace de postulación suele ser un inicio de sesión.
    ficha = limpiar_url(evidencia.get('url_ficha'))
    if ficha and _https_limpio(ficha):
        add('url_oficial', ficha, 'URL de la ficha de origen', 'Ficha de origen')
    bases = _urls(data.get('enlaces_bases'))
    if len(bases) == 1 and _https_limpio(bases[0]):
        add('url_bases', bases[0], 'Enlace «BASES» de la ficha', 'Enlaces de la ficha')
    literal_type = (extra.get('tipo_beca_literal') or '').strip()
    if literal_type:
        add('tipo_beca', literal_type, f'Beca de {literal_type}', 'Título')
    if extra.get('cobertura_tipo_sugerida') in ('total', 'parcial', 'mixta'):
        source = (extra.get('cobertura_procedencia') or {}).get('campo')
        add('cobertura_tipo', extra['cobertura_tipo_sugerida'],
            f'Cobertura {extra["cobertura_tipo_sugerida"]}', 'Beneficio' if source == 'beneficio' else 'Descripción')
    if extra.get('gastos_no_cubiertos_literal'):
        add('gastos_no_cubiertos', extra['gastos_no_cubiertos_literal'], extra['gastos_no_cubiertos_literal'], 'Beneficio')
    obligations = [row['texto_original'] for row in found.get('requisitos', []) if row.get('estado') == 'obligacion']
    if obligations:
        add('obligaciones_beneficiario', '\n'.join(obligations), '\n'.join(obligations), 'Requisitos')
    published = ((extra.get('fechas') or {}).get('publicacion') or '')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', published):
        try:
            date.fromisoformat(published)
            add('fecha_publicacion', published, f'Publicada el {published}', 'Ficha de origen')
        except ValueError:
            pass
    names = extra.get('areas_literales')
    if isinstance(names, list) and names and all(isinstance(name, str) for name in names):
        add('areas', names, ', '.join(names), 'Ficha de origen')
    return out

_PUBLICO = re.compile(r'^(?:ministerio|secretaria|subsecretaria|gobierno\s+autonomo|prefectura|municipio|municipalidad|gad|alcaldia|'
                      r'servicio\s+nacional|senescyt|ifth|minedec)\b')
_PRIVADO = re.compile(r'\b(?:fundacion|corporacion|asociacion|privad[ao]|particular)\b')


def _sigla(nombre):
    found = re.search(r'\(([A-Z0-9]{2,12})\)\s*$', nombre or '')
    return found[1] if found else None


def _base(nombre):
    return _normal(re.sub(r'\s*\([A-Z0-9]{2,12}\)\s*$', '', nombre or ''))


def _plano(texto):
    """Minúsculas sin tildes y sin signos, carácter a carácter: conserva las posiciones del texto original."""
    salida = []
    for caracter in texto or '':
        base = ''.join(c for c in unicodedata.normalize('NFD', caracter.casefold()) if unicodedata.category(c) != 'Mn')
        salida.append(base if len(base) == 1 and base.isalnum() else ' ')
    return ''.join(salida)


def _alias_regex(alias):
    palabras = _plano(alias).split()
    return r'\s+'.join(re.escape(palabra) for palabra in palabras) if palabras else None


_VERBO = r'(?:otorgad[ao]s?|ofrecid[ao]s?|coofrecid[ao]s?|impulsad[ao]s?|financiad[ao]s?|convocad[ao]s?|ejecutad[ao]s?|promovid[ao]s?)'
_ACCION = (r'(?:ofrece|otorga|coofrece|convoca|impulsa|concede|financia|'
           r'tiene\s+por\s+(?:objetivo|objeto)\s+(?:otorgar|conceder|la\s+concesion|el\s+otorgamiento))')


def entidad_en_documentos(datos, texto, documento_id, registradas):
    """Entidad registrada que un documento de la misma versión nombra con papel de oferente o impulsora.

    Revisa la ficha y, cuando existan, los fragmentos de las bases en PDF. Devuelve las coincidencias
    [{institucion, literal, seccion, documento_id, pagina}] sin deducir nada por defecto.
    """
    fuentes = []
    for clave, etiqueta in (('titulo', 'Título'), ('descripcion', 'Descripción'), ('requisitos', 'Requisitos'),
                            ('postulacion_y_documentos', 'Postulación')):
        valor = datos.get(clave)
        if isinstance(valor, dict) and isinstance(valor.get('texto_original'), str):
            fuentes.append((valor['texto_original'], etiqueta, documento_id, None))
    if texto:
        fuentes.append((texto, 'Ficha de origen', documento_id, None))
    for documento in (datos.get('evidencia_pdf') or {}).get('documentos', []):
        for fragmento in documento.get('fragmentos', []):
            procedencia = fragmento.get('procedencia') or {}
            fuentes.append((fragmento.get('texto_original') or '', 'Bases en PDF',
                            procedencia.get('documento_id') or documento.get('documento_id'), procedencia.get('pagina')))
    encontradas = {}
    for institucion in registradas:
        alias = {institucion.nombre, re.sub(r'\s*\([A-Z0-9]{2,12}\)\s*$', '', institucion.nombre)}
        # «Ministerio X del Ecuador (SIGLA)» suele nombrarse en las bases sin el país: «Ministerio X».
        alias |= {re.sub(r'\s+(?:del|de)\s+ecuador$', '', nombre, flags=re.I) for nombre in list(alias)}
        sigla = _sigla(institucion.nombre)
        if sigla and len(sigla) >= 4:
            alias.add(sigla)
        for nombre in alias:
            expresion = _alias_regex(nombre)
            if not expresion or len(_plano(nombre).strip()) < 4:
                continue
            patron = re.compile(rf'(?:{_VERBO}\s+por\s+(?:el\s+|la\s+)?{expresion}\b|iniciativa\s+(?:del|de\s+la)\s+{expresion}\b|'
                                rf'a\s+cargo\s+del\s+{expresion}\b|\b{expresion}\s+{_ACCION}\b)')
            for contenido, seccion, documento, pagina in fuentes:
                encontrado = patron.search(_plano(contenido))
                if encontrado and institucion.pk not in encontradas:
                    inicio, fin = encontrado.span()
                    encontradas[institucion.pk] = {
                        'institucion': institucion, 'literal': contenido[max(0, inicio - 30):fin + 40].strip(),
                        'seccion': seccion, 'documento_id': documento, 'pagina': pagina}
    return list(encontradas.values())


def _resolver(nombre, datos, registradas):
    """Resuelve el nombre de una única candidata ecuatoriana: asignar una registrada, crear una nueva o nada."""
    from .auto_borradores import _MARCA_EC, _ecuadorian_institution
    declaradas = {(row.get('nombre') or '').strip() for row in datos.get('oferentes') or []
                  if isinstance(row, dict) and row.get('pais_codigo') == 'EC'}
    base = _base(nombre)
    # Sigla del candidato: entre paréntesis o tras un guion final («Ministerio X – SIGLA»).
    encontrada = re.search(r'(?:\(([A-Z0-9]{2,12})\)|[–—-]\s*([A-Z0-9]{3,12}))\s*$', nombre)
    siglas = (encontrada[1] or encontrada[2]) if encontrada else None
    coincidencias = [row for row in registradas if _normal(row.nombre) == _normal(nombre) or _base(row.nombre) == base
                     or (siglas and _sigla(row.nombre) == siglas)
                     or (_sigla(row.nombre) and _normal(_sigla(row.nombre)) == _normal(nombre))]
    if len(coincidencias) > 1:
        return {'accion': None, 'motivo': 'Varias entidades registradas podrían coincidir; no se asigna ninguna.'}
    if coincidencias:
        return {'accion': 'asignar', 'institucion': coincidencias[0]}
    if _ecuadorian_institution(nombre):
        return {'accion': None, 'motivo': 'El nombre solo coincide en parte con una entidad registrada; no se duplica ni se asigna.'}
    if not (re.search(_MARCA_EC, _normal(nombre)) or nombre in declaradas):
        return {'accion': None, 'motivo': 'Sin evidencia directa de que la entidad sea ecuatoriana.'}
    limpio = re.sub(r'\s+', ' ', re.split(r'\s+(?:20\d{2}|intake|cohorte)\b', nombre, maxsplit=1, flags=re.I)[0]).strip(' .,;:–-')[:200]
    plano = _normal(limpio)
    sector = 'publico' if _PUBLICO.match(plano) else 'privado' if _PRIVADO.search(plano) else None
    return {'accion': 'crear', 'nombre': limpio, 'sector': sector or 'privado', 'sector_por_defecto': sector is None}


def entidad_oferente(datos, texto='', documento_id=None):
    """Entidad oferente ecuatoriana de la ficha: asignar una registrada, crear una nueva o nada.

    Las entidades extranjeras y el lugar de estudio no cuentan. Con una única candidata ecuatoriana con
    papel claro de oferente o cooferente se asigna o crea; con dos o más distintas, o ninguna, no se hace nada.
    Si la ficha no nombra al oferente («esta Cartera de Estado»), solo se asigna una entidad registrada que un
    documento de la misma versión nombre explícitamente como oferente o impulsora.
    """
    from .auto_borradores import _named_entities, _texto
    from convocatorias.models import Institucion
    ecuatorianas = _named_entities(datos)[0]
    registradas = list(Institucion.objects.select_related('pais').filter(pais__codigo='EC'))
    candidatas = list(dict.fromkeys(ecuatorianas))
    resoluciones = [(nombre, _resolver(nombre, datos, registradas)) for nombre in candidatas]
    claves = {r['institucion'].pk if r.get('institucion') else _normal(r.get('nombre') or n)
              for n, r in resoluciones if r['accion']}
    if len(candidatas) > 1 and (len(claves) > 1 or any(r['accion'] is None for _n, r in resoluciones)):
        return {'accion': None, 'motivo': 'La ficha nombra varias entidades ecuatorianas como oferentes; no se asigna ninguna.'}
    if candidatas:
        nombre, resolucion = resoluciones[0]
        if resolucion['accion'] is None:
            return resolucion
        textos = {'Título': _texto(datos.get('titulo')), 'Descripción': _texto(datos.get('descripcion')),
                  'Requisitos': _texto(datos.get('requisitos')), 'Postulación': _texto(datos.get('postulacion_y_documentos'))}
        seccion, literal = 'Oferentes declarados', nombre
        for clave, valor in textos.items():
            posicion = valor.lower().find(nombre.lower())
            if posicion >= 0:
                seccion, literal = clave, valor[max(0, posicion - 40):posicion + len(nombre) + 40].strip()
                break
        return {**resolucion, 'nombre': resolucion.get('nombre') or nombre, 'literal': literal, 'seccion': seccion,
                'documento_id': documento_id, 'pagina': None}
    en_documentos = entidad_en_documentos(datos, texto, documento_id, registradas)
    if len(en_documentos) == 1:
        encontrada = en_documentos[0]
        return {'accion': 'asignar', 'institucion': encontrada['institucion'], 'nombre': encontrada['institucion'].nombre,
                'literal': encontrada['literal'], 'seccion': encontrada['seccion'],
                'documento_id': encontrada['documento_id'], 'pagina': encontrada['pagina']}
    if len(en_documentos) > 1:
        return {'accion': None, 'motivo': 'Los documentos nombran varias entidades registradas como oferentes; no se asigna ninguna.'}
    return {'accion': None, 'motivo': 'Ni la ficha ni sus documentos nombran una entidad ecuatoriana con papel de oferente.'}


def _vacio(offer, campo):
    if campo == 'areas':
        return not offer.areas.exists()
    if campo == 'tipo_beca':
        return offer.tipo_beca_id is None
    if campo == 'institucion':
        return offer.institucion_id is None
    return not getattr(offer, campo)


def _valor_de_campo(item, tipos_beca, areas):
    """Valor listo para el serializer, o None si no coincide exactamente con el catálogo."""
    if item['campo'] == 'tipo_beca':
        return tipos_beca.get(_normal(item['valor']))
    if item['campo'] == 'areas':
        found = [areas.get(_normal(name)) for name in item['valor']]
        return found if all(found) and len(set(found)) == len(found) else None
    return item['valor']


def completar_borrador(offer, evidencia, registro):
    """Escribe en el borrador lo identificado con claridad, sin sobrescribir ni repetir.

    `registro` es el libro de lo ya procesado y se actualiza in situ. Devuelve un resumen de lo escrito.
    """
    from .auto_borradores import candidatos_de_datos
    found = candidatos_de_datos(evidencia['datos'], evidencia['version_id'], evidencia.get('documento_id'), evidencia.get('texto') or '')
    complementar_con_bases(found, evidencia.get('bases') or [], evidencia['version_id'])
    tipos = {row.codigo: row for row in TipoRequisito.objects.all()}
    paises = {_normal(row.nombre): row.pk for row in Pais.objects.all()}
    registro.setdefault('campos', [])
    registro.setdefault('registros', [])
    registro.setdefault('omitidos', [])
    registro.setdefault('huellas', [])
    registro['version_id'] = evidencia['version_id']
    seen = set(registro['huellas'])
    resumen = {'campos': [], 'creados': [], 'omitidos': []}

    # 1. Campos generales: solo los vacíos y los que el proceso no escribió antes.
    ConvocatoriaSerializer = catalogo_serializers.ConvocatoriaSerializer
    tipos_beca = {_normal(row.nombre): row.pk for row in TipoBeca.objects.all()}
    areas = {_normal(row.nombre): row.pk for row in Area.objects.all()}
    written = {item['campo'] for item in registro['campos']}
    values, accepted = {}, []
    generales = campos_generales(found, evidencia)
    obligaciones = (found.get('otros_campos') or {}).get('obligaciones_bases')
    if obligaciones and not any(item['campo'] == 'obligaciones_beneficiario' for item in generales):
        generales.append({'campo': 'obligaciones_beneficiario', 'valor': obligaciones['texto'], 'literal': obligaciones['texto'],
                          'seccion': 'Bases en PDF · Obligaciones', 'documento_id': obligaciones['documento_id'],
                          'pagina': obligaciones['pagina']})
    if 'institucion' not in written and offer.institucion_id is None:
        entidad = entidad_oferente(evidencia['datos'], evidencia.get('texto') or '', evidencia.get('documento_id'))
        if entidad['accion']:
            entry = {'campo': 'institucion', 'literal': entidad['literal'], 'seccion': entidad['seccion'],
                     'documento_id': entidad.get('documento_id') or evidencia.get('documento_id'), 'nombre': entidad['nombre']}
            if entidad.get('pagina'):
                entry['pagina'] = entidad['pagina']
            nueva = None
            if entidad['accion'] == 'asignar':
                entry['valor'] = entidad['institucion'].pk
                entry['nombre'] = entidad['institucion'].nombre
            else:
                from convocatorias.models import Institucion
                ecuador = Pais.objects.filter(codigo='EC').first()
                if ecuador is None:
                    registro.setdefault('entidad_omitida', 'El país Ecuador no está en el catálogo; no se crea la entidad.')
                else:
                    nueva = Institucion.objects.create(nombre=entidad['nombre'], sector=entidad['sector'], pais=ecuador)
                    entry.update(valor=nueva.pk, entidad_creada=True, sector=entidad['sector'],
                                 sector_por_defecto=entidad['sector_por_defecto'])
            if entry.get('valor') is not None:
                generales.append(entry)
        else:
            registro.setdefault('entidad_omitida', entidad['motivo'])
    for item in generales:
        if item['campo'] in written or not _vacio(offer, item['campo']):
            continue
        value = _valor_de_campo(item, tipos_beca, areas)
        if value is None:
            continue
        probe = ConvocatoriaSerializer(offer, data={item['campo']: value}, partial=True)
        if probe.is_valid():
            values[item['campo']] = value
            accepted.append(item)
    if values:
        serializer = ConvocatoriaSerializer(offer, data=values, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        for item in accepted:
            entry = {key: item[key] for key in ('campo', 'valor', 'literal', 'seccion', 'documento_id', 'nombre', 'pagina',
                                                'entidad_creada', 'sector', 'sector_por_defecto') if key in item}
            registro['campos'].append(entry)
            resumen['campos'].append({'campo': item['campo'], 'valor': item['valor']})

    # 2. Registros de las listas normales.
    for fila in filas_de_candidatos(found, tipos, paises):
        entry = {'modelo': fila['modelo'], 'texto': fila['texto'][:500]}
        if fila['huella'] in seen:
            continue
        seen.add(fila['huella'])
        if 'omitido' in fila:
            registro['omitidos'].append({**entry, 'motivo': fila['omitido']})
            registro['huellas'].append(fila['huella'])
            resumen['omitidos'].append({**entry, 'motivo': fila['omitido']})
            continue
        if _ya_existe(offer, fila):
            motive = 'El borrador ya contiene un registro equivalente; se conserva sin cambios.'
            registro['omitidos'].append({**entry, 'motivo': motive})
            registro['huellas'].append(fila['huella'])
            resumen['omitidos'].append({**entry, 'motivo': motive})
            continue
        serializer = serializador_de_fila(fila, offer)
        if not serializer.is_valid():
            motive = 'Valores incompletos para el contrato del catálogo; queda como evidencia en la publicación.'
            registro['omitidos'].append({**entry, 'motivo': motive})
            registro['huellas'].append(fila['huella'])
            resumen['omitidos'].append({**entry, 'motivo': motive})
            continue
        try:
            with transaction.atomic():
                record = serializer.save(convocatoria=offer)
        except IntegrityError:
            # Un valor del catálogo recién ampliado cuya migración aún no se aplicó: se reintenta después.
            seen.discard(fila['huella'])
            resumen['omitidos'].append({**entry, 'transitorio': True,
                                        'motivo': 'La base de datos aún no admite este valor (migración del catálogo pendiente).'})
            continue
        registro['huellas'].append(fila['huella'])
        registro['registros'].append({
            **entry, 'id': record.pk, 'huella': fila['huella'], 'seccion': fila['seccion'], 'pagina': fila.get('pagina'),
            'documento_id': fila.get('documento_id') or evidencia.get('documento_id'), 'metodo': fila.get('metodo'),
            'contenido': contenido_de_requisito(record) if fila['modelo'] == 'requisitos' else None})
        resumen['creados'].append({**entry, 'id': record.pk})
    return resumen


def bases_de_version(version):
    """Lee los PDF de bases conservados de la versión, con los límites de `evidencia_pdf` (sin red)."""
    from .evidencia_pdf import MAX_DOCUMENTOS, leer_evidencia_pdf
    documentos, vistos = [], set()
    for relacion in version.documentos.filter(rol='bases_pdf').select_related('documento').order_by('id'):
        if relacion.documento.sha256 in vistos:
            continue
        vistos.add(relacion.documento.sha256)
        if len(documentos) >= MAX_DOCUMENTOS:
            break
        documentos.append(leer_evidencia_pdf(relacion, version.pk))
    return documentos


def evidencia_de_origen(origin, version=None):
    """Evidencia de una versión del borrador: datos y texto de la ficha y sus bases en PDF ya conservadas."""
    from .bases_pdf import fragmentos_para_entidad
    version = version or origin.version
    html = version.documentos.filter(rol='ficha_html').first()
    bases = bases_de_version(version) if hasattr(version, 'documentos') else []
    datos = dict(version.datos_extraidos or {})
    legibles = fragmentos_para_entidad(bases)['documentos']
    if legibles:
        # Copia en memoria: la versión conservada no se modifica. Se suman a los fragmentos que ya hubiera.
        previos = (datos.get('evidencia_pdf') or {}).get('documentos') or []
        datos['evidencia_pdf'] = {'documentos': previos + legibles}
    return {'version_id': version.pk, 'datos': datos, 'texto': getattr(version, 'texto_extraido', '') or '',
            'documento_id': html.documento_id if html else None, 'url_ficha': origin.publicacion.url_original,
            'bases': bases}


def llenar_origen(origin, version=None, *, tocar=False):
    """Completa el borrador de `origin` y guarda el libro en datos_iniciales. Un fallo no pierde el borrador."""
    offer = origin.convocatoria
    registro = deepcopy((origin.datos_iniciales or {}).get('llenado_automatico') or {})
    resumen = {'campos': [], 'creados': [], 'omitidos': [], 'error': None}
    try:
        with transaction.atomic():
            resumen = {**completar_borrador(offer, evidencia_de_origen(origin, version), registro), 'error': None}
            registro.pop('error', None)
    except Exception as exc:  # El borrador conserva su evidencia aunque el llenado falle.
        registro = deepcopy((origin.datos_iniciales or {}).get('llenado_automatico') or {})
        registro['error'] = type(exc).__name__
        resumen['error'] = type(exc).__name__
    origin.datos_iniciales = {**(origin.datos_iniciales or {}), 'llenado_automatico': registro}
    origin.save(update_fields=['datos_iniciales'])
    if tocar and (resumen['campos'] or resumen['creados']):
        offer.refresh_from_db()
        touch(offer)
    return resumen


def evidencia_visible(origin):
    """Campos y registros cargados automáticamente que siguen existiendo en el borrador."""
    registro = (origin.datos_iniciales or {}).get('llenado_automatico') or {}
    ids = {model: set() for model in MODELOS}
    for item in registro.get('registros', []):
        ids[item['modelo']].add(item['id'])
    alive = {model: set(MODELOS[model].objects.filter(convocatoria=origin.convocatoria, pk__in=ids[model]).values_list('pk', flat=True))
             for model in MODELOS}
    return {'campos': registro.get('campos', []),
            'registros': [item for item in registro.get('registros', []) if item['id'] in alive[item['modelo']]]}
