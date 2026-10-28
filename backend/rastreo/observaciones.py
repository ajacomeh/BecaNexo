"""Identidad y observaciones técnicas; nunca escribe en el catálogo."""
import copy
import hashlib
import json
from datetime import date
from urllib.parse import urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from convocatorias.siau_extraccion import validate_observation
from .models import Publicacion, Version, VersionDocumento, Observacion, Ejecucion

NORMALIZADOR = 'urls-cerradas/1'
CONTRATO = 1


def normalize_url(value):
    parts = urlsplit(value)
    # El adaptador actual no necesita queries: no conservar tokens ni ampliar acceso.
    if parts.scheme.lower() != 'https' or not parts.hostname or parts.username or parts.password or parts.query or any(c.isspace() for c in value):
        raise ValidationError('URL fuera del contrato público sin credenciales ni parámetros.')
    host = parts.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    if parts.port not in (None, 443):
        host += ':' + str(parts.port)
    normalized = urlunsplit(('https', host, parts.path, '', ''))
    if len(normalized.encode('utf-8')) > 2048:
        raise ValidationError('URL excede 2048 bytes; no truncar.')
    return normalized


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def identity(execution, url):
    normalized = normalize_url(url)
    now = timezone.now()
    return Publicacion.objects.get_or_create(fuente_id=execution.fuente_id, url_normalizada=normalized,
        defaults={'url_original': url, 'normalizacion_version': NORMALIZADOR,
                  'primera_deteccion': now, 'ultima_deteccion': now})[0]


def technical_content(item, pending):
    data = copy.deepcopy(item)
    # Fecha mínima fija: obtiene advertencias estructurales sin vigencia del reloj.
    validate_observation(data, date.min)
    for key in ('consulta_utc', 'sha256', 'version_extractor', 'vigencia_observada'):
        data.pop(key, None)
    warnings = data.pop('advertencias')
    if pending:
        warnings.append('Bases pendientes de obtención: evidencia incompleta.')
    text = data.pop('texto_ficha', None)
    return data, text, warnings


@transaction.atomic
def observe(execution, publication, item=None, evidence=(), pending=(), detail=None):
    """Transacción corta: bloquea identidad, confirma versión+relaciones+observación."""
    publication = Publicacion.objects.select_for_update().get(pk=publication.pk)
    current = Ejecucion.objects.select_for_update().get(pk=execution.pk)
    if current.fuente_id != publication.fuente_id or current.estado != 'en_curso':
        raise ValidationError('Observación requiere ejecución activa de la misma fuente.')
    previous = Observacion.objects.filter(ejecucion=current, publicacion=publication).first()
    if previous:
        return previous  # Una sola confirmación por ejecución/publicación.
    version = None
    created = False
    result = 'fallo'
    if item is not None:
        # Conjunto por rol+URL; un documento puede respaldar distintas identidades.
        unique = {}
        for entry in evidence:
            value = {**entry, 'url': normalize_url(entry['url'])}
            key = (value['rol'], value['url'])
            if key in unique and unique[key]['documento'].pk != value['documento'].pk:
                raise ValidationError('Dos documentos distintos para una misma URL en la observación.')
            unique[key] = value
        entries = sorted(unique.values(), key=lambda x: (x['rol'], x['url']))
        manifest = {'documentos': [{'rol': e['rol'], 'url': e['url'], 'sha256': e['documento'].sha256} for e in entries],
                    'pendientes': sorted(pending, key=lambda x: (x['url'], x['estado']))}
        data, text, warnings = technical_content(item, pending)
        relevant_hash = digest({'datos': data, 'texto': text, 'advertencias': warnings})
        version_key = dict(publicacion=publication, hash_manifiesto=digest(manifest),
            version_extractor=current.version_extractor, version_normalizador=current.version_normalizador, version_contrato=CONTRATO)
        version = Version.objects.filter(**version_key).first()
        last = publication.observaciones.exclude(version=None).select_related('version').order_by('-id').first()
        if version is None:
            number = (publication.versiones.aggregate(n=Max('numero'))['n'] or 0) + 1
            version = Version.objects.create(**version_key, numero=number, manifiesto=manifest,
                hash_contenido_relevante=relevant_hash, datos_extraidos=data, texto_extraido=text, advertencias=warnings,
                estado_extraccion='completa' if item['seccion_completa'] and not pending else 'parcial')
            VersionDocumento.objects.bulk_create([VersionDocumento(version=version, documento=e['documento'],
                rol=e['rol'], url_original=e.get('url_original', e['url']), url_normalizada=e['url'],
                localizador=e.get('localizador')) for e in entries])
            created = True
        elif version.hash_contenido_relevante != relevant_hash or version.manifiesto != manifest:
            raise ValidationError('Extracción no determinista: cambiar versión del extractor/contrato antes de reutilizar.')
        if last is None:
            result = 'nueva'
        elif last.version_id == version.pk:
            result = 'sin_cambios'
        else:
            def pdfs(v):
                return [e for e in v.manifiesto['documentos'] if e['rol'] != 'ficha_html']
            result = 'cambio_relevante' if last.version.hash_contenido_relevante != relevant_hash or pdfs(last.version) != pdfs(version) else 'cambio_bytes'
        Publicacion.objects.filter(pk=publication.pk).update(ultima_deteccion=timezone.now())
    observation = Observacion.objects.create(ejecucion=current, publicacion=publication, version=version, resultado=result, detalle=detail)
    Ejecucion.objects.filter(pk=current.pk).update(publicaciones_observadas=F('publicaciones_observadas') + 1,
        versiones_nuevas=F('versiones_nuevas') + int(created),
        observaciones_sin_cambios=F('observaciones_sin_cambios') + int(result == 'sin_cambios'))
    return observation


def differences(first, second):
    if first.publicacion_id != second.publicacion_id:
        raise ValidationError('Las versiones deben pertenecer a la misma publicación.')
    fields = sorted(set(first.datos_extraidos) | set(second.datos_extraidos))
    changes = {k: {'antes': first.datos_extraidos.get(k), 'despues': second.datos_extraidos.get(k)}
               for k in fields if first.datos_extraidos.get(k) != second.datos_extraidos.get(k)}
    for key in ('texto_extraido', 'advertencias'):
        if getattr(first, key) != getattr(second, key):
            changes[key] = {'antes': getattr(first, key), 'despues': getattr(second, key)}
    return {'version_desde': first.pk, 'version_hasta': second.pk,
            'contenido_relevante_igual': first.hash_contenido_relevante == second.hash_contenido_relevante,
            'cambios': changes, 'manifiesto_antes': first.manifiesto, 'manifiesto_despues': second.manifiesto,
            'extractor_antes': first.version_extractor, 'extractor_despues': second.version_extractor}
