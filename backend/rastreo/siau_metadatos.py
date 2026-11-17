"""Vista previa acotada de metadatos del índice SIAU, sin conservar HTML ni PDF.

Una tarjeta del índice acredita un enlace y su título, no la vigencia, el
oferente, los requisitos ni la aptitud editorial de la beca.
"""
import hashlib
import json
from datetime import timedelta
from urllib.robotparser import RobotFileParser

from convocatorias.siau_red import (AGENT, INDEX, NATIONAL_INDEX, ROBOTS, Downloader,
                                    AccessError, SourceBackoff, retry_after_at)
from .descubrimiento import MAX_FICHAS, NationalIndexLinks
from .siau_ajax import AJAX_INDEX, MAX_INDEX_PAGES, ajax_request, grid_config, robots_allowed, robots_allow_ajax


class MetadataBackoff(SourceBackoff):
    """Respuesta de reducción de frecuencia, sin reintentar ni visitar más rutas."""

    def __init__(self, status, headers):
        self.status = status
        self.retry_after = (headers.get('retry-after') or '').strip()[:128]
        self.retry_at = retry_after_at(headers)
        super().__init__(f'HTTP {status}; reducir accesos a la fuente.')


def _cards(content, page, origin, method):
    parser = NationalIndexLinks(include_all_becas=True)
    parser.feed(content.decode('utf-8-sig'))
    if not parser.article_count:
        raise AccessError('Índice sin tarjetas reconocibles.')
    digest = hashlib.sha256(content).hexdigest()
    return [{**entry, 'pagina': page, 'origen': origin, 'metodo': method,
             'respuesta_sha256': digest, 'estado': 'pendiente',
             'motivo': 'Solo se verificó la tarjeta del índice; faltan ficha, vigencia, oferente y requisitos.'}
            for entry in parser.entries]


def report(index_content, ajax_content=None, *, ajax_page=2, known_urls=(), max_pages=2, limit=MAX_FICHAS):
    """Construye datos factuales mínimos; jamás infiere una convocatoria abierta."""
    first = _cards(index_content, 1, NATIONAL_INDEX, 'GET')
    second = _cards(ajax_content, ajax_page, AJAX_INDEX, 'POST') if ajax_content is not None else []
    # Reparte el presupuesto entre ambas páginas; no privilegia cientos de
    # tarjetas de la primera página a costa de la segunda.
    if not 1 <= limit <= MAX_FICHAS:
        raise ValueError('Presupuesto de candidatos fuera del límite auditado.')
    known = set(known_urls)
    half = limit // 2
    fresh_first = [entry for entry in first if entry['url'] not in known]
    fresh_second = [entry for entry in second if entry['url'] not in known]
    selected = fresh_first[:half] + fresh_second[:half] + fresh_first[half:] + fresh_second[half:]
    unique = {}
    for entry in selected:
        unique.setdefault(entry['url'], entry)
        if len(unique) == limit:
            break
    all_unique = {entry['url'] for entry in first + second}
    return {'candidatos': list(unique.values()), 'tarjetas_reconocidas': len(first) + len(second),
            'duplicados_conocidos': len(all_unique & known), 'pagina_ajax': ajax_page if ajax_content is not None else None,
            'limite_fichas': limit, 'cobertura_parcial': max_pages > 2 or len(all_unique - known) > len(unique),
            'contenido_conservado': False, 'documentos_descargados': 0,
            'borradores_creados': 0, 'publicacion_automatica': False}


def consultar_una_vez(previous_page=None, known_urls=(), limit=MAX_FICHAS):
    """Consulta pública explícita, sin escribir base de datos ni archivos."""
    client = Downloader(allowed_urls={ROBOTS, INDEX, NATIONAL_INDEX, AJAX_INDEX})
    status, headers, robots = client.once(ROBOTS)
    if status in (429, 503):
        raise MetadataBackoff(status, headers)
    if status != 200 or headers.get('content-type', '').split(';')[0].lower() != 'text/plain':
        raise AccessError('robots.txt no verificable.')
    if not all(robots_allowed(robots, url) for url in (INDEX, NATIONAL_INDEX)) or not robots_allow_ajax(robots):
        raise AccessError('robots.txt restringe el índice o AJAX.')
    parser = RobotFileParser(ROBOTS)
    parser.parse(robots.decode('utf-8-sig').splitlines())
    delay = parser.crawl_delay(AGENT) or 0
    if delay > 60:
        raise AccessError('crawl-delay excede el presupuesto admitido.')
    client.pause = max(client.pause, delay)
    status, headers, first = client.once(NATIONAL_INDEX)
    if status in (429, 503):
        raise MetadataBackoff(status, headers)
    if status != 200 or headers.get('content-type', '').split(';')[0].lower() != 'text/html':
        raise AccessError('Índice nacional no verificable; no continuar.')
    config = grid_config(first)
    second = None
    page = None
    if config['max_num_pages'] > 1:
        maximum = min(config['max_num_pages'], MAX_INDEX_PAGES)
        page = previous_page + 1 if previous_page and 2 <= previous_page < maximum else 2
        body, _public_parameters = ajax_request(config, page)
        status, headers, second = client.post_once(AJAX_INDEX, body)
        if status in (429, 503):
            raise MetadataBackoff(status, headers)
        if status != 200 or headers.get('content-type', '').split(';')[0].lower() != 'text/html':
            raise AccessError('Página AJAX no verificable; no conservar resultados parciales.')
    return report(first, second, ajax_page=page, known_urls=known_urls,
                  max_pages=config['max_num_pages'], limit=limit)


def last_completed_page(source):
    """Recupera la última página AJAX completada; los fallos no avanzan el cursor."""
    from .models import CandidatoIndice, Ejecucion, Incidencia
    completed = Ejecucion.objects.filter(fuente=source, version_extractor='siau-index-meta/1',
                                        estado__in=('finalizada', 'parcial')).order_by('-fin', '-pk').first()
    if not completed:
        return None
    detail = Incidencia.objects.filter(ejecucion=completed, codigo='METADATOS_INDICE').values_list('detalle', flat=True).first()
    if detail:
        try:
            page = json.loads(detail).get('pagina_ajax')
            if type(page) is int and 2 <= page <= MAX_INDEX_PAGES:
                return page
        except (ValueError, TypeError, AttributeError):
            pass
    # Compatibilidad con la primera captura, anterior al cursor explícito.
    return CandidatoIndice.objects.filter(ultima_ejecucion=completed, pagina__gte=2).order_by('-pagina').values_list('pagina', flat=True).first()


def capturar_metadatos(source_id, actor_id, key, reason):
    """Una ejecución auditada, sin fichas, versiones, documentos ni borradores."""
    import uuid
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.utils import timezone
    from .models import CandidatoIndice, Ejecucion, Fuente, Incidencia
    from .services import actor_admin, exclusion, next_due, snapshot, NATIONAL_POLICY
    from .web_frequency import source_blocked

    actor = actor_admin(actor_id)
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError('Motivo obligatorio para la consulta limitada.')
    key = uuid.UUID(str(key))
    previous = Ejecucion.objects.filter(clave_idempotencia=key).first()
    if previous:
        if previous.fuente_id != source_id or previous.solicitado_por_id != actor.pk or previous.version_extractor != 'siau-index-meta/1':
            raise ValidationError('Clave idempotente pertenece a otra operación.')
        return previous
    with exclusion(source_id) as locked:
        if not locked:
            raise ValidationError('Existe otra ejecución del rastreador.')
        with transaction.atomic():
            source = Fuente.objects.select_for_update().get(pk=source_id)
            if (source.adaptador != 'siau' or source.politica_version != 'siau-nacionales/3'
                    or source.politica_acceso != NATIONAL_POLICY or not source.activa
                    or source.aprobada_publicacion_automatica):
                raise ValidationError('La fuente SIAU debe conservar la política /3 sin publicación automática.')
            if Ejecucion.objects.filter(fuente=source, estado='en_curso').exists():
                raise ValidationError('Existe una ejecución pendiente de recuperación.')
            if source_blocked(source):
                raise ValidationError('Fuente bloqueada por HTTP 429/503; requiere revisión antes de continuar.')
            due = next_due(source)
            if due and due > timezone.now():
                raise ValidationError('Aún no corresponde otra consulta SIAU.')
            previous_page = last_completed_page(source)
            known_urls = set(CandidatoIndice.objects.filter(fuente=source).values_list('url_normalizada', flat=True))
            limit = min(MAX_FICHAS, source.politica_acceso['descubrimiento']['max_fichas'])
            configuration = snapshot(source.pk)
            configuration['consulta_limitada'] = {'modo': 'metadatos_indice/4', 'motivo': reason.strip()[:500],
                                                  'pagina_previa': previous_page, 'limite_candidatos': limit}
            execution = Ejecucion.objects.create(
                fuente=source, solicitado_por=actor, origen='manual', clave_idempotencia=key,
                configuracion_snapshot=configuration, version_extractor='siau-index-meta/1')
        try:
            result = consultar_una_vez(previous_page, known_urls, limit)
            now = timezone.now()
            with transaction.atomic():
                for item in result['candidatos']:
                    CandidatoIndice.objects.get_or_create(
                        fuente=source, url_normalizada=item['url'],
                        defaults={'titulo_publico': item['titulo'], 'pagina': item['pagina'],
                                  'respuesta_sha256': item['respuesta_sha256'],
                                  'ultima_ejecucion': execution, 'primera_deteccion': now,
                                  'ultima_deteccion': now})
                Incidencia.objects.create(fuente=source, ejecucion=execution, codigo='METADATOS_INDICE',
                    gravedad='aviso', detalle=json.dumps({
                        'pagina_ajax': result['pagina_ajax'], 'tarjetas': result['tarjetas_reconocidas'],
                        'candidatos_nuevos': len(result['candidatos']),
                        'duplicados_conocidos': result['duplicados_conocidos'],
                        'cobertura_parcial': result['cobertura_parcial'],
                        'contenido_conservado': False, 'documentos_descargados': 0}, sort_keys=True))
                Ejecucion.objects.filter(pk=execution.pk).update(
                    estado='parcial' if result['cobertura_parcial'] else 'finalizada', fin=now)
        except Exception as exc:
            with transaction.atomic():
                detail = {'error': type(exc).__name__}
                summary = type(exc).__name__
                if isinstance(exc, MetadataBackoff):
                    retry_due = max(execution.inicio + timedelta(minutes=source.frecuencia_min),
                                    exc.retry_at or execution.inicio)
                    detail.update(http_status=exc.status, retry_after=exc.retry_after or None,
                                  proximo_intento=retry_due.isoformat())
                    summary = f'HTTP {exc.status}'
                    Incidencia.objects.create(fuente=source, ejecucion=execution, codigo='REINTENTO_FUENTE',
                                              gravedad='aviso', detalle=retry_due.isoformat())
                Incidencia.objects.create(fuente=source, ejecucion=execution, codigo='METADATOS_FALLIDOS',
                    gravedad='error', detalle=json.dumps(detail, sort_keys=True))
                Ejecucion.objects.filter(pk=execution.pk).update(
                    estado='fallida', fin=timezone.now(), error_resumen=summary)
            raise
        return execution
