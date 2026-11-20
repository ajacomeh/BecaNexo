"""Ventanas independientes para la captura extraordinaria, cerrada por defecto."""
import json
import uuid
from datetime import datetime, timedelta, time, timezone as utc_timezone

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from .models import Acceso, Ejecucion, Fuente, Incidencia, Revision
from .web_launch import launch_root


MANUAL_INTERVAL = timedelta(seconds=300)
MAX_DAILY = 3


def extraordinary_enabled():
    # Una opción del navegador jamás habilita esta excepción.
    return bool(getattr(settings, 'RASTREO_EXTRAORDINARIO_HABILITADO', False))


def accepted_path(source_id, key):
    return launch_root() / f'solicitud-{source_id}-{key}.json'


def acceptances(source_id, exclude_key=None):
    values = []
    for path in launch_root().glob(f'solicitud-{source_id}-*.json') if launch_root().exists() else ():
        if exclude_key and path.name == f'solicitud-{source_id}-{exclude_key}.json':
            continue
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            accepted = datetime.fromisoformat(value['aceptada_en'])
            if not timezone.is_aware(accepted):
                raise ValueError('Fecha sin zona horaria.')
            values.append(accepted)
        except (OSError, ValueError, KeyError, TypeError):
            # Un registro dañado exige revisión; el llamador no debe abrir la ventana.
            raise ValueError('Registro de solicitudes manuales ilegible.') from None
    return values


def global_due(source):
    last = Ejecucion.objects.filter(fuente=source).exclude(estado='omitida').order_by('-inicio', '-id').first()
    return last.inicio + MANUAL_INTERVAL if last else None


def source_retry_due(source):
    dates = []
    values = Incidencia.objects.filter(fuente=source, codigo='REINTENTO_FUENTE')
    for raw in values.values_list('detalle', flat=True):
        value = datetime.fromisoformat(raw)
        if not timezone.is_aware(value):
            raise ValueError('Espera de la fuente sin zona horaria.')
        dates.append(value)
    return max(dates, default=None)


UNLOCK_ACTION = 'desbloqueo_http_429_503'


def blocking_access(source):
    """Primer acceso 429/503 de la última ejecución no omitida, o None."""
    last = Ejecucion.objects.filter(fuente=source).exclude(estado='omitida').order_by('-inicio', '-id').first()
    if not last:
        return None
    return Acceso.objects.filter(ejecucion=last, http_status__in=(429, 503)).order_by('secuencia', 'id').first()


def unlock_record(source, access):
    return Revision.objects.filter(fuente=source, dimension='configuracion', decision='aplicada',
                                   detalle__accion=UNLOCK_ACTION,
                                   detalle__ejecucion_id=access.ejecucion_id).order_by('-id').first()


def source_blocked(source):
    # Una respuesta 429/503 bloquea la fuente de forma indefinida hasta que un
    # administrador la revise y la desbloquee con motivo (unlock_source). Sin una
    # confirmación externa, esperar es más seguro que interpretar un Retry-After
    # desconocido. El desbloqueo no anula Retry-After ni la frecuencia (next_due).
    access = blocking_access(source)
    return bool(access and not unlock_record(source, access))


def block_details(source):
    access = blocking_access(source)
    if not access or unlock_record(source, access):
        return None
    retry = source_retry_due(source)
    return {'fuente_id': source.pk, 'fuente_nombre': source.nombre, 'http_status': access.http_status,
            'bloqueado_en': access.fin, 'ejecucion_id': access.ejecucion_id,
            'reintento_desde': retry}


@transaction.atomic
def unlock_source(source_id, actor_id, reason, key):
    """Levanta, con auditoría, el bloqueo indefinido por HTTP 429/503 de una fuente."""
    from .services import actor_admin
    actor = actor_admin(actor_id)
    reason = reason.strip() if isinstance(reason, str) else ''
    if not 10 <= len(reason) <= 500 or not reason.isprintable():
        raise ValidationError('Indica un motivo administrativo entre 10 y 500 caracteres.')
    try:
        key = uuid.UUID(str(key))
    except ValueError:
        raise ValidationError('Clave de acción inválida.') from None
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(742600, 3)')
    previous = Revision.objects.filter(clave_accion=key).first()
    if previous:
        if (previous.actor_id != actor.pk or previous.fuente_id != source_id or previous.motivo != reason
                or previous.detalle.get('accion') != UNLOCK_ACTION):
            raise ValidationError('Clave de acción reutilizada con otro contenido.')
        return previous, False
    source = Fuente.objects.select_for_update().get(pk=source_id)
    if Ejecucion.objects.filter(fuente=source, estado='en_curso').exists():
        raise ValidationError('No se desbloquea una fuente con una ejecución en curso.')
    access = blocking_access(source)
    if not access or unlock_record(source, access):
        raise ValidationError('La fuente no está bloqueada por una respuesta HTTP 429/503.')
    retry = source_retry_due(source)
    detail = {'accion': UNLOCK_ACTION, 'ejecucion_id': access.ejecucion_id, 'acceso_id': access.pk,
              'http_status': access.http_status, 'bloqueado_en': access.fin.isoformat(),
              'url': access.url_normalizada, 'reintento_desde': retry.isoformat() if retry else None}
    row = Revision.objects.create(actor=actor, fuente=source, dimension='configuracion', decision='aplicada',
                                  motivo=reason, detalle=detail, clave_accion=key)
    return row, True


def manual_window(source, exclude_key=None):
    from .services import next_due
    accepted = acceptances(source.pk, exclude_key)
    latest = max(accepted) if accepted else None
    today = timezone.now().astimezone(utc_timezone.utc).date()
    daily = sum(value.astimezone(utc_timezone.utc).date() == today for value in accepted)
    daily_limit = (datetime.combine(today + timedelta(days=1), time.min, utc_timezone.utc)
                   if daily >= MAX_DAILY else None)
    dates = [date for date in (latest + MANUAL_INTERVAL if latest else None, daily_limit,
                               next_due(source)) if date]
    return max(dates) if dates else None
