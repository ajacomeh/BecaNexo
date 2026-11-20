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


def classify_candidate(publication, version, *, allow_partial=False):
    """Clasificación editorial; pendiente nunca equivale a fuera de alcance."""
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


def candidate_assessment(publication, version):
    assessment = classify_candidate(publication, version)
    return assessment['estado'] == 'apta', (
        assessment['motivo'] if assessment['estado'] != 'apta' or assessment['elegibilidad'] == 'no_especificada' else None)


def editable_candidates(version):
    """Interpreta la evidencia sin escribir ni validar candidatos editoriales."""
    from .estructura_semantica import interpretar_requisitos, candidatos_adicionales
    from .evidencia_tabular import extraer_tablas
    from .evidencia_pdf import MAX_DOCUMENTOS, leer_evidencia_pdf
    from .propuestas_documentales import proponer
    from .storage import StorageError, root_path, verify_file
    data = version.datos_extraidos or {}
    requirements = _literal(data.get('requisitos'), 5000)
    html = version.documentos.filter(rol='ficha_html').select_related('documento').first()
    document_id = html.documento_id if html else None
    suggestions = interpretar_requisitos(requirements, version_id=version.pk,
        url=(data.get('requisitos') or {}).get('url'), documento_id=document_id)
    studies = data.get('estudios') or {}
    level_text = [_normal(str(x)) for x in studies.get('niveles_mencionados', []) if isinstance(x, str)]
    level_map = {'bachillerato': 'bachillerato', 'tercer nivel': 'grado', 'grado': 'grado',
                 'especializacion': 'especializacion', 'maestria': 'maestria', 'doctorado': 'doctorado'}
    levels = {value for mention in level_text for word, value in level_map.items() if word in mention}
    modality_text = _normal(_literal(studies.get('modalidad'), 60))
    modalities = {'presencial': 'presencial', 'virtual': 'virtual', 'en linea': 'virtual',
                  'semipresencial': 'semipresencial', 'hibrida': 'hibrida', 'hibrido': 'hibrida'}
    destination = _literal(studies.get('destino'), 500)
    options = []
    if len(levels) == 1 and modality_text in modalities and destination:
        options.append({'nivel': next(iter(levels)), 'modalidad': modalities[modality_text],
                        'destino_original': destination, 'validado': False,
                        'procedencia': {'version_id': version.pk, 'campos': ['estudios.niveles_mencionados', 'estudios.modalidad', 'estudios.destino']}})
    fields = candidatos_adicionales(data, version_id=version.pk, documento_id=document_id)
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
    return {'requisitos': suggestions, 'opciones': options, 'otros_campos': fields}


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
    title = _literal(data.get('titulo'), 250)
    description = _literal(data.get('descripcion'), 15000)
    closure_original = _literal(data.get('cierre'), 500)
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
    requirements = _literal(data.get('requisitos'), 5000)
    pending = []
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
                'beneficio_original': _literal(data.get('beneficio'), 5000),
                'url_publicacion': publication.url_original,
                'candidatos_editables': editable_candidates(version),
                'clasificacion_inicial': assessment}
    identity = hashlib.sha256(f'rastreo:{publication.pk}'.encode()).hexdigest()
    offer = Convocatoria.objects.create(institucion=None, titulo=title, descripcion=description,
        cierre_original=closure_original or None, cierre_dia=closure_day, url_oficial='',
        clave_deduplicacion=identity, revision='pendiente', activa=True)
    origin = BorradorRastreo.objects.create(publicacion=publication, convocatoria=offer, version=version,
        datos_iniciales=snapshot, pendientes_iniciales=pending)
    publication.convocatoria = offer
    publication.save(update_fields=['convocatoria'])
    return origin, True, assessment['motivo'] if assessment['elegibilidad'] == 'no_especificada' else None


def pending_for_publication(offer, origin):
    """Solo bloqueos materiales de procedencia, alcance y revisión vigente."""
    errors = []
    if not offer.institucion_id:
        errors.append('Asigna una institución oferente ecuatoriana antes de publicar.')
    if origin.publicacion.convocatoria_id != offer.pk or origin.version.publicacion_id != origin.publicacion_id:
        errors.append('La procedencia del borrador no coincide con la publicación rastreada.')
    if not origin.version.documentos.filter(rol='ficha_html').exists():
        errors.append('No existe ficha HTML preservada para verificar la fuente.')
    current = latest_version(origin.publicacion)
    assessment = classify_candidate(origin.publicacion, current) if current else None
    if not assessment or assessment['estado'] != 'apta':
        errors.append('La ficha vigente no acredita una beca dentro del alcance.')
    if not assessment or assessment['elegibilidad'] != 'confirmada':
        errors.append('La participación ecuatoriana no está acreditada; no se presume cumplida.')
    if current and materially_changed(review_baseline(origin, offer), current) and not version_confirmed(offer, current):
        errors.append(f'La versión {current.pk} tiene cambios relevantes; confirma su revisión antes de publicar.')
    if offer.url_oficial:
        from convocatorias.serializers import safe_url
        from rest_framework import serializers
        try:
            safe_url(offer.url_oficial)
            host = urlsplit(offer.url_oficial).hostname or ''
            if not host or host.endswith(('.local', '.localhost', '.test')):
                errors.append('El enlace oficial no apunta a una fuente pública verificable.')
            if not offer.institucion_id:
                evidence = (current.datos_extraidos or {}) if current else {}
                urls = {origin.publicacion.url_original}
                for key in ('enlaces_bases', 'enlaces_postulacion'):
                    urls.update(row.get('url') for row in evidence.get(key, []) if isinstance(row, dict))
                if offer.url_oficial not in urls:
                    errors.append('Sin oferente identificado, el enlace debe constar en la evidencia de origen.')
        except serializers.ValidationError:
            errors.append('El enlace oficial no es una URL HTTP/HTTPS válida.')
    from .precarga import bloqueo_publicacion
    pending_preload = bloqueo_publicacion(offer)
    if pending_preload:
        errors.append(pending_preload)
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
