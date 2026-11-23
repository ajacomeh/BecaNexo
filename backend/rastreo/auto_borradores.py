"""Borradores técnicos desde fichas nacionales; nunca publica ni crea oferentes."""
import hashlib
import re
import unicodedata
from datetime import date
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.exceptions import PermissionDenied, ValidationError

from convocatorias.models import BorradorRastreo, Convocatoria, Evento, Institucion
from .models import Observacion, Publicacion, Version


def _literal(value, limit):
    text = (value.get('texto_original') or value.get('original') or '') if isinstance(value, dict) else ''
    return text.strip() if isinstance(text, str) and len(text.strip()) <= limit else ''


def _texto(value):
    """Texto literal completo, sin descartar contenido largo."""
    text = (value.get('texto_original') or value.get('original') or '') if isinstance(value, dict) else ''
    return text.strip() if isinstance(text, str) else ''


# Palabras con las que empieza el nombre de una entidad que puede ofrecer o coofrecer una beca.
_ENTIDAD = (r'(?:ministerio|secretar[ií]a|subsecretar[ií]a|universidad|escuela\s+polit[eé]cnica|instituto|fundaci[oó]n|'
            r'gobierno|prefectura|municipio|municipalidad|gad|alcald[ií]a|banco|corporaci[oó]n|consejo|agencia|embajada|'
            r'organizaci[oó]n|asociaci[oó]n|colegio|centro|senescyt|ifth|minedec|funiber|oea)')
_ROL = (r'(?:otorgad[ao]s?|ofrecid[ao]s?|coofrecid[ao]s?|financiad[ao]s?|auspiciad[ao]s?|patrocinad[ao]s?)\s+por|'
        r'en\s+(?:convenio|alianza|coordinaci[oó]n|cooperaci[oó]n)\s+con|con\s+el\s+(?:apoyo|auspicio|financiamiento)\s+de')
_MARCA_EC = r'\b(?:del\s+ecuador|de\s+ecuador|ecuatorian[oa]s?|senescyt|ifth|minedec)\b'
_MARCA_EXTRANJERA = (r'\b(?:europ\w*|americana|norteamerican\w*|iberoamerican\w*|espana|argentina|brunei|darussalam|corea|korea|'
                     r'japon|china|estados\s+unidos|reino\s+unido|alemania|francia|italia|mexico|chile|colombia|peru|brasil|'
                     r'indonesia|oea|fulbright|daad|chevening)\b')


def _ecuadorian_institution(name):
    normal = _normal(name)
    for institution in Institucion.objects.select_related('pais').filter(pais__codigo='EC'):
        aliases = {_normal(institution.nombre)}
        acronym = re.search(r'\(([A-Z0-9]{2,12})\)\s*$', institution.nombre)
        base = re.sub(r'\s*\([A-Z0-9]{2,12}\)\s*$', '', institution.nombre).strip()
        if base != institution.nombre and len(base) >= 20:
            aliases.add(_normal(base))
        if any(alias and alias in normal for alias in aliases) or (acronym and re.search(rf'\b{acronym[1]}\b', name)):
            return institution
    return None


def _named_entities(data):
    """Entidades nombradas como oferente o cooferente, separadas en ecuatorianas y extranjeras.

    Solo cuenta una entidad concreta (ministerio, universidad, fundación...) en un papel de
    oferta: «otorgada por», «en convenio con», un oferente declarado o un segmento del título.
    Una mención de Ecuador o de ecuatorianos como destinatarios no es una entidad.
    """
    ecuadorian, foreign, unknown = [], [], []

    def add(name):
        name = ' '.join(str(name).split())
        # El nombre termina antes de datos de la convocatoria: nivel, año, cohorte, semestre o intake.
        name = re.split(r'\s+(?:\d|\(?\d|[1-4](?:er|do|ro|to)\b|intake\b|cohorte\b|semestre\b|convocatoria\b|'
                        r'cuarto\s+nivel\b|tercer\s+nivel\b)', name, maxsplit=1, flags=re.I)[0]
        name = name.strip(' .,;:–-')[:160]
        if not name or not re.match(_ENTIDAD, _normal(name)):
            return
        if _ecuadorian_institution(name) or re.search(_MARCA_EC, _normal(name)):
            target = ecuadorian
        elif re.search(_MARCA_EXTRANJERA, _normal(name)):
            target = foreign
        else:
            target = unknown
        if name not in target:
            target.append(name)

    for row in data.get('oferentes') or []:
        if isinstance(row, dict) and row.get('rol') in ('oferente', 'cooferente') and isinstance(row.get('nombre'), str):
            if row.get('pais_codigo') == 'EC':
                if row['nombre'].strip() not in ecuadorian:
                    ecuadorian.append(row['nombre'].strip())
            elif row.get('pais_codigo'):
                if row['nombre'].strip() not in foreign:
                    foreign.append(row['nombre'].strip())
            else:
                add(row['nombre'])
    # entidad_html es una mención en la descripción, sin papel de oferente: no cuenta por sí sola.
    title = _texto(data.get('titulo'))
    # Los segmentos posteriores al primero suelen nombrar a la entidad o al cooferente.
    for segment in re.split(r'\s+[–—-]\s+', title)[1:]:
        add(segment)
    text = '\n'.join(_texto(data.get(key)) for key in ('titulo', 'descripcion', 'requisitos', 'postulacion_y_documentos'))
    for match in re.finditer(rf'(?:{_ROL})\s+(?:el|la|los|las)?\s*([^\n.;:,()]{{4,160}})', text, re.I):
        candidate = re.split(r'\s+(?:para|que|con\s+el\s+fin|a\s+trav[eé]s)\s+', match[1], maxsplit=1, flags=re.I)[0]
        # Una segunda entidad con su propio papel («en convenio con…») es otro candidato, no parte del nombre.
        for part in re.split(rf'\s+(?:{_ROL})\s+(?:el|la|los|las)?\s*', candidate, flags=re.I):
            add(part)
    # «…, del Ministerio X – SIGLA tiene por objetivo conceder becas»: la entidad que concede es oferente.
    for match in re.finditer(r'\bdel?\s+((?:Ministerio|Secretar[ií]a|Subsecretar[ií]a|Gobierno|Prefectura|Municipio|Universidad|'
                             r'Escuela\s+Polit[eé]cnica|Instituto|Fundaci[oó]n)[^\n.;:()]{3,150}?)\s+tiene\s+por\s+(?:objetivo|objeto)\s+'
                             r'(?:otorgar|conceder|la\s+concesi[oó]n|el\s+otorgamiento)', text, re.I):
        add(match[1])
    return ecuadorian, foreign, unknown


def _normal(value):
    return ' '.join(unicodedata.normalize('NFD', value).casefold().split()).translate(
        str.maketrans('', '', ''.join(chr(x) for x in range(0x300, 0x370))))


def _institution(data):
    mentioned = _literal(data.get('entidad_html'), 200)
    if not mentioned:
        return None
    matches = [row for row in Institucion.objects.select_related('pais').filter(pais__codigo='EC')
               if _normal(row.nombre) == _normal(mentioned)]
    return matches[0] if len(matches) == 1 else None


def _offerer_evidence(data):
    """Una fuente difusora no acredita por sí misma al oferente."""
    entries = data.get('oferentes') or []
    if not isinstance(entries, list):
        entries = []
    participating = [row for row in entries if isinstance(row, dict) and row.get('rol') in ('oferente', 'cooferente')
                     and isinstance(row.get('nombre'), str) and row['nombre'].strip()
                     and isinstance(row.get('evidencia'), str) and row['evidencia'].strip()]
    ec = [row for row in participating if row.get('pais_verificado') is True and row.get('pais_codigo') == 'EC']
    if ec:
        return 'verificado_ec', ec[0]['nombre'].strip(), 'Participación ecuatoriana respaldada en la ficha.'
    context = _normal(' '.join(_literal(data.get(key), 15000) for key in ('titulo', 'descripcion', 'requisitos', 'postulacion_y_documentos')))
    registered = []
    if re.search(r'\b(?:otorga|ofrece|coofrece|otorgad[ao]s?|ofrecid[ao]s?|coofrecid[ao]s?)\b', context):
        for institution in Institucion.objects.select_related('pais').filter(pais__codigo='EC'):
            aliases = {_normal(institution.nombre)}
            # Un acrónimo editorial al final del registro no forma parte del nombre
            # literal que puede aparecer en una ficha oficial.
            without_acronym = re.sub(r'\s*\([A-Z0-9]{2,12}\)\s*$', '', institution.nombre).strip()
            if without_acronym != institution.nombre and len(without_acronym) >= 20:
                aliases.add(_normal(without_acronym))
            if any(re.search(rf'\b(?:otorgad[ao]s?|ofrecid[ao]s?|coofrecid[ao]s?)\s+por\s+{re.escape(name)}\b', context)
                   or re.search(rf'\b{re.escape(name)}\s+(?:ofrece|otorga|coofrece)\b', context)
                   for name in aliases):
                registered.append(institution)
    if registered:
        return 'verificado_ec', ' / '.join(row.nombre for row in registered), 'Participación de entidad ecuatoriana registrada y explícita en la ficha.'
    if participating and all(row.get('pais_verificado') is True and row.get('pais_codigo') not in ('', None, 'EC')
                             for row in participating):
        return 'solo_extranjero', participating[0]['nombre'].strip(), 'Solo se identificaron oferentes extranjeros.'
    mentioned = _literal(data.get('entidad_html'), 200)
    return ('sugerido' if mentioned else 'desconocido', mentioned,
            'La entidad mencionada no acredita todavía que ofrezca la beca.' if mentioned
            else 'No se identificó una entidad oferente en la ficha.')


MARCA_OFERENTE_NO_EC = 'Oferente no ecuatoriano / no consta entidad ecuatoriana'


def oferente_externo(origin):
    """Marca y nombre detectado del oferente guardados al crear el borrador (sin entidad del catálogo)."""
    data = origin.datos_iniciales or {}
    if 'oferente_no_ecuatoriano' in data:
        return bool(data['oferente_no_ecuatoriano']), data.get('oferente_detectado') or ''
    return False, ''


def classify_candidate(publication, version, *, allow_partial=False):
    """Clasificación al crear el borrador: exige solo lo necesario para revisarlo.

    Toda ficha de una fuente autorizada cuyo título nombra una beca genera un borrador privado:
    confianza alta (oferente ecuatoriano verificado y destinatarios confirmados), media (entidad
    ecuatoriana nombrada o beca nacional de SIAU) o baja (oferente extranjero o sin entidad
    ecuatoriana). En el último caso el borrador lleva la marca de oferente no ecuatoriano y el
    nombre detectado como texto, sin registrarlo en el catálogo de entidades; publicarla es
    decisión del administrador. No hay borrador si la ficha no es una beca, si falta evidencia o si
    excluye expresamente a ciudadanos ecuatorianos (la beca debe admitirlos, no necesariamente en exclusiva).
    """
    marks = []

    def result(state, reason, confidence=None, **details):
        return {'estado': state, 'motivo': reason, 'confianza': confidence if state == 'apta' else 'baja',
                'marcas': list(dict.fromkeys(marks)) if state == 'apta' else [],
                'oferente': details.get('oferente', 'desconocido'),
                'oferente_mencionado': details.get('oferente_mencionado', ''),
                'elegibilidad': details.get('elegibilidad', 'no_especificada'),
                'naturaleza': details.get('naturaleza', 'sin_confirmar'),
                'datos_esenciales': details.get('datos_esenciales', False),
                'oferente_no_ecuatoriano': details.get('oferente_no_ecuatoriano', False),
                'oferente_detectado': details.get('oferente_detectado', '')}

    def no_ecuadorian(name, reason, **details):
        marks.append(f'{MARCA_OFERENTE_NO_EC}: {name}.' if name else f'{MARCA_OFERENTE_NO_EC}.')
        details.update(oferente_no_ecuatoriano=True, oferente_detectado=name)
        return result('apta', reason, 'baja', **details)
    data = version.datos_extraidos or {}
    full_title = _texto(data.get('titulo'))
    title = full_title[:250]
    if len(full_title) > 250:
        marks.append('Título truncado a 250 caracteres; el texto completo está en la ficha.')
    adapter = publication.fuente.adaptador
    portal_names = []
    if data.get('tipo_oportunidad') in ('pagina_informativa', 'categoria_general', 'noticia'):
        return result('fuera_alcance', 'Descartada: contenido informativo sin una beca individual identificable.', naturaleza='informativa')
    if adapter == 'siau':
        if not re.search(r'\bbecas?\b', _normal(title)):
            return result('fuera_alcance', 'Descartada: la ficha no identifica una beca individual.', naturaleza='sin_confirmar')
    elif adapter.startswith('portal_ec:'):
        from .portal_fuentes import portal_for_source, admitted_url
        try:
            portal = portal_for_source(publication.fuente)
        except Exception:
            return result('pendiente', 'Sin borrador: la fuente institucional no tiene una política auditada.')
        section_base = publication.url_original if portal.generico else portal.indice
        section_identity = (portal.secciones_en_indice and (portal.generico or publication.url_original == portal.indice)
                            and re.fullmatch(re.escape(section_base) + r'#becanexo-[0-9a-f]{20}', publication.url_normalizada))
        if not re.search(r'\bbecas?\b', _normal(title)):
            return result('fuera_alcance', 'Descartada: la ficha no describe una beca identificable.', naturaleza='informativa')
        if not (section_identity or admitted_url(portal, publication.url_normalizada)):
            return result('pendiente', 'Sin borrador: no se confirmó una ficha de beca del portal institucional.')
        if data.get('vigencia_al_consultar') == 'vencida':
            marks.append('Cierre vencido al consultar: solo puede publicarse como convocatoria histórica.')
        if not (data.get('cierre') or {}).get('fecha'):
            marks.append('Fecha de cierre no encontrada en la ficha.')
        elif Version.objects.filter(datos_extraidos__titulo__texto_original=full_title,
                                    datos_extraidos__cierre__fecha=data['cierre']['fecha'],
                                    publicacion__fuente__adaptador__startswith='portal_ec:').exclude(publicacion=publication).exists():
            marks.append('Posible duplicado: el mismo título y cierre constan en otra fuente.')
        # El portal es la web oficial de la entidad registrada: se nombra como oferente por confirmar.
        portal_names.append(portal.institucion or publication.fuente.nombre)
    else:
        return result('fuera_alcance', 'Descartada: adaptador sin clasificación de becas autorizada.')
    if not version.documentos.filter(rol='ficha_html').exists():
        return result('pendiente', 'Sin borrador: no se conservó la ficha HTML que permite revisarla.')
    if data.get('seccion_completa') is not True:
        marks.append('Estructura de ficha distinta o incompleta; revisa la ficha archivada.')
    if not _texto(data.get('requisitos')):
        marks.append('Requisitos no encontrados en la ficha.')
    if not _texto(data.get('cierre')):
        marks.append('Cierre no encontrado en la ficha.')
    if not _texto(data.get('descripcion')):
        marks.append('Descripción no encontrada en la ficha.')
    scope = ' '.join(_normal(_texto(data.get(key))) for key in ('titulo', 'descripcion', 'requisitos', 'postulacion_y_documentos'))
    offerer, mentioned, offerer_reason = _offerer_evidence(data)
    details = {'oferente': offerer, 'oferente_mencionado': mentioned,
               'naturaleza': 'beca_individual', 'datos_esenciales': bool(
                   data.get('seccion_completa') and _texto(data.get('requisitos')) and _texto(data.get('cierre')))}
    # La beca debe admitir ciudadanos ecuatorianos (no necesariamente de forma exclusiva): la exclusión expresa descarta la ficha.
    if re.search(r'\b(?:no\s+(?:pueden|podran)\s+postular|no\s+se\s+admiten|se\s+excluye(?:n)?\s+a?)\s+(?:personas|ciudadan[oa]s?)?\s*ecuatorian[oa]s?\b', scope):
        return result('fuera_alcance', 'Descartada: la ficha excluye expresamente a ciudadanos ecuatorianos.',
                      elegibilidad='excluida', **details)
    recipient = 'confirmada' if re.search(
        r'\b(?:personas|estudiantes|postulantes|ciudadan[oa]s?(?:/[oa]s?)?)\s+ecuatorian[oa]s?(?:/[oa]s?)?\b|'
        r'\bciudadan[oa]s?\s+del\s+ecuador\b|\bnacionalidad\s+ecuatoriana\b|'
        r'\bcedula\s+de\s+ciudadania\s+ecuatoriana\b|'
        r'\becuatorian[oa]s?\s+(?:pueden|podran|deben)\s+postular\b', scope
    ) else 'no_especificada'
    details['elegibilidad'] = recipient
    if recipient != 'confirmada':
        marks.append('Participación de ciudadanos ecuatorianos por confirmar en las bases.')
    if offerer == 'solo_extranjero':
        return no_ecuadorian(mentioned, f'Borrador privado: oferente extranjero ({mentioned}); no consta entidad ecuatoriana.', **details)
    if offerer == 'verificado_ec':
        if recipient == 'confirmada':
            return result('apta', 'Borrador privado con oferente ecuatoriano verificado y destinatarios confirmados.', 'alta', **details)
        return result('apta', 'Borrador privado con oferente ecuatoriano verificado.', 'media', **details)
    ecuadorian, foreign, unknown = _named_entities(data)
    # Un portal institucional registrado y auditado pertenece a una entidad ecuatoriana.
    ecuadorian = list(dict.fromkeys([name for name in portal_names if name] + ecuadorian))
    if ecuadorian:
        details.update(oferente='mencionado_ec', oferente_mencionado=' / '.join(ecuadorian))
        if portal_names and ecuadorian == [name for name in portal_names if name]:
            marks.append('Oferente inferido del portal institucional; confirma que la beca es propia.')
        else:
            marks.append(f'Oferente o cooferente ecuatoriano por verificar: {" / ".join(ecuadorian)}.')
        return result('apta', 'Borrador privado: entidad ecuatoriana nombrada como oferente o cooferente.', 'media', **details)
    national_siau = adapter == 'siau' and bool(re.search(r'\bbecas?\s+nacionales?\b', _normal(title)))
    if national_siau:
        marks.append('Oferente por identificar en las bases de la beca nacional.')
        return result('apta', 'Borrador privado de beca nacional difundida por SIAU.', 'media', **details)
    if foreign:
        details.update(oferente='extranjero_nombrado', oferente_mencionado=' / '.join(foreign))
        return no_ecuadorian(' / '.join(foreign), f'Borrador privado: oferente extranjero ({" / ".join(foreign)}); no consta entidad ecuatoriana.', **details)
    if unknown:
        return no_ecuadorian(' / '.join(unknown), f'Borrador privado: la entidad nombrada ({" / ".join(unknown)}) no consta como ecuatoriana. '
                             'Si lo es, regístrala en Entidades oferentes y asígnala.', **details)
    return no_ecuadorian('', 'Borrador privado: la ficha no nombra una entidad ecuatoriana como oferente o cooferente.', **details)


def candidate_assessment(publication, version):
    assessment = classify_candidate(publication, version)
    return assessment['estado'] == 'apta', (
        assessment['motivo'] if assessment['estado'] != 'apta' or assessment['elegibilidad'] == 'no_especificada' else None)


def candidatos_de_datos(data, version_id, document_id=None, texto=''):
    """Función pura: requisitos, opciones y campos adicionales a partir de los datos extraídos.

    `texto` es el texto conservado de la ficha: completa valores que el maquetado partió en dos líneas.
    """
    from convocatorias.models import NIVELES_OPCION
    from perfiles.models import MODALIDADES
    from .estructura_semantica import interpretar_requisitos, candidatos_adicionales
    from .estudios import opciones_candidatas
    requirements = _texto(data.get('requisitos'))
    suggestions = interpretar_requisitos(requirements, version_id=version_id,
        url=(data.get('requisitos') or {}).get('url'), documento_id=document_id)
    options, pending_options = opciones_candidatas(data, texto, version_id, {value for value, _label in NIVELES_OPCION},
                                                     [value for value, _label in MODALIDADES])
    fields = candidatos_adicionales(data, version_id=version_id, documento_id=document_id)
    return {'requisitos': suggestions, 'opciones': options, 'opciones_pendientes': pending_options, 'otros_campos': fields}


def editable_candidates(version):
    """Interpreta la evidencia sin escribir ni validar candidatos editoriales."""
    from .evidencia_tabular import extraer_tablas
    from .evidencia_pdf import MAX_DOCUMENTOS, leer_evidencia_pdf
    from .propuestas_documentales import proponer
    from .storage import StorageError, root_path, verify_file
    data = version.datos_extraidos or {}
    html = version.documentos.filter(rol='ficha_html').select_related('documento').first()
    document_id = html.documento_id if html else None
    found = candidatos_de_datos(data, version.pk, document_id, getattr(version, 'texto_extraido', '') or '')
    suggestions, options, fields = found['requisitos'], found['opciones'], found['otros_campos']
    fields['evidencia_tabular'] = {'tablas': [], 'enlaces_documentales': [], 'estado': 'sin_html'}
    if html:
        try:
            document = html.documento
            path = root_path() / document.clave_almacenamiento
            verify_file(path, document.sha256, document.tamano_bytes)
            fields['evidencia_tabular'] = {**extraer_tablas(path.read_bytes(), html.url_normalizada,
                version_id=version.pk, documento_id=document_id), 'estado': 'extraida'}
        except (StorageError, OSError, UnicodeError, ValueError):
            fields['evidencia_tabular']['estado'] = 'no_disponible'
    pdfs = list(version.documentos.filter(rol='bases_pdf').select_related('documento').order_by('id')[:MAX_DOCUMENTOS * 4])
    seen = {}
    documents = []
    omitted = len(pdfs) == MAX_DOCUMENTOS * 4
    for row in pdfs:
        key = row.documento.sha256
        if key in seen:
            if row.url_normalizada not in seen[key]['urls']:
                seen[key]['urls'].append(row.url_normalizada)
        elif len(documents) < MAX_DOCUMENTOS:
            result = leer_evidencia_pdf(row, version.pk)
            seen[key] = result
            documents.append(result)
        else:
            omitted = True
    fields['evidencia_pdf'] = {'documentos': documents, 'omitidos_por_limite': omitted}
    fields['propuestas_documentales'] = proponer(fields['evidencia_tabular'], fields['evidencia_pdf'])
    return {'requisitos': suggestions, 'opciones': options, 'opciones_pendientes': found['opciones_pendientes'],
            'otros_campos': fields}


def _candidate(publication, version):
    return candidate_assessment(publication, version)[0]


def latest_version(publication):
    observed = Observacion.objects.filter(publicacion=publication, version__isnull=False).select_related('version').order_by('-id').first()
    return observed.version if observed else None


def reevaluate_stored(publication_id, *, apply=False):
    """Vista previa idempotente; la escritura requiere opt-in explícito del llamador."""
    publication = Publicacion.objects.select_related('fuente').get(pk=publication_id)
    version = latest_version(publication)
    if not version:
        return {'publicacion_id': publication_id, 'version_id': None, 'estado': 'pendiente',
                'motivo': 'No existe una versión conservada para reevaluar.', 'borrador_id': None, 'creado': False}
    assessment = classify_candidate(publication, version)
    result = {'publicacion_id': publication_id, 'version_id': version.pk, **assessment,
              'borrador_id': publication.convocatoria_id, 'creado': False}
    if apply and assessment['estado'] == 'apta':
        origin, created, _ = prepare_automatic_draft(publication_id, version.pk)
        result['borrador_id'] = origin.convocatoria_id if origin else publication.convocatoria_id
        result['creado'] = created
    return result


def materially_changed(first, second):
    if not second or first.pk == second.pk:
        return False
    def bases(version):
        return sorted((entry['url'], entry['sha256']) for entry in version.manifiesto.get('documentos', [])
                      if entry.get('rol') == 'bases_pdf')
    return first.hash_contenido_relevante != second.hash_contenido_relevante or bases(first) != bases(second)


def version_confirmed(offer, version):
    row = Evento.objects.filter(convocatoria=offer, accion='confirmar_version_rastreo',
                                cambios__version_id=version.pk).order_by('-id').first()
    if not row:
        return False
    saved = row.cambios.get('oferta_version')
    return saved == offer.version or (offer.revision == 'validada' and saved == offer.version - 1)


def review_baseline(origin, offer):
    """Última evidencia confirmada, sin modificar la versión de origen del borrador."""
    for event in Evento.objects.filter(convocatoria=offer, accion='confirmar_version_rastreo').order_by('-id'):
        version = Version.objects.filter(pk=event.cambios.get('version_id'), publicacion=origin.publicacion).first()
        if version:
            return version
    return origin.version


@transaction.atomic
def confirm_latest_version(offer_id, version_id, offer_version, actor_id, reason):
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ValidationError({'motivo': 'Describe la comparación con la versión nueva (máximo 1000 caracteres).'})
    actor = get_user_model().objects.get(pk=actor_id)
    if not actor.is_active or actor.rol != 'administrador':
        raise PermissionDenied()
    origin = BorradorRastreo.objects.select_related('publicacion', 'version').get(convocatoria_id=offer_id)
    publication = Publicacion.objects.select_for_update().get(pk=origin.publicacion_id)
    offer = Convocatoria.objects.select_for_update().get(pk=offer_id)
    current = latest_version(publication)
    if not current or current.pk != version_id or offer.version != offer_version:
        raise ValidationError('La versión de la fuente o del borrador cambió; vuelve a comparar antes de confirmar.')
    if not materially_changed(review_baseline(origin, offer), current):
        raise ValidationError('No hay cambios relevantes pendientes de esta versión.')
    if version_confirmed(offer, current):
        return current, False
    Evento.objects.create(actor=actor, convocatoria=offer, accion='confirmar_version_rastreo',
        cambios={'version_id': current.pk, 'version_origen_id': origin.version_id,
                 'oferta_version': offer.version, 'motivo': reason.strip()})
    return current, True


@transaction.atomic
def prepare_automatic_draft(publication_id, version_id, *, allow_partial=False):
    publication = Publicacion.objects.select_for_update().select_related('fuente').get(pk=publication_id)
    if publication.convocatoria_id:
        origin = BorradorRastreo.objects.filter(publicacion=publication).select_related('convocatoria', 'version').first()
        if not origin:
            return None, False, None
        version = Version.objects.get(pk=version_id, publicacion=publication)
        if materially_changed(review_baseline(origin, origin.convocatoria), version) and not version_confirmed(origin.convocatoria, version):
            offer = origin.convocatoria
            if offer.revision == 'validada':
                offer.revision = 'pendiente'
                offer.version += 1
                offer.actualizado_en = timezone.now()
                offer.save(update_fields=['revision', 'version', 'actualizado_en'])
            return origin, False, f'Versión {version.pk} con cambios relevantes; revisión administrativa pendiente.'
        return origin, False, None
    version = Version.objects.get(pk=version_id, publicacion=publication)
    assessment = classify_candidate(publication, version, allow_partial=allow_partial)
    if assessment['estado'] != 'apta':
        return None, False, assessment['motivo']
    data = version.datos_extraidos
    # Textos íntegros; solo el título se ajusta al límite del modelo y queda marcado.
    title = _texto(data.get('titulo'))[:250]
    description = _texto(data.get('descripcion'))
    closure_original = _texto(data.get('cierre'))
    closure_day = None
    if closure_original and isinstance(data.get('cierre'), dict):
        try:
            closure_day = date.fromisoformat(data['cierre'].get('fecha') or '')
        except ValueError:
            pass
    institution_suggestion = _institution(data)
    if not institution_suggestion and assessment['oferente'] == 'verificado_ec' and assessment['oferente_mencionado']:
        matches = [row for row in Institucion.objects.select_related('pais').filter(pais__codigo='EC')
                   if _normal(row.nombre) == _normal(assessment['oferente_mencionado'])]
        institution_suggestion = matches[0] if len(matches) == 1 else None
    requirements = _texto(data.get('requisitos'))
    pending = []
    if assessment['oferente_no_ecuatoriano']:
        pending.append('Oferente no ecuatoriano o sin entidad ecuatoriana: publicarla exige confirmación expresa '
                       '(«Publicar bajo mi responsabilidad»).')
    else:
        pending.append('Identificar entidad oferente si la evidencia lo permite; no atribuir la fuente difusora.')
    if assessment['elegibilidad'] == 'no_especificada':
        pending.append('Confirmar en las bases si ciudadanos ecuatorianos pueden participar.')
    if not description: pending.append('Completar descripción respaldada.')
    if not closure_day: pending.append('Verificar vigencia y fecha de cierre.')
    if requirements: pending.append('Estructurar y revisar requisitos extraídos.')
    else: pending.append('Verificar requisitos de la beca en la fuente oficial.')
    pending.extend(['Confirmar enlace oficial de consulta o postulación.',
                    'Registrar y revisar al menos una opción de estudio.'])
    if version.manifiesto.get('pendientes'):
        pending.append('Resolver documentos de bases pendientes.')
    snapshot = {'titulo': title, 'descripcion': description, 'cierre_original': closure_original,
                'cierre_dia_interpretado': closure_day.isoformat() if closure_day else None,
                'entidad_mencionada': assessment['oferente_mencionado'],
                'entidad_sugerida': {'id': institution_suggestion.pk, 'nombre': institution_suggestion.nombre} if institution_suggestion else None,
                'requisitos_originales': requirements,
                'modalidad_mencionada': _literal((data.get('estudios') or {}).get('modalidad'), 60),
                'destino_mencionado': _literal((data.get('estudios') or {}).get('destino'), 500),
                'beneficio_original': _texto(data.get('beneficio')),
                'url_publicacion': publication.url_original,
                'oferente_no_ecuatoriano': assessment['oferente_no_ecuatoriano'],
                'oferente_detectado': assessment['oferente_detectado'],
                'clasificacion_inicial': assessment}
    identity = hashlib.sha256(f'rastreo:{publication.pk}'.encode()).hexdigest()
    offer = Convocatoria.objects.create(institucion=None, titulo=title, descripcion=description,
        cierre_original=closure_original or None, cierre_dia=closure_day, url_oficial='',
        clave_deduplicacion=identity, revision='pendiente', activa=True)
    origin = BorradorRastreo.objects.create(publicacion=publication, convocatoria=offer, version=version,
        datos_iniciales=snapshot, pendientes_iniciales=pending)
    publication.convocatoria = offer
    publication.save(update_fields=['convocatoria'])
    # Escribe en los campos y listas normales lo identificado con claridad; un fallo no pierde el borrador.
    from .llenado import llenar_origen
    llenar_origen(origin)
    return origin, True, assessment['motivo'] if assessment['elegibilidad'] == 'no_especificada' else None


def _classify_for_publication(publication, version, *, allow_partial=False):
    """Regla de publicación vigente (sin cambios): la versión actual debe acreditar una beca en alcance.

    Se conserva tal cual estaba antes de relajar la creación de borradores, para que
    pending_for_publication siga exigiendo exactamente lo mismo al publicar.
    """
    def result(state, reason, **details):
        return {'estado': state, 'motivo': reason, 'oferente': details.get('oferente', 'desconocido'),
                'oferente_mencionado': details.get('oferente_mencionado', ''),
                'elegibilidad': details.get('elegibilidad', 'no_especificada'),
                'naturaleza': details.get('naturaleza', 'sin_confirmar'),
                'datos_esenciales': details.get('datos_esenciales', False)}
    data = version.datos_extraidos or {}
    title = _literal(data.get('titulo'), 250)
    adapter = publication.fuente.adaptador
    if data.get('tipo_oportunidad') in ('pagina_informativa', 'categoria_general', 'noticia'):
        return result('fuera_alcance', 'Contenido informativo sin beca individual identificable.', naturaleza='informativa')
    if adapter == 'siau':
        if not re.search(r'\bbecas?\b', _normal(title)):
            return result('fuera_alcance', 'La ficha no identifica una beca individual.', naturaleza='sin_confirmar')
    elif adapter.startswith('portal_ec:'):
        from .portal_fuentes import portal_for_source, admitted_url
        try:
            portal = portal_for_source(publication.fuente)
        except Exception:
            return result('pendiente', 'Fuente institucional sin política auditada.')
        section_base = publication.url_original if portal.generico else portal.indice
        section_identity = (portal.secciones_en_indice and (portal.generico or publication.url_original == portal.indice)
                            and re.fullmatch(re.escape(section_base) + r'#becanexo-[0-9a-f]{20}', publication.url_normalizada))
        if not re.search(r'\bbecas?\b', _normal(title)):
            return result('fuera_alcance', 'La ficha no describe una beca identificable.', naturaleza='informativa')
        if not (section_identity or admitted_url(portal, publication.url_normalizada)):
            return result('pendiente', 'No se confirmó una ficha de beca del portal institucional.')
        if portal.generico and data.get('vigencia_al_consultar') == 'vencida':
            return result('pendiente', 'Cierre vencido; conservar evidencia sin crear un borrador nuevo.')
        if not (data.get('cierre') or {}).get('fecha'):
            return result('pendiente', 'Fecha de cierre de la ficha institucional pendiente de verificación.')
        if Version.objects.filter(datos_extraidos__titulo__texto_original=title,
                                  datos_extraidos__cierre__fecha=data['cierre']['fecha'],
                                  publicacion__fuente__adaptador__startswith='portal_ec:').exclude(publicacion=publication).exists():
            return result('pendiente', 'Título y cierre coinciden con otra fuente; revisión de posible duplicado.')
    else:
        return result('fuera_alcance', 'Adaptador sin clasificación de becas autorizada.')
    if not version.documentos.filter(rol='ficha_html').exists():
        return result('pendiente', 'Ficha nacional sin evidencia HTML completa.')
    if not allow_partial and data.get('seccion_completa') is not True:
        return result('pendiente', 'Ficha nacional sin evidencia HTML completa.')
    if not allow_partial and (not _literal(data.get('requisitos'), 5000) or not _literal(data.get('cierre'), 500)):
        return result('pendiente', 'No se verificaron requisitos y cierre de la oportunidad.')
    if allow_partial and not _literal(data.get('descripcion'), 15000):
        return result('pendiente', 'La ficha no aporta descripción suficiente para identificar una beca individual.')
    scope = ' '.join(_normal(_literal(data.get(key), 15000)) for key in ('titulo', 'descripcion', 'requisitos', 'postulacion_y_documentos'))
    offerer, mentioned, offerer_reason = _offerer_evidence(data)
    details = {'oferente': offerer, 'oferente_mencionado': mentioned,
               'naturaleza': 'beca_individual', 'datos_esenciales': bool(
                   data.get('seccion_completa') and _literal(data.get('requisitos'), 5000)
                   and _literal(data.get('cierre'), 500))}
    if re.search(r'\b(?:no\s+(?:pueden|podran)\s+postular|no\s+se\s+admiten|se\s+excluye(?:n)?\s+a?)\s+(?:personas|ciudadan[oa]s?)?\s*ecuatorian[oa]s?\b', scope):
        return result('fuera_alcance', 'La ficha excluye expresamente a ciudadanos ecuatorianos.',
                      elegibilidad='excluida', **details)
    recipient = 'confirmada' if re.search(
        r'\b(?:personas|estudiantes|postulantes|ciudadan[oa]s?(?:/[oa]s?)?)\s+ecuatorian[oa]s?(?:/[oa]s?)?\b|'
        r'\bciudadan[oa]s?\s+del\s+ecuador\b|\bnacionalidad\s+ecuatoriana\b|'
        r'\bcedula\s+de\s+ciudadania\s+ecuatoriana\b|'
        r'\becuatorian[oa]s?\s+(?:pueden|podran|deben)\s+postular\b', scope
    ) else 'no_especificada'
    if offerer == 'solo_extranjero':
        return result('fuera_alcance', offerer_reason, elegibilidad=recipient, **details)
    national_siau = adapter == 'siau' and bool(re.search(r'\bbecas?\s+nacionales?\b', _normal(title)))
    if allow_partial and offerer != 'verificado_ec' and not national_siau:
        return result('pendiente', 'La ficha parcial no acredita un oferente o cooferente ecuatoriano.',
                      elegibilidad=recipient, **details)
    if adapter == 'siau' and not re.search(r'\bbecas?\s+nacionales?\b', _normal(title)) and offerer != 'verificado_ec':
        return result('pendiente', 'Ficha difundida por SIAU sin evidencia de oferente o cooferente ecuatoriano; revisar procedencia.',
                      elegibilidad=recipient, **details)
    if offerer != 'verificado_ec' and recipient != 'confirmada':
        if national_siau:
            return result('apta', 'Borrador privado de beca nacional; oferente y destinatarios pendientes de revisión.',
                          elegibilidad=recipient, **details)
        return result('pendiente', offerer_reason, elegibilidad=recipient, **details)
    if offerer != 'verificado_ec':
        return result('apta', 'Borrador privado: destinatarios ecuatorianos acreditados; oferente no identificado.',
                      elegibilidad=recipient, **details)
    return result('apta', 'Borrador privado sujeto a revisión editorial y confirmación de destinatarios.'
                  if recipient == 'no_especificada' else 'Borrador privado con oferente ecuatoriano y destinatarios acreditados en la ficha.',
                  elegibilidad=recipient, **details)


def pending_for_publication(offer, origin):
    """Único control propio del origen: el enlace oficial debe apuntar a una fuente pública.

    La entidad oferente ecuatoriana, el título, la descripción, el enlace y la opción activa los exige
    convocatorias.services.errores_publicacion; la ficha, su versión y el alcance dejan de bloquear:
    publicar es la confirmación del administrador (queda en el Evento de confirmación).
    """
    errors = []
    if offer.url_oficial:
        from convocatorias.serializers import safe_url
        from rest_framework import serializers
        try:
            safe_url(offer.url_oficial)
            host = urlsplit(offer.url_oficial).hostname or ''
            if not host or host.endswith(('.local', '.localhost', '.test')):
                errors.append('El enlace oficial no apunta a una fuente pública verificable.')
        except serializers.ValidationError:
            errors.append('El enlace oficial no es una URL HTTP/HTTPS válida.')
    return errors


def review_notes(offer, origin):
    """Datos complementarios visibles sin impedir conservar una beca verificable."""
    notes = []
    if not offer.institucion_id:
        notes.append('Oferente no identificado; SIAU es fuente, no oferente por defecto.')
    if not offer.cierre and not offer.cierre_dia:
        notes.append('Vigencia por verificar; fuera de las oportunidades abiertas y recomendaciones.')
    elif (offer.cierre and offer.cierre <= timezone.now()) or (offer.cierre_dia and offer.cierre_dia < timezone.localdate()):
        notes.append('Convocatoria cerrada; solo consulta histórica.')
    if origin.version.manifiesto.get('pendientes'):
        notes.append('Documentos de bases pendientes; consultar evidencia conservada.')
    if origin.datos_iniciales.get('requisitos_originales') and not offer.requisitos.filter(activo=True).exists():
        notes.append('Requisitos extraídos aún no estructurados; compatibilidad no confirmada.')
    return notes
