import uuid
import json
import time
import http.client
from contextlib import contextmanager
from datetime import datetime, timedelta
from urllib.robotparser import RobotFileParser

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, transaction, DatabaseError
from django.utils import timezone

from convocatorias.siau_red import Downloader, AccessError, INDEX, ROBOTS, PAGES, PDFS, ALLOWED, AGENT
from convocatorias.siau_extraccion import EXTRACTOR_VERSION, extract_html
from .models import Fuente, Ejecucion, Acceso, Incidencia, Revision, Publicacion
from .observaciones import identity, observe, normalize_url
from .storage import prepare_document, register_document, StorageError, root_path
from .descubrimiento import BASE, MAX_BASES, MAX_FICHAS, candidate_url, index_pages


BASE_POLICY = {'urls': sorted(ALLOWED), 'bytes_html': 2097152, 'bytes_pdf': 8388608, 'reintentos': 1}
DISCOVERY_POLICY = {**BASE_POLICY, 'descubrimiento': {'indice': INDEX, 'max_fichas': MAX_FICHAS, 'max_bases': MAX_BASES}}


def supported_policy(source):
    return ((source.politica_version == 'siau-cerrada/1' and source.politica_acceso == BASE_POLICY)
            or (source.politica_version == 'siau-indice/2' and source.politica_acceso == DISCOVERY_POLICY))


def actor_admin(actor_id):
    actor = get_user_model().objects.filter(pk=actor_id, is_active=True, rol='administrador').first()
    if actor is None:
        raise ValidationError('Se requiere ID de administrador activo real.')
    return actor


def snapshot(source_id):
    with connection.cursor() as cursor:
        cursor.execute('SELECT to_jsonb(f) FROM "CFG_FUENTE" f WHERE id=%s', [source_id])
        value = cursor.fetchone()[0]
        return json.loads(value) if isinstance(value, str) else value


@transaction.atomic
def configure(actor_id, reason, active=None, key=None):
    actor = actor_admin(actor_id)
    if not reason or not reason.strip():
        raise ValidationError('Motivo obligatorio.')
    key = uuid.UUID(str(key)) if key else uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(742600, 1)')
    previous_action = Revision.objects.filter(clave_accion=key).first()
    if previous_action:
        desired = previous_action.detalle.get('despues', {})
        if previous_action.actor_id != actor.pk or previous_action.motivo != reason.strip() or (active is not None and desired.get('activa') != active):
            raise ValidationError('Clave de acción reutilizada con otro contenido.')
        return previous_action.fuente, False
    source = Fuente.objects.select_for_update().filter(url_base=INDEX).first()
    before = snapshot(source.pk) if source else None
    policy = BASE_POLICY
    if source is None:
        if active is not None:
            raise ValidationError('Primero registre la fuente desactivada.')
        source = Fuente.objects.create(nombre='SIAU', url_base=INDEX, politica_acceso=policy)
    elif source.adaptador != 'siau' or not supported_policy(source) or source.aprobada_publicacion_automatica:
        raise ValidationError('Configuración existente diferente: no sobrescribir.')
    elif active is None or source.activa == active:
        return source, False
    else:
        source.activa = active
        source.save(update_fields=['activa'])
    Revision.objects.create(actor=actor, fuente=source, dimension='configuracion', decision='aplicada',
                            motivo=reason.strip(), detalle={'antes': before, 'despues': snapshot(source.pk)}, clave_accion=key)
    return source, True


@transaction.atomic
def enable_discovery(actor_id, reason, key=None):
    """Amplía el acceso solo con una decisión administrativa auditable."""
    actor = actor_admin(actor_id)
    if not reason or not reason.strip():
        raise ValidationError('Motivo obligatorio.')
    key = uuid.UUID(str(key)) if key else uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(742600, 1)')
    previous = Revision.objects.filter(clave_accion=key).first()
    if previous:
        if (previous.actor_id != actor.pk or previous.motivo != reason.strip()
                or previous.detalle.get('despues', {}).get('politica_version') != 'siau-indice/2'):
            raise ValidationError('Clave de acción reutilizada con otro contenido.')
        return previous.fuente, False
    source = Fuente.objects.select_for_update().get(url_base=INDEX)
    if source.adaptador != 'siau' or not supported_policy(source) or source.aprobada_publicacion_automatica:
        raise ValidationError('Fuente fuera del contrato SIAU.')
    if source.politica_version == 'siau-indice/2':
        return source, False
    if Ejecucion.objects.filter(fuente=source, estado='en_curso').exists():
        raise ValidationError('No cambiar la política durante una ejecución activa.')
    before = snapshot(source.pk)
    source.politica_acceso = DISCOVERY_POLICY
    source.politica_version = 'siau-indice/2'
    source.save(update_fields=['politica_acceso', 'politica_version'])
    Revision.objects.create(actor=actor, fuente=source, dimension='configuracion', decision='aplicada',
                            motivo=reason.strip(), detalle={'antes': before, 'despues': snapshot(source.pk)}, clave_accion=key)
    return source, True


@transaction.atomic
def set_frequency(source_id, actor_id, reason, minutes, key=None):
    actor = actor_admin(actor_id)
    if not reason or not reason.strip() or not isinstance(minutes, int) or not 60 <= minutes <= 10080:
        raise ValidationError('Motivo y frecuencia de 60 a 10080 minutos obligatorios.')
    key = uuid.UUID(str(key)) if key else uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(742600, 1)')
    previous = Revision.objects.filter(clave_accion=key).first()
    if previous:
        if (previous.actor_id != actor.pk or previous.fuente_id != source_id or previous.motivo != reason.strip()
                or previous.detalle.get('despues', {}).get('frecuencia_min') != minutes):
            raise ValidationError('Clave de acción reutilizada con otro contenido.')
        return previous.fuente, False
    source = Fuente.objects.select_for_update().get(pk=source_id)
    if not supported_policy(source) or source.aprobada_publicacion_automatica:
        raise ValidationError('Fuente fuera del contrato SIAU.')
    if source.frecuencia_min == minutes:
        return source, False
    if Ejecucion.objects.filter(fuente=source, estado='en_curso').exists():
        raise ValidationError('No cambiar la frecuencia durante una ejecución activa.')
    before = snapshot(source.pk)
    source.frecuencia_min = minutes
    source.save(update_fields=['frecuencia_min'])
    Revision.objects.create(actor=actor, fuente=source, dimension='configuracion', decision='aplicada',
                            motivo=reason.strip(), detalle={'antes': before, 'despues': snapshot(source.pk)}, clave_accion=key)
    return source, True


@contextmanager
def exclusion(source_id):
    """Sesión PostgreSQL, sin transacción durante HTTP. Orden origen → fuente."""
    if connection.in_atomic_block:
        raise ValidationError('Rastreo requiere autocommit, sin transacción externa.')
    acquired = []
    try:
        for lock in ((742601, 1), (742602, source_id)):
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_try_advisory_lock(%s,%s)', lock)
                success = cursor.fetchone()[0]
            if not success:
                yield False
                return
            acquired.append(lock)
        yield True
    finally:
        for lock in reversed(acquired):
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_unlock(%s,%s)', lock)


def incident(execution, code, detail, access=None, severity='error', publication=None):
    return Incidencia.objects.create(fuente_id=execution.fuente_id, ejecucion=execution, acceso=access,
                                    publicacion_id=access.publicacion_id if access else getattr(publication, 'pk', None),
                                    codigo=code, detalle=detail, gravedad=severity)


class PersistentDownloader(Downloader):
    def __init__(self, execution, source):
        super().__init__(pause=max(2, source.espera_seg), timeout=min(15, source.timeout_seg))
        self.execution = execution
        self.sequence = 0
        self.publication = None
        self.page_url = None
        self.pages = set(PAGES)
        self.pdfs = set(PDFS)

    def record(self, url, record, status, result, document=None, error=None, headers=None):
        self.sequence += 1
        admitted = datetime.fromisoformat(record['consulta_utc'])
        started = datetime.fromisoformat(record['inicio_peticion_utc']) if record.get('inicio_peticion_utc') else None
        finished = timezone.now()
        return Acceso.objects.create(ejecucion=self.execution, secuencia=self.sequence, publicacion=self.publication,
            rol='robots' if url == ROBOTS else 'indice' if url == INDEX else 'bases' if url in self.pdfs else 'ficha',
            url_original=url, url_normalizada=url, url_final=url, admitido_en=admitted,
            inicio_peticion_en=started, fin=max(finished, started or admitted, admitted),
            espera_ms=record.get('espera_ms', 0),
            duracion_ms=max(0, int((time.monotonic() - record['inicio_peticion_monotonic']) * 1000)) if 'inicio_peticion_monotonic' in record else None,
            http_status=status, resultado=result, documento=document, error_codigo=error,
            etag=(headers or {}).get('etag'), last_modified=(headers or {}).get('last-modified'))

    def once(self, url):
        entry = self.history[-1]
        status = None
        try:
            status, headers, content = super().once(url)
        except (AccessError, OSError, ValueError, http.client.HTTPException) as exc:
            access = self.record(url, entry, None, 'error', error=type(exc).__name__)
            incident(self.execution, 'RED', type(exc).__name__, access)
            raise
        if status == 200:
            expected = 'application/pdf' if url in self.pdfs else 'text/plain' if url == ROBOTS else 'text/html'
            mime = headers.get('content-type', '').split(';')[0].strip().lower()
            try:
                if mime != expected:
                    raise StorageError('MIME distinto del recurso esperado.')
                prepared = prepare_document(content, mime)
                with transaction.atomic():
                    document, created = register_document(prepared)
                    if self.page_url and url in self.pages and self.publication is None:
                        self.publication = identity(self.execution, self.page_url)
                    prior = Acceso.objects.filter(url_normalizada=url, documento__isnull=False).order_by('-id').first()
                    access = self.record(url, entry, status, 'descargado' if created else 'reutilizado', document, headers=headers)
                    if url in self.pdfs and prior and prior.documento_id != document.pk:
                        incident(self.execution, 'PDF_CAMBIADO', 'Nueva huella; no hereda revisión previa.', access, 'aviso')
                    if url in self.pdfs:
                        incident(self.execution, 'REVISION_DOCUMENTAL_PENDIENTE', 'Descarga técnica correcta; bases no aprobadas.', access, 'aviso')
            except (StorageError, OSError, DatabaseError) as exc:
                if self.page_url:
                    self.publication = Publicacion.objects.filter(fuente_id=self.execution.fuente_id, url_normalizada=normalize_url(self.page_url)).first()
                access = self.record(url, entry, status, 'error', error=type(exc).__name__)
                incident(self.execution, 'ALMACENAMIENTO', str(exc) if isinstance(exc, StorageError) else type(exc).__name__, access)
                raise AccessError('No se pudo conservar evidencia íntegra.') from exc
        else:
            result = 'redirigido' if status in (301, 302, 303, 307, 308) else 'error'
            access = self.record(url, entry, status, result, error=None if result == 'redirigido' else f'HTTP_{status}')
            if result == 'error':
                incident(self.execution, 'HTTP', f'HTTP {status}; no cancela convocatorias.', access)
        Ejecucion.objects.filter(pk=self.execution.pk).update(latido_en=timezone.now())
        return status, headers, content


def summary(execution):
    execution.refresh_from_db()
    return {'id': execution.pk, 'clave': str(execution.clave_idempotencia), 'estado': execution.estado,
            'accesos': execution.accesos.count(), 'documentos_distintos': execution.accesos.exclude(documento=None).values('documento').distinct().count(),
            'incidencias': list(execution.incidencias.values('id', 'codigo', 'gravedad', 'detalle')),
            'publicaciones_observadas': execution.publicaciones_observadas, 'versiones_nuevas': execution.versiones_nuevas,
            'observaciones_sin_cambios': execution.observaciones_sin_cambios,
            'convocatorias_creadas': 0, 'revision_documental': 'pendiente'}


def run_manual(source_id, actor_id, key):
    actor_admin(actor_id)
    return _run(source_id, actor_id, key, 'manual')


def run_scheduled(source_id, key=None):
    return _run(source_id, None, key or uuid.uuid4(), 'programada')


def next_due(source):
    last = Ejecucion.objects.filter(fuente=source).exclude(estado='omitida').order_by('-inicio').first()
    return last.inicio + timedelta(minutes=source.frecuencia_min) if last else None


def _run(source_id, actor_id, key, origin):
    key = uuid.UUID(str(key))
    existing = Ejecucion.objects.filter(clave_idempotencia=key).first()
    if existing:
        if existing.fuente_id != source_id or existing.solicitado_por_id != actor_id or existing.origen != origin:
            raise ValidationError('Clave idempotente pertenece a otra operación.')
        return existing
    with exclusion(source_id) as locked:
        with transaction.atomic():
            source = Fuente.objects.select_for_update().get(pk=source_id)
            # Serializa creación incluso para invocaciones omitidas.
            existing = Ejecucion.objects.filter(clave_idempotencia=key).first()
            if existing:
                if existing.fuente_id != source_id or existing.solicitado_por_id != actor_id or existing.origen != origin:
                    raise ValidationError('Clave idempotente pertenece a otra operación.')
                return existing
            if origin == 'programada':
                due = next_due(source)
                if due and due > timezone.now():
                    return Ejecucion.objects.filter(fuente=source).exclude(estado='omitida').order_by('-inicio').first()
            reason = None
            if not locked:
                reason = 'Origen o fuente ocupados por otra ejecución.'
            elif not source.activa:
                reason = 'Fuente desactivada.'
            elif Ejecucion.objects.filter(fuente=source, estado='en_curso').exists():
                reason = 'Existe una ejecución pendiente de recuperación explícita.'
            if source.adaptador != 'siau' or source.url_base != INDEX or not supported_policy(source):
                reason = 'Configuración fuera del contrato SIAU cerrado.'
            now = timezone.now()
            execution = Ejecucion.objects.create(fuente=source, solicitado_por_id=actor_id, origen=origin, clave_idempotencia=key,
                configuracion_snapshot=snapshot(source.pk), version_extractor=EXTRACTOR_VERSION,
                inicio=now, estado='omitida' if reason else 'en_curso', fin=now if reason else None, error_resumen=reason)
            if reason:
                incident(execution, 'OMITIDA', reason, severity='aviso')
                return execution
        try:
            root_path()
            downloader = PersistentDownloader(execution, source)
            robots = downloader.fetch(ROBOTS)
            policy = RobotFileParser(ROBOTS)
            policy.parse(robots['contenido'].decode('utf-8-sig').splitlines())
            delay = policy.crawl_delay(AGENT) or 0
            if delay > 60:
                raise AccessError('crawl-delay requiere ejecución con otro presupuesto; detener.')
            downloader.pause = max(downloader.pause, delay)
            def allowed(url):
                return policy.can_fetch(AGENT, url)
            def download(url):
                if not allowed(url):
                    entry = {'consulta_utc': timezone.now().isoformat()}
                    access = downloader.record(url, entry, None, 'bloqueado', error='ROBOTS')
                    incident(execution, 'ROBOTS', 'Ruta bloqueada por robots.', access)
                    raise AccessError('robots bloquea la ruta.')
                return downloader.fetch(url, can_fetch=allowed)
            pages = list(PAGES)
            try:
                index = download(INDEX)
                if source.politica_version == 'siau-indice/2':
                    discovered, truncated = index_pages(index['contenido'])
                    if truncated:
                        incident(execution, 'INDICE_LIMITE', 'El índice supera el máximo de fichas; se requiere revisión.')
                    pages = list(dict.fromkeys([*PAGES, *discovered]))[:MAX_FICHAS]
                    downloader.pages.update(pages)
                    downloader.allowed_urls.update(pages)
            except AccessError:
                pass  # Fichas autorizadas se investigan aunque falle el índice.
            except (UnicodeError, ValueError):
                incident(execution, 'INDICE_ESTRUCTURA', 'Índice no interpretable; se conservan las fichas conocidas.')
            pdf_cache = {}
            for url in pages:
                downloader.page_url = url
                downloader.publication = Publicacion.objects.filter(fuente=source, url_normalizada=normalize_url(url)).first()
                try:
                    page = download(url)
                    item = extract_html(page)
                    publication = downloader.publication
                    if publication is None:
                        raise ValueError('Ficha sin identidad persistida.')
                    html_access = execution.accesos.filter(url_normalizada=page['url'], documento__isnull=False).select_related('documento').latest('id')
                    evidence = [{'rol': 'ficha_html', 'url': url, 'url_original': url, 'documento': html_access.documento}]
                    pending = []
                    if not item['seccion_completa']:
                        incident(execution, 'ESTRUCTURA', 'HTML fuera de contrato; no estructurar automáticamente.', publication=publication)
                    for link in item['enlaces_bases']:
                        candidate = candidate_url(link['url'], BASE) if source.politica_version == 'siau-indice/2' else None
                        if link['url'] not in downloader.pdfs and (not candidate or candidate != link['url'] or len(downloader.pdfs) >= MAX_BASES):
                            pending.append({'url': link['url'], 'estado': 'fuera_de_lista'})
                            incident(execution, 'BASE_NO_PERMITIDA', 'Enlace de bases fuera de lista cerrada.', publication=publication)
                            continue
                        if candidate:
                            downloader.pdfs.add(candidate)
                            downloader.allowed_urls.add(candidate)
                        if link['url'] not in pdf_cache:
                            try:
                                pdf = download(link['url'])
                                pdf_cache[link['url']] = execution.accesos.filter(url_normalizada=pdf['url'], documento__isnull=False).select_related('documento').latest('id').documento
                            except (AccessError, ValueError):
                                pdf_cache[link['url']] = None
                        document = pdf_cache[link['url']]
                        if document is None:
                            pending.append({'url': link['url'], 'estado': 'inaccesible'})
                            incident(execution, 'BASE_INACCESIBLE', 'Evidencia parcial; no se sustituye por un PDF histórico.', publication=publication)
                        else:
                            evidence.append({'rol': 'bases_pdf', 'url': link['url'], 'url_original': link['url_original'], 'documento': document})
                    observe(execution, publication, item, evidence, pending)
                except (AccessError, ValueError, ValidationError) as exc:
                    publication = downloader.publication
                    incident(execution, 'FICHA_INCOMPLETA', type(exc).__name__, publication=publication)
                    if publication:
                        observe(execution, publication, detail='Fallo de ficha; no se fabricó versión.')
            downloader.publication = None
            downloader.page_url = None
            failures = execution.incidencias.filter(gravedad='error').exists()
            state = 'parcial' if failures else 'finalizada'
            if not execution.accesos.filter(documento__isnull=False).exists():
                state = 'fallida'
            Ejecucion.objects.filter(pk=execution.pk).update(estado=state, fin=timezone.now())
        except Exception as exc:
            # Sin mensajes de drivers/paths privados ni credenciales en historial.
            incident(execution, 'EJECUCION_FALLIDA', type(exc).__name__)
            observed_pages = getattr(locals().get('downloader'), 'pages', PAGES)
            for publication in Publicacion.objects.filter(fuente=source, url_normalizada__in=observed_pages):
                observe(execution, publication, detail='Ejecución interrumpida por fallo técnico; sin versión nueva.')
            Ejecucion.objects.filter(pk=execution.pk).update(estado='fallida', fin=timezone.now(), error_resumen=type(exc).__name__)
        # BaseException/interrupción dura deja en_curso; el lock se libera y se recupera explícitamente.
        return execution


def recover(source_id, actor_id, reason):
    actor = actor_admin(actor_id)
    if not reason or not reason.strip():
        raise ValidationError('Motivo obligatorio.')
    with exclusion(source_id) as locked:
        if not locked:
            raise ValidationError('No se obtuvo exclusión; no recuperar un trabajador vivo.')
        with transaction.atomic():
            Fuente.objects.select_for_update().get(pk=source_id)
            result = []
            for execution in Ejecucion.objects.select_for_update().filter(fuente_id=source_id, estado='en_curso'):
                issue = incident(execution, 'INTERRUMPIDA', 'Recuperación con exclusión comprobada.')
                Revision.objects.create(actor=actor, incidencia=issue, dimension='incidencia', decision='resuelta',
                                        motivo=reason.strip(), detalle={'accion': 'cerrar_ejecucion', 'antes': 'en_curso', 'despues': 'fallida'})
                Ejecucion.objects.filter(pk=execution.pk).update(estado='fallida', fin=timezone.now(), error_resumen='Interrumpida; exclusión comprobada.')
                result.append(execution.pk)
            return result
