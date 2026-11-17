"""Ventanas independientes para la captura extraordinaria, cerrada por defecto."""
import json
from datetime import datetime, timedelta, time, timezone as utc_timezone

from django.conf import settings
from django.utils import timezone

from .models import Acceso, Ejecucion, Incidencia
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


def source_blocked(source):
    # Respuestas de reducción de frecuencia quedan bloqueadas hasta revisión
    # administrativa o una captura programada posterior sin tales respuestas.
    # Sin una confirmación externa, una espera indefinida es más segura que
    # interpretar un Retry-After desconocido como cinco minutos.
    last = Ejecucion.objects.filter(fuente=source).exclude(estado='omitida').order_by('-inicio', '-id').first()
    return bool(last and Acceso.objects.filter(ejecucion=last, http_status__in=(429, 503)).exists())


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
