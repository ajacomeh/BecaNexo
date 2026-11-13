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


def candidate_assessment(publication, version):
    data = version.datos_extraidos or {}
    title = _literal(data.get('titulo'), 250)
    adapter = publication.fuente.adaptador
    if adapter == 'siau':
        if not re.search(r'\bbecas?\s+nacionales?\b', _normal(title)):
            return False, None
    elif adapter.startswith('portal_ec:'):
        from .portal_fuentes import portal_for_source, admitted_url
        try:
            portal = portal_for_source(publication.fuente)
        except Exception:
            return False, 'Fuente institucional sin política auditada.'
        section_base = publication.url_original if portal.generico else portal.indice
        section_identity = (portal.secciones_en_indice and (portal.generico or publication.url_original == portal.indice)
                            and re.fullmatch(re.escape(section_base) + r'#becanexo-[0-9a-f]{20}', publication.url_normalizada))
        if not (section_identity or admitted_url(portal, publication.url_normalizada)) or not re.search(r'\bbecas?\b', _normal(title)):
            return False, 'No se confirmó una ficha de beca del portal institucional.'
        if portal.generico and data.get('vigencia_al_consultar') == 'vencida':
            return False, 'Cierre vencido; conservar evidencia sin crear un borrador nuevo.'
        if not (data.get('cierre') or {}).get('fecha'):
            return False, 'Fecha de cierre de la ficha institucional pendiente de verificación.'
        if Version.objects.filter(datos_extraidos__titulo__texto_original=title,
                                  datos_extraidos__cierre__fecha=data['cierre']['fecha'],
                                  publicacion__fuente__adaptador__startswith='portal_ec:').exclude(publicacion=publication).exists():
            return False, 'Título y cierre coinciden con otra fuente; revisión de posible duplicado.'
    else:
        return False, None
    if data.get('seccion_completa') is not True or not version.documentos.filter(rol='ficha_html').exists():
        return False, 'Ficha nacional sin evidencia HTML completa.'
    if not _literal(data.get('requisitos'), 5000) or not _literal(data.get('cierre'), 500):
        return False, 'No se verificaron requisitos y cierre de la oportunidad.'
    scope = ' '.join(_normal(_literal(data.get(key), 15000)) for key in ('descripcion', 'requisitos', 'postulacion_y_documentos'))
    if not re.search(r'\b(ecuatorian[oa]s?|ciudadan[oa]s?\s+del\s+ecuador)\b', scope):
        return False, 'No se identificó evidencia explícita de destinatarios ecuatorianos.'
    return True, None


def _candidate(publication, version):
    return candidate_assessment(publication, version)[0]


def latest_version(publication):
    observed = Observacion.objects.filter(publicacion=publication, version__isnull=False).select_related('version').order_by('-id').first()
    return observed.version if observed else None


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
def prepare_automatic_draft(publication_id, version_id):
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
    admitted, reason = candidate_assessment(publication, version)
    if not admitted:
        return None, False, reason
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
    requirements = _literal(data.get('requisitos'), 5000)
    pending = []
    pending.append('Identificar y confirmar entidad oferente ecuatoriana.')
    if not description: pending.append('Completar descripción respaldada.')
    if not closure_day: pending.append('Verificar vigencia y fecha de cierre.')
    if requirements: pending.append('Estructurar y revisar requisitos extraídos.')
    pending.extend(['Confirmar enlace oficial de consulta o postulación.',
                    'Registrar y revisar al menos una opción de estudio.'])
    if version.manifiesto.get('pendientes'):
        pending.append('Resolver documentos de bases pendientes.')
    snapshot = {'titulo': title, 'descripcion': description, 'cierre_original': closure_original,
                'cierre_dia_interpretado': closure_day.isoformat() if closure_day else None,
                'entidad_mencionada': _literal(data.get('entidad_html'), 200),
                'entidad_sugerida': {'id': institution_suggestion.pk, 'nombre': institution_suggestion.nombre} if institution_suggestion else None,
                'requisitos_originales': requirements,
                'modalidad_mencionada': _literal((data.get('estudios') or {}).get('modalidad'), 60),
                'destino_mencionado': _literal((data.get('estudios') or {}).get('destino'), 500),
                'beneficio_original': _literal(data.get('beneficio'), 5000),
                'url_publicacion': publication.url_original}
    identity = hashlib.sha256(f'rastreo:{publication.pk}'.encode()).hexdigest()
    offer = Convocatoria.objects.create(institucion=None, titulo=title, descripcion=description,
        cierre_original=closure_original or None, cierre_dia=closure_day, url_oficial='',
        clave_deduplicacion=identity, revision='pendiente', activa=True)
    origin = BorradorRastreo.objects.create(publicacion=publication, convocatoria=offer, version=version,
        datos_iniciales=snapshot, pendientes_iniciales=pending)
    publication.convocatoria = offer
    publication.save(update_fields=['convocatoria'])
    return origin, True, None


def pending_for_publication(offer, origin):
    """Bloqueos específicos del borrador automático, revaluados tras cada edición."""
    errors = []
    if origin.publicacion.convocatoria_id != offer.pk or origin.version.publicacion_id != origin.publicacion_id:
        errors.append('La procedencia del borrador no coincide con la publicación rastreada.')
    if not origin.version.documentos.filter(rol='ficha_html').exists():
        errors.append('No existe ficha HTML preservada para verificar la fuente.')
    if origin.version.manifiesto.get('pendientes'):
        errors.append('Persisten documentos de bases pendientes; revisa la evidencia antes de publicar.')
    current = latest_version(origin.publicacion)
    if materially_changed(review_baseline(origin, offer), current) and not version_confirmed(offer, current):
        errors.append(f'La versión {current.pk} contiene cambios relevantes posteriores al borrador; confirma su revisión antes de publicar.')
    if not offer.cierre and not offer.cierre_dia:
        errors.append('Verifica una fecha de cierre antes de publicar.')
    if offer.cierre and offer.cierre <= timezone.now() or offer.cierre_dia and offer.cierre_dia < timezone.localdate():
        errors.append('La fecha de cierre ya pasó; revisa la vigencia antes de publicar.')
    if origin.datos_iniciales.get('requisitos_originales') and not offer.requisitos.filter(activo=True).exists():
        errors.append('Hay requisitos extraídos que aún no se registraron ni revisaron.')
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
