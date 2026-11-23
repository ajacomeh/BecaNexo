import uuid
import copy
import json
import time
import http.client
from contextlib import contextmanager
from datetime import datetime, timedelta
from urllib.robotparser import RobotFileParser

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction, DatabaseError
from django.utils import timezone

from convocatorias.siau_red import Downloader, AccessError, SourceBackoff, retry_after_at, INDEX, NATIONAL_INDEX, ROBOTS, PAGES, PDFS, ALLOWED, AGENT, HOST
from convocatorias.siau_extraccion import EXTRACTOR_VERSION, extract_html
from .models import Fuente, Ejecucion, Acceso, Incidencia, Revision, Publicacion, CandidatoIndice, FRECUENCIA_MINIMA_MIN
from .observaciones import identity, observe, normalize_url
from .storage import prepare_document, register_document, StorageError, root_path
from .descubrimiento import BASE, MAX_BASES, MAX_FICHAS, NATIONAL_FICHA, NationalIndexLinks, candidate_url, index_pages, national_index_pages, national_ficha_content, national_ficha_flexible, candidate_ficha_content
from .siau_ajax import AJAX_INDEX, MAX_INDEX_PAGES, ajax_request, grid_config, robots_allowed, robots_allow_ajax
from .portal_fuentes import PORTALES, POLITICA_VERSION, GENERIC_POLICY_VERSION, generic_portal, portal_for_source, links as portal_links, extract_portal


BASE_POLICY = {'urls': sorted(ALLOWED), 'bytes_html': 2097152, 'bytes_pdf': 8388608, 'reintentos': 1}
CANDIDATE_BASE_LINK_LIMIT = 8
DISCOVERY_POLICY = {**BASE_POLICY, 'descubrimiento': {'indice': INDEX, 'max_fichas': MAX_FICHAS, 'max_bases': MAX_BASES}}
NATIONAL_POLICY = {**BASE_POLICY, 'descubrimiento': {'indice': INDEX, 'indice_nacionales': NATIONAL_INDEX,
    'max_fichas': MAX_FICHAS, 'max_bases': MAX_BASES, 'max_paginas_nacionales': 1}}
PAGINATED_POLICY = {**BASE_POLICY, 'urls': sorted([*ALLOWED, NATIONAL_INDEX, AJAX_INDEX]),
    'descubrimiento': {'indice': INDEX, 'indice_nacionales': NATIONAL_INDEX,
    'ajax_nacionales': AJAX_INDEX, 'max_fichas': MAX_FICHAS, 'max_bases': MAX_BASES,
    'max_paginas_nacionales': MAX_INDEX_PAGES, 'paginas_adicionales_por_ciclo': 1}}


def supported_policy(source):
    return ((source.politica_version == 'siau-cerrada/1' and source.politica_acceso == BASE_POLICY)
            or (source.politica_version == 'siau-indice/2' and source.politica_acceso == DISCOVERY_POLICY)
            or (source.politica_version == 'siau-nacionales/3' and source.politica_acceso == NATIONAL_POLICY)
            or (source.politica_version == 'siau-nacionales/4' and source.politica_acceso == PAGINATED_POLICY))


def actor_admin(actor_id):
    actor = get_user_model().objects.filter(pk=actor_id, is_active=True, rol='administrador').first()
    if actor is None:
        raise ValidationError('Se requiere ID de administrador activo real.')
    return actor


@transaction.atomic
def register_portal(actor_id, portal_key, reason, key=None):
    """Registra una fuente auditada inactiva; habilitarla exige decisión posterior."""
    actor = actor_admin(actor_id)
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError('Motivo obligatorio.')
    portal = PORTALES.get(portal_key)
    if portal is None:
        raise ValidationError('Portal fuera de los conectores revisados.')
    key = uuid.UUID(str(key)) if key else uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(742600, 1)')
    previous = Revision.objects.filter(clave_accion=key).first()
    if previous:
        if previous.actor_id != actor.pk or previous.motivo != reason.strip() or previous.fuente.url_base != portal.indice:
            raise ValidationError('Clave de acción reutilizada con otro contenido.')
        return previous.fuente, False
    if Fuente.objects.filter(url_base=portal.indice).exists():
        raise ValidationError('Fuente ya registrada: no sobrescribir configuración.')
    source = Fuente.objects.create(nombre=portal.nombre, adaptador='portal_ec:' + portal.clave,
        url_base=portal.indice, politica_version=POLITICA_VERSION, politica_acceso=portal.politica,
        frecuencia_min=FRECUENCIA_MINIMA_MIN, activa=False, aprobada_publicacion_automatica=False)
    Revision.objects.create(actor=actor, fuente=source, dimension='configuracion', decision='aplicada',
        motivo=reason.strip(), detalle={'antes': None, 'despues': snapshot(source.pk)}, clave_accion=key)
    return source, True


@transaction.atomic
def register_generic_portal(actor_id, name, seed, host, reason, *, max_pages=8,
                            max_depth=2, max_cards=8, access_verified=False, key=None):
    """Alta auditada e inactiva; la verificación de acceso requiere decisión humana."""
    actor = actor_admin(actor_id)
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError('Motivo obligatorio.')
    try:
        portal = generic_portal(name, seed, host, max_pages, max_depth, max_cards, access_verified)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if access_verified and len(reason.strip()) < 20:
        raise ValidationError('Describe la verificación de acceso antes de declararla aprobada.')
    key = uuid.UUID(str(key)) if key else uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(742600, 1)')
    previous = Revision.objects.filter(clave_accion=key).first()
    if previous:
        if (previous.actor_id != actor.pk or previous.motivo != reason.strip()
                or previous.fuente.url_base != portal.indice or previous.fuente.politica_acceso != portal.politica):
            raise ValidationError('Clave de acción reutilizada con otro contenido.')
        return previous.fuente, False
    if Fuente.objects.filter(url_base=seed).exists():
        raise ValidationError('Fuente ya registrada.')
    source = Fuente.objects.create(nombre=portal.nombre, adaptador='portal_ec:generico',
        url_base=seed, politica_version=GENERIC_POLICY_VERSION, politica_acceso=portal.politica,
        frecuencia_min=FRECUENCIA_MINIMA_MIN, activa=False, aprobada_publicacion_automatica=False)
    Revision.objects.create(actor=actor, fuente=source, dimension='configuracion', decision='aplicada',
        motivo=reason.strip(), detalle={'antes': None, 'despues': snapshot(source.pk)}, clave_accion=key)
    return source, True


@transaction.atomic
def verify_generic_access(source_id, actor_id, reason, key=None):
    """Confirma condiciones de acceso revisadas por un administrador; no activa la fuente."""
    actor = actor_admin(actor_id)
    if not isinstance(reason, str) or len(reason.strip()) < 20:
        raise ValidationError('Describa la verificación de condiciones públicas y robots.txt.')
    key = uuid.UUID(str(key)) if key else uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(742600, 1)')
    previous = Revision.objects.filter(clave_accion=key).first()
    if previous:
        if (previous.actor_id != actor.pk or previous.fuente_id != source_id or previous.motivo != reason.strip()):
            raise ValidationError('Clave de acción reutilizada con otro contenido.')
        return previous.fuente, False
    source = Fuente.objects.select_for_update().get(pk=source_id)
    portal = portal_for_source(source)
    if not portal.generico:
        raise ValidationError('Se requiere una fuente genérica.')
    if source.activa:
        raise ValidationError('No verificar acceso mientras la fuente esté activa.')
    if portal.acceso_verificado:
        return source, False
    before = snapshot(source.pk)
    source.politica_acceso = {**source.politica_acceso, 'acceso_verificado': True}
    source.save(update_fields=['politica_acceso'])
    Revision.objects.create(actor=actor, fuente=source, dimension='configuracion', decision='aplicada',
        motivo=reason.strip(), detalle={'antes': before, 'despues': snapshot(source.pk)}, clave_accion=key)
    return source, True


@transaction.atomic
def set_portal_active(source_id, actor_id, reason, active, key=None):
    actor = actor_admin(actor_id)
    if not isinstance(reason, str) or not reason.strip() or type(active) is not bool:
        raise ValidationError('Motivo y estado explícitos obligatorios.')
    key = uuid.UUID(str(key)) if key else uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(742600, 1)')
    previous = Revision.objects.filter(clave_accion=key).first()
    if previous:
        if (previous.actor_id != actor.pk or previous.fuente_id != source_id or previous.motivo != reason.strip()
                or previous.detalle.get('despues', {}).get('activa') != active):
            raise ValidationError('Clave de acción reutilizada con otro contenido.')
        return previous.fuente, False
    source = Fuente.objects.select_for_update().get(pk=source_id)
    portal = portal_for_source(source)
    if active and portal.generico and not portal.acceso_verificado:
        raise ValidationError('Condiciones de acceso sin verificar; fuente inactiva.')
    if source.activa == active:
        return source, False
    if Ejecucion.objects.filter(fuente=source, estado='en_curso').exists():
        raise ValidationError('No cambiar fuente durante una ejecución activa.')
    before = snapshot(source.pk)
    source.activa = active
    source.save(update_fields=['activa'])
    Revision.objects.create(actor=actor, fuente=source, dimension='configuracion', decision='aplicada',
        motivo=reason.strip(), detalle={'antes': before, 'despues': snapshot(source.pk)}, clave_accion=key)
    return source, True


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
    if source.politica_version in ('siau-indice/2', 'siau-nacionales/3'):
        return source, False
    if source.politica_version != 'siau-cerrada/1':
        raise ValidationError('La política actual no admite esta transición.')
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
def enable_national_discovery(actor_id, reason, key=None):
    """Autoriza por separado el segundo índice; no altera la fuente por importar código."""
    actor = actor_admin(actor_id)
    if not reason or not reason.strip():
        raise ValidationError('Motivo obligatorio.')
    key = uuid.UUID(str(key)) if key else uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(742600, 1)')
    previous = Revision.objects.filter(clave_accion=key).first()
    if previous:
        if (previous.actor_id != actor.pk or previous.motivo != reason.strip()
                or previous.detalle.get('despues', {}).get('politica_version') != 'siau-nacionales/3'):
            raise ValidationError('Clave de acción reutilizada con otro contenido.')
        return previous.fuente, False
    source = Fuente.objects.select_for_update().get(url_base=INDEX)
    if source.adaptador != 'siau' or not supported_policy(source) or source.aprobada_publicacion_automatica:
        raise ValidationError('Fuente fuera de la política SIAU vigente para ampliar.')
    if source.politica_version == 'siau-nacionales/3':
        return source, False
    if source.politica_version != 'siau-indice/2':
        raise ValidationError('Se requiere primero siau-indice/2.')
    if Ejecucion.objects.filter(fuente=source, estado='en_curso').exists():
        raise ValidationError('No cambiar la política durante una ejecución activa.')
    before = snapshot(source.pk)
    source.politica_acceso = NATIONAL_POLICY
    source.politica_version = 'siau-nacionales/3'
    source.save(update_fields=['politica_acceso', 'politica_version'])
    Revision.objects.create(actor=actor, fuente=source, dimension='configuracion', decision='aplicada',
                            motivo=reason.strip(), detalle={'antes': before, 'despues': snapshot(source.pk)}, clave_accion=key)
    return source, True


@transaction.atomic
def revert_national_discovery(actor_id, reason, key=None):
    """Vuelve solo a la política anterior; conserva capturas y auditoría."""
    actor = actor_admin(actor_id)
    if not reason or not reason.strip():
        raise ValidationError('Motivo obligatorio.')
    key = uuid.UUID(str(key)) if key else uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(742600, 1)')
    previous = Revision.objects.filter(clave_accion=key).first()
    if previous:
        before = previous.detalle.get('antes') or {}
        after = previous.detalle.get('despues') or {}
        if (previous.actor_id != actor.pk or previous.motivo != reason.strip()
                or before.get('politica_version') != 'siau-nacionales/3'
                or after.get('politica_version') != 'siau-indice/2'):
            raise ValidationError('Clave de acción reutilizada con otro contenido.')
        return previous.fuente, False
    source = Fuente.objects.select_for_update().get(url_base=INDEX)
    if source.adaptador != 'siau' or not supported_policy(source) or source.aprobada_publicacion_automatica:
        raise ValidationError('Fuente fuera del contrato SIAU.')
    if source.politica_version == 'siau-indice/2':
        return source, False
    if source.politica_version != 'siau-nacionales/3':
        raise ValidationError('La política actual no admite esta reversión.')
    if Ejecucion.objects.filter(fuente=source, estado='en_curso').exists():
        raise ValidationError('No revertir la política durante una ejecución activa.')
    before = snapshot(source.pk)
    source.politica_acceso = DISCOVERY_POLICY
    source.politica_version = 'siau-indice/2'
    source.save(update_fields=['politica_acceso', 'politica_version'])
    Revision.objects.create(actor=actor, fuente=source, dimension='configuracion', decision='aplicada',
                            motivo=reason.strip(), detalle={'antes': before, 'despues': snapshot(source.pk)}, clave_accion=key)
    return source, True


@transaction.atomic
def set_paginated_discovery(actor_id, reason, enable, key=None):
    """Transición auditada /3 ↔ /4; no toca ejecuciones ni evidencias."""
    actor = actor_admin(actor_id)
    if not reason or not reason.strip():
        raise ValidationError('Motivo obligatorio.')
    key = uuid.UUID(str(key)) if key else uuid.uuid4()
    before_version, after_version = (('siau-nacionales/3', 'siau-nacionales/4') if enable
                                     else ('siau-nacionales/4', 'siau-nacionales/3'))
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(742600, 1)')
    previous = Revision.objects.filter(clave_accion=key).first()
    if previous:
        old = previous.detalle.get('antes') or {}
        new = previous.detalle.get('despues') or {}
        if (previous.actor_id != actor.pk or previous.motivo != reason.strip()
                or old.get('politica_version') != before_version
                or new.get('politica_version') != after_version):
            raise ValidationError('Clave de acción reutilizada con otro contenido.')
        return previous.fuente, False
    source = Fuente.objects.select_for_update().get(url_base=INDEX)
    if source.adaptador != 'siau' or not supported_policy(source) or source.aprobada_publicacion_automatica:
        raise ValidationError('Fuente fuera del contrato SIAU.')
    if source.politica_version == after_version:
        return source, False
    if source.politica_version != before_version:
        raise ValidationError('La política actual no admite esta transición.')
    if Ejecucion.objects.filter(fuente=source, estado='en_curso').exists():
        raise ValidationError('No cambiar la política durante una ejecución activa.')
    before = snapshot(source.pk)
    source.politica_acceso = PAGINATED_POLICY if enable else NATIONAL_POLICY
    source.politica_version = after_version
    source.save(update_fields=['politica_acceso', 'politica_version'])
    Revision.objects.create(actor=actor, fuente=source, dimension='configuracion', decision='aplicada',
                            motivo=reason.strip(), detalle={'antes': before, 'despues': snapshot(source.pk)}, clave_accion=key)
    return source, True


@transaction.atomic
def set_frequency(source_id, actor_id, reason, minutes, key=None):
    actor = actor_admin(actor_id)
    if not reason or not reason.strip() or not isinstance(minutes, int) or not FRECUENCIA_MINIMA_MIN <= minutes <= 10080:
        raise ValidationError(f'Motivo y frecuencia de {FRECUENCIA_MINIMA_MIN} a 10080 minutos obligatorios.')
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
    if source.adaptador == 'siau':
        if not supported_policy(source) or source.aprobada_publicacion_automatica:
            raise ValidationError('Fuente fuera del contrato SIAU.')
    elif source.adaptador.startswith('portal_ec:'):
        proposed = copy.copy(source)
        proposed.frecuencia_min = minutes
        try:
            portal_for_source(proposed)
        except AccessError as exc:
            raise ValidationError('Fuente fuera del contrato institucional.') from exc
    else:
        raise ValidationError('Adaptador no admitido.')
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
def exclusion(source_id, global_lock=True):
    """Sesión PostgreSQL, sin transacción durante HTTP. Orden origen → fuente."""
    if connection.in_atomic_block:
        raise ValidationError('Rastreo requiere autocommit, sin transacción externa.')
    acquired = []
    try:
        for lock in (((742601, 1), (742602, source_id)) if global_lock else ((742602, source_id),)):
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
        self.portal = portal_for_source(source) if source.adaptador.startswith('portal_ec:') else None
        self.robots_url = self.portal.robots if self.portal else ROBOTS
        self.index_urls = {self.portal.indice} if self.portal else {INDEX, NATIONAL_INDEX, AJAX_INDEX}
        initial_urls = {self.robots_url, *self.index_urls} if self.portal else None
        super().__init__(pause=max(2, source.espera_seg), timeout=min(15, source.timeout_seg),
                         allowed_urls=initial_urls, allowed_host=self.portal.host if self.portal else HOST)
        self.execution = execution
        self.sequence = 0
        self.publication = None
        self.page_url = None
        self.candidate = None
        self.pages = set() if self.portal else set(PAGES)
        self.pdfs = set() if self.portal else set(PDFS)

    def record(self, url, record, status, result, document=None, error=None, headers=None,
               method='GET', public_parameters=None):
        self.sequence += 1
        admitted = datetime.fromisoformat(record['consulta_utc'])
        started = datetime.fromisoformat(record['inicio_peticion_utc']) if record.get('inicio_peticion_utc') else None
        finished = timezone.now()
        return Acceso.objects.create(ejecucion=self.execution, secuencia=self.sequence, publicacion=self.publication,
            rol='robots' if url == self.robots_url else 'indice' if url in self.index_urls else 'bases' if url in self.pdfs else 'ficha',
            metodo=method, parametros_publicos=public_parameters,
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
            if (not self.portal and url == NATIONAL_INDEX
                    and self.execution.configuracion_snapshot['politica_version'] == 'siau-nacionales/4'):
                try:
                    grid_config(content)
                except AccessError:
                    access = self.record(url, entry, status, 'bloqueado', error='AJAX_CONTRATO')
                    incident(self.execution, 'INDICE_ESTRUCTURA',
                             'Contrato AJAX público fuera de los límites admitidos.', access)
                    raise AccessError('Índice nacional fuera del contrato AJAX.') from None
            all_becas = self.execution.configuracion_snapshot['politica_version'] == 'siau-nacionales/4'
            if (not self.portal and self.page_url == url and url not in PAGES and self.execution.configuracion_snapshot['politica_version'] in ('siau-nacionales/3', 'siau-nacionales/4')
                    and not (candidate_ficha_content(content, self.candidate.titulo_publico) if self.candidate
                             else (national_ficha_content(content, include_all_becas=all_becas)
                                   # Plantilla distinta con el mismo título admitido: se conserva y se marca.
                                   or national_ficha_flexible(content, include_all_becas=all_becas)))):
                access = self.record(url, entry, status, 'bloqueado', error='FICHA_FUERA_ALCANCE')
                incident(self.execution, 'FICHA_FUERA_ALCANCE', 'La ficha no conserva la estructura nacional anunciada en el índice.', access, 'aviso')
                raise AccessError('Ficha fuera del alcance nacional verificado.')
            expected = 'application/pdf' if url in self.pdfs else 'text/plain' if url == self.robots_url else 'text/html'
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
                    # Aviso una sola vez por documento y URL: al obtenerlo por primera vez o cuando cambia su huella.
                    # Volver a descargar el mismo PDF no repite el aviso en cada corrida.
                    if url in self.pdfs and (created or prior is None or prior.documento_id != document.pk):
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
            if status in (429, 503):
                due = retry_after_at(headers)
                if due:
                    incident(self.execution, 'REINTENTO_FUENTE', due.isoformat(), access, 'aviso')
        Ejecucion.objects.filter(pk=self.execution.pk).update(latido_en=timezone.now())
        return status, headers, content

    def fetch_ajax(self, body, public_parameters):
        """Una sola solicitud POST; éxito solo con HTML interpretable y evidencia íntegra."""
        entry = {'consulta_utc': timezone.now().isoformat()}
        self.history.append(entry)
        self.current_record = entry
        try:
            status, headers, content = self.post_once(AJAX_INDEX, body)
        except (AccessError, OSError, ValueError, http.client.HTTPException) as exc:
            access = self.record(AJAX_INDEX, entry, None, 'error', error=type(exc).__name__,
                                 method='POST', public_parameters=public_parameters)
            incident(self.execution, 'RED', type(exc).__name__, access)
            raise AccessError('Fallo de acceso AJAX.') from exc
        if status != 200:
            access = self.record(AJAX_INDEX, entry, status, 'error', error=f'HTTP_{status}',
                                 method='POST', public_parameters=public_parameters)
            incident(self.execution, 'HTTP', f'HTTP {status}; sin avanzar la paginación.', access)
            if status in (429, 503):
                due = retry_after_at(headers)
                if due:
                    incident(self.execution, 'REINTENTO_FUENTE', due.isoformat(), access, 'aviso')
                raise SourceBackoff(f'HTTP {status}; reducir accesos a la fuente.')
            raise AccessError(f'HTTP {status}; sin avanzar la paginación.')
        try:
            if headers.get('content-type', '').split(';')[0].strip().lower() != 'text/html':
                raise AccessError('MIME AJAX inesperado.')
            parser = NationalIndexLinks(include_all_becas=True)
            parser.feed(content.decode('utf-8-sig'))
            if not parser.article_count:
                raise AccessError('Respuesta AJAX sin tarjetas de convocatorias.')
            prepared = prepare_document(content, 'text/html')
            with transaction.atomic():
                document, created = register_document(prepared)
                self.record(AJAX_INDEX, entry, status, 'descargado' if created else 'reutilizado',
                            document, headers=headers, method='POST', public_parameters=public_parameters)
            Ejecucion.objects.filter(pk=self.execution.pk).update(latido_en=timezone.now())
            return parser.urls
        except (AccessError, StorageError, OSError, DatabaseError, UnicodeError, ValueError) as exc:
            access = self.record(AJAX_INDEX, entry, status, 'error', error=type(exc).__name__,
                                 method='POST', public_parameters=public_parameters)
            incident(self.execution, 'INDICE_ESTRUCTURA', type(exc).__name__, access)
            raise AccessError('Página AJAX no verificable.') from exc


def _borradores_creados(execution):
    from convocatorias.models import BorradorRastreo
    return BorradorRastreo.objects.filter(
        version__observacion__ejecucion=execution,
        creada_en__gte=execution.inicio,
        creada_en__lte=execution.fin,
    ).distinct().count() if execution.fin else 0


def resumen_corrida(execution):
    """Resumen compacto y legible de una corrida: fecha, peticiones, candidatos nuevos y borradores creados."""
    from zoneinfo import ZoneInfo
    execution.refresh_from_db()
    fin = execution.fin or timezone.now()
    nuevas = Publicacion.objects.filter(fuente_id=execution.fuente_id, primera_deteccion__gte=execution.inicio,
                                        primera_deteccion__lte=fin).count() if execution.estado != 'omitida' else 0
    codigos = {}
    for codigo in execution.incidencias.values_list('codigo', flat=True):
        codigos[codigo] = codigos.get(codigo, 0) + 1
    peticiones = execution.accesos.count()
    borradores = _borradores_creados(execution)
    resultados = list(execution.observaciones.values_list('resultado', flat=True))
    con_cambios = sum(r in ('nueva', 'cambio_relevante') for r in resultados)
    tecnicos = resultados.count('cambio_bytes')
    local = execution.inicio.astimezone(ZoneInfo('America/Guayaquil'))
    partes = [local.strftime('%Y-%m-%d %H:%M') + ' (Ecuador)', execution.estado,
              f'{peticiones} {"petición" if peticiones == 1 else "peticiones"}',
              f'{execution.publicaciones_observadas} fichas observadas', f'{con_cambios} versiones nuevas',
              *([f'{tecnicos} {"cambio técnico" if tecnicos == 1 else "cambios técnicos"} sin cambios de contenido'] if tecnicos else []),
              f'{nuevas} {"candidato nuevo" if nuevas == 1 else "candidatos nuevos"}',
              f'{borradores} {"borrador creado" if borradores == 1 else "borradores creados"}',
              f'{sum(codigos.values())} incidencias']
    if execution.estado == 'omitida' and execution.error_resumen:
        partes.append(f'motivo: {execution.error_resumen}')
    return {'ejecucion_id': execution.pk, 'origen': execution.origen, 'estado': execution.estado, 'inicio': execution.inicio,
            'fin': execution.fin, 'peticiones': peticiones, 'publicaciones_observadas': execution.publicaciones_observadas,
            'versiones_nuevas': execution.versiones_nuevas, 'versiones_con_cambios': con_cambios, 'cambios_tecnicos': tecnicos,
            'observaciones_sin_cambios': execution.observaciones_sin_cambios,
            'candidatos_nuevos': nuevas, 'borradores_creados': borradores,
            'incidencias_total': sum(codigos.values()), 'incidencias_por_codigo': codigos,
            'motivo': execution.error_resumen if execution.estado in ('omitida', 'fallida') else None, 'texto': ' · '.join(partes)}


def summary(execution):
    execution.refresh_from_db()
    created = _borradores_creados(execution)
    return {'id': execution.pk, 'clave': str(execution.clave_idempotencia), 'estado': execution.estado,
            'accesos': execution.accesos.count(), 'documentos_distintos': execution.accesos.exclude(documento=None).values('documento').distinct().count(),
            'incidencias': list(execution.incidencias.values('id', 'codigo', 'gravedad', 'detalle')),
            'publicaciones_observadas': execution.publicaciones_observadas, 'versiones_nuevas': execution.versiones_nuevas,
            'observaciones_sin_cambios': execution.observaciones_sin_cambios,
            'convocatorias_creadas': created, 'revision_documental': 'pendiente',
            'resumen': resumen_corrida(execution)}


INTERRUMPIDA_MINUTOS = 10
ROTACION = 'Más fichas o páginas de las que caben en esta corrida; se cubren por rotación en las siguientes.'
# Cupo de MAX_FICHAS reservado para volver a observar publicaciones ya conocidas (la más antigua primero).
MAX_FICHAS_CONOCIDAS = 6


def seleccionar_fichas(source, candidates, limit=MAX_FICHAS, known_limit=MAX_FICHAS_CONOCIDAS):
    """Reparte el cupo entre publicaciones conocidas y candidatos nuevos.

    Hasta `known_limit` conocidas de la fuente, por última detección más antigua, aunque no aparezcan en el
    índice de esta corrida (se piden por su URL guardada si cumple el contrato de ficha de SIAU); el resto,
    candidatos nuevos en el orden del índice. Los cupos que sobran de un lado pasan al otro; nunca más de `limit`.
    Devuelve (fichas, hay_mas).
    """
    known = [url for url in Publicacion.objects.filter(fuente=source).order_by('ultima_deteccion', 'id')
             .values_list('url_normalizada', flat=True) if candidate_url(url, NATIONAL_FICHA) == url]
    known_set = set(known)
    new = [url for url in dict.fromkeys(candidates) if url not in known_set]
    take_known = known[:max(known_limit, limit - len(new))]
    take_new = new[:limit - len(take_known)]
    take_known = known[:limit - len(take_new)]
    return [*take_known, *take_new], len(known) + len(new) > limit


def _cerrar_interrumpidas(source):
    """Cierra las corridas programadas que quedaron «en curso» porque el proceso murió (apagado del equipo, tope de la tarea).

    Se llama con la exclusión de la fuente ya obtenida: un trabajador vivo la conservaría, así que lo que sigue en
    curso no tiene proceso. Solo corridas programadas (sin actor) y con latido más antiguo que el margen; las manuales
    siguen exigiendo la recuperación explícita y auditada. La corrida cerrada sigue consumiendo la ventana de frecuencia.
    """
    limite = timezone.now() - timedelta(minutes=INTERRUMPIDA_MINUTOS)
    cerradas = []
    for execution in Ejecucion.objects.select_for_update().filter(fuente=source, estado='en_curso', origen='programada'):
        if (execution.latido_en or execution.inicio) > limite:
            continue
        incident(execution, 'INTERRUMPIDA', 'Corrida programada interrumpida; cerrada automáticamente con la exclusión comprobada.')
        Ejecucion.objects.filter(pk=execution.pk).update(estado='fallida', fin=timezone.now(), error_resumen='Interrumpida; exclusión comprobada.')
        cerradas.append(execution.pk)
    return cerradas


def run_manual(source_id, actor_id, key, manual_context=None):
    actor_admin(actor_id)
    return _run(source_id, actor_id, key, 'manual', manual_context)


def cerrar_programadas_interrumpidas(source_id):
    """Cierra (con la exclusión de la fuente) las corridas programadas que quedaron en curso sin proceso vivo."""
    adapter = Fuente.objects.only('adaptador').get(pk=source_id).adaptador
    with exclusion(source_id, global_lock=not adapter.startswith('portal_ec:')) as locked:
        if not locked:
            return []
        with transaction.atomic():
            return _cerrar_interrumpidas(Fuente.objects.select_for_update().get(pk=source_id))


def run_scheduled(source_id, key=None):
    return _run(source_id, None, key or uuid.uuid4(), 'programada')


def run_candidate(candidate_id, actor_id, key, reason):
    """Procesa una ficha de un candidato, con los mismos controles de una captura manual."""
    actor_admin(actor_id)
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError('Motivo de auditoría obligatorio.')
    candidate = CandidatoIndice.objects.select_related('fuente').get(pk=candidate_id)
    if candidate_url(candidate.url_normalizada, NATIONAL_FICHA) != candidate.url_normalizada:
        raise ValidationError('El candidato no conserva una URL individual canónica admitida.')
    return _run(candidate.fuente_id, actor_id, key, 'manual',
                {'modalidad': 'candidato_indice', 'candidato_id': candidate.pk,
                 'url': candidate.url_normalizada, 'motivo': reason.strip()})


def next_due(source):
    # Todas las capturas consumen la misma ventana mínima de la fuente.
    last = (Ejecucion.objects.filter(fuente=source).exclude(estado='omitida')
            .order_by('-inicio', '-id').first())
    scheduled = last.inicio + timedelta(minutes=source.frecuencia_min) if last else None
    from .web_frequency import source_retry_due
    retry_limit = source_retry_due(source)
    return max(filter(None, (scheduled, retry_limit)), default=None)


def _run(source_id, actor_id, key, origin, manual_context=None):
    key = uuid.UUID(str(key))
    candidate_id = (manual_context or {}).get('candidato_id')
    existing = Ejecucion.objects.filter(clave_idempotencia=key).first()
    if existing:
        if existing.fuente_id != source_id or existing.solicitado_por_id != actor_id or existing.origen != origin:
            raise ValidationError('Clave idempotente pertenece a otra operación.')
        if candidate_id and existing.configuracion_snapshot.get('solicitud_manual') != manual_context:
            raise ValidationError('Clave idempotente pertenece a otro candidato o motivo.')
        return existing
    adapter = Fuente.objects.only('adaptador').get(pk=source_id).adaptador
    with exclusion(source_id, global_lock=not adapter.startswith('portal_ec:')) as locked:
        with transaction.atomic():
            source = Fuente.objects.select_for_update().get(pk=source_id)
            if origin == 'programada' and locked:
                _cerrar_interrumpidas(source)
            # Serializa creación incluso para invocaciones omitidas.
            existing = Ejecucion.objects.filter(clave_idempotencia=key).first()
            if existing:
                if existing.fuente_id != source_id or existing.solicitado_por_id != actor_id or existing.origen != origin:
                    raise ValidationError('Clave idempotente pertenece a otra operación.')
                if candidate_id and existing.configuracion_snapshot.get('solicitud_manual') != manual_context:
                    raise ValidationError('Clave idempotente pertenece a otro candidato o motivo.')
                return existing
            from .web_frequency import source_blocked
            due = next_due(source)
            if origin == 'programada':
                if due and due > timezone.now():
                    return Ejecucion.objects.filter(fuente=source).exclude(estado='omitida').order_by('-inicio').first()
            reason = None
            if due and due > timezone.now():
                reason = 'La frecuencia de esta fuente aún no permite otra captura.'
            if source_blocked(source):
                reason = 'Fuente bloqueada por HTTP 429/503; requiere revisión antes de continuar.'
            if candidate_id:
                if (source.adaptador != 'siau'
                        or source.politica_version not in ('siau-nacionales/3', 'siau-nacionales/4')
                        or not supported_policy(source)
                        or not CandidatoIndice.objects.filter(pk=candidate_id, fuente=source,
                            url_normalizada=manual_context['url']).exists()):
                    reason = 'Candidato o política fuera del contrato de ficha individual SIAU.'
            if not locked:
                reason = 'Origen o fuente ocupados por otra ejecución.'
            elif not source.activa:
                reason = 'Fuente desactivada.'
            elif Ejecucion.objects.filter(fuente=source, estado='en_curso').exists():
                reason = 'Existe una ejecución pendiente de recuperación explícita.'
            portal = None
            if source.adaptador.startswith('portal_ec:'):
                try:
                    portal = portal_for_source(source)
                except AccessError:
                    reason = 'Configuración fuera del contrato institucional cerrado.'
            elif source.adaptador != 'siau' or source.url_base != INDEX or not supported_policy(source):
                reason = 'Configuración fuera del contrato SIAU cerrado.'
            now = timezone.now()
            configuration = snapshot(source.pk)
            if manual_context:
                kind = ('solicitud_extraordinaria' if manual_context.get('modalidad') == 'extraordinaria'
                        else 'solicitud_manual')
                configuration[kind] = manual_context
            execution = Ejecucion.objects.create(fuente=source, solicitado_por_id=actor_id, origen=origin, clave_idempotencia=key,
                configuracion_snapshot=configuration, version_extractor=(GENERIC_POLICY_VERSION if portal and portal.generico else POLITICA_VERSION) if portal else EXTRACTOR_VERSION,
                inicio=now, estado='omitida' if reason else 'en_curso', fin=now if reason else None, error_resumen=reason)
            if reason:
                incident(execution, 'OMITIDA', reason, severity='aviso')
                return execution
        if portal:
            from .portal_runner import capture
            return capture(execution, source, portal)
        if candidate_id:
            return _capture_candidate(execution, source, candidate_id)
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
                return (robots_allowed(robots['contenido'], url) if source.politica_version == 'siau-nacionales/4'
                        else policy.can_fetch(AGENT, url))
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
                if source.politica_version in ('siau-indice/2', 'siau-nacionales/3', 'siau-nacionales/4'):
                    discovered, truncated = index_pages(index['contenido'])
                    if truncated:
                        if source.politica_version == 'siau-nacionales/4':
                            incident(execution, 'INDICE_LIMITE', ROTACION, severity='aviso')
                        else:
                            incident(execution, 'INDICE_LIMITE', 'El índice supera el máximo de fichas; se requiere revisión.')
                    pages = list(dict.fromkeys([*PAGES, *discovered]))[:MAX_FICHAS]
                    downloader.pages.update(pages)
                    downloader.allowed_urls.update(pages)
            except SourceBackoff:
                raise
            except AccessError:
                pass  # Fichas autorizadas se investigan aunque falle el índice.
            except (UnicodeError, ValueError):
                incident(execution, 'INDICE_ESTRUCTURA', 'Índice no interpretable; se conservan las fichas conocidas.')
            if source.politica_version in ('siau-nacionales/3', 'siau-nacionales/4'):
                downloader.allowed_urls.add(NATIONAL_INDEX)
                try:
                    national = download(NATIONAL_INDEX)
                    discovered, truncated = national_index_pages(national['contenido'])
                    if source.politica_version == 'siau-nacionales/4':
                        first_parser = NationalIndexLinks(include_all_becas=True)
                        first_parser.feed(national['contenido'].decode('utf-8-sig'))
                        discovered = first_parser.urls
                        truncated = truncated or len(discovered) > MAX_FICHAS
                        pages = list(dict.fromkeys([*pages, *discovered]))[:MAX_FICHAS]
                        downloader.pages.update(pages)
                        downloader.allowed_urls.update(pages)
                        try:
                            config = grid_config(national['contenido'])
                        except AccessError:
                            incident(execution, 'INDICE_ESTRUCTURA', 'Contrato AJAX público fuera de los límites admitidos.')
                            raise
                        extra = []
                        if config['max_num_pages'] > 1:
                            if not robots_allow_ajax(robots['contenido']):
                                incident(execution, 'ROBOTS', 'No se confirmó autorización del endpoint AJAX.')
                            else:
                                previous = (Acceso.objects.filter(ejecucion__fuente=source, url_normalizada=AJAX_INDEX,
                                                                  metodo='POST').order_by('-id').first())
                                last_page = ((previous.parametros_publicos or {}).get('pagina') if previous else None)
                                maximum = min(config['max_num_pages'], MAX_INDEX_PAGES)
                                page_number = (last_page + 1 if previous and previous.documento_id and
                                               type(last_page) is int and 2 <= last_page < maximum else
                                               last_page if previous and not previous.documento_id and
                                               type(last_page) is int and 2 <= last_page <= maximum else 2)
                                body, parameters = ajax_request(config, page_number)
                                downloader.allowed_urls.add(AJAX_INDEX)
                                try:
                                    extra = downloader.fetch_ajax(body, parameters)
                                except SourceBackoff:
                                    raise
                                except AccessError:
                                    pass  # Se conserva la posición anterior para el próximo ciclo.
                        candidates = list(dict.fromkeys([*discovered, *extra, *pages]))
                        pages, more = seleccionar_fichas(source, candidates)
                        truncated = truncated or config['max_num_pages'] > 2 or more
                    else:
                        truncated = truncated or len(pages) + len([url for url in discovered if url not in pages]) > MAX_FICHAS
                        pages = list(dict.fromkeys([*pages, *discovered]))[:MAX_FICHAS]
                    if truncated:
                        # Con /4 la cobertura parcial es la rotación por diseño (12 fichas y una página AJAX por corrida):
                        # aviso. Los fallos reales del índice o del AJAX (red, HTTP, 429/503, robots, respuesta inválida)
                        # registran su propia incidencia de error y siguen degradando el estado.
                        if source.politica_version == 'siau-nacionales/4':
                            incident(execution, 'INDICE_LIMITE', ROTACION, severity='aviso')
                        else:
                            incident(execution, 'INDICE_LIMITE', 'Índice nacional con cobertura parcial; existen más páginas o fichas que el límite.')
                    downloader.pages.update(pages)
                    downloader.allowed_urls.update(pages)
                except SourceBackoff:
                    raise
                except AccessError:
                    pass  # Fichas conocidas siguen disponibles; el acceso fallido queda registrado.
                except (UnicodeError, ValueError):
                    incident(execution, 'INDICE_ESTRUCTURA', 'Índice nacional no interpretable; se conservan las fichas conocidas.')
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
                        candidate = candidate_url(link['url'], BASE) if source.politica_version in ('siau-indice/2', 'siau-nacionales/3', 'siau-nacionales/4') else None
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
                            except SourceBackoff:
                                raise
                            except (AccessError, ValueError):
                                pdf_cache[link['url']] = None
                        document = pdf_cache[link['url']]
                        if document is None:
                            pending.append({'url': link['url'], 'estado': 'inaccesible'})
                            incident(execution, 'BASE_INACCESIBLE', 'Evidencia parcial; no se sustituye por un PDF histórico.', publication=publication)
                        else:
                            evidence.append({'rol': 'bases_pdf', 'url': link['url'], 'url_original': link['url_original'], 'documento': document})
                    observed = observe(execution, publication, item, evidence, pending)
                    if observed.version_id and getattr(settings, 'RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS', False):
                        try:
                            from .auto_borradores import prepare_automatic_draft
                            _origin, _created, review_reason = prepare_automatic_draft(publication.pk, observed.version_id)
                            if review_reason and observed.resultado != 'sin_cambios':
                                # Sin borrador: el motivo queda visible en la bandeja de rastreo.
                                code = ('BORRADOR_REVISION_PENDIENTE' if _origin else
                                        'CANDIDATO_FUERA_ALCANCE' if review_reason.startswith('Descartada') else 'CANDIDATO_PENDIENTE')
                                incident(execution, code, review_reason, severity='aviso', publication=publication)
                        except Exception as exc:
                            # Una incidencia editorial no elimina la versión ni sus documentos.
                            incident(execution, 'BORRADOR_AUTO_FALLIDO', type(exc).__name__, publication=publication)
                except SourceBackoff:
                    raise
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


def _capture_candidate(execution, source, candidate_id):
    """Captura una ficha sin consultar índices; PDF opcional bajo límites de acceso."""
    candidate = CandidatoIndice.objects.get(pk=candidate_id, fuente=source)
    url = candidate.url_normalizada
    try:
        root_path()
        downloader = PersistentDownloader(execution, source)
        downloader.candidate = candidate
        downloader.page_url = url
        downloader.pages.add(url)
        downloader.allowed_urls.add(url)
        robots = downloader.fetch(ROBOTS)
        policy = RobotFileParser(ROBOTS)
        policy.parse(robots['contenido'].decode('utf-8-sig').splitlines())
        delay = policy.crawl_delay(AGENT) or 0
        if delay > 60:
            raise AccessError('crawl-delay excede el presupuesto admitido.')
        downloader.pause = max(downloader.pause, delay)
        if not robots_allowed(robots['contenido'], url):
            incident(execution, 'ROBOTS', 'Ficha bloqueada por robots.txt.')
            raise AccessError('robots.txt bloquea la ficha.')
        page = downloader.fetch(url, can_fetch=lambda target: robots_allowed(robots['contenido'], target))
        item = extract_html(page)
        publication = downloader.publication
        if publication is None:
            raise AccessError('La ficha no produjo una identidad verificable.')
        html_access = execution.accesos.filter(url_normalizada=page['url'], documento__isnull=False).select_related('documento').latest('id')
        evidence = [{'rol': 'ficha_html', 'url': url, 'url_original': url, 'documento': html_access.documento}]
        pending = []
        links = list({link['url']: link for link in item['enlaces_bases']}.values())
        too_many_links = len(links) > CANDIDATE_BASE_LINK_LIMIT
        if too_many_links:
            incident(execution, 'BASES_LIMITE', 'Demasiados enlaces BASES; revisar la ficha archivada.',
                     severity='aviso', publication=publication)
            links = links[:CANDIDATE_BASE_LINK_LIMIT]
        pdf_enabled = getattr(settings, 'RASTREO_CANDIDATO_PDF_HABILITADO', False)
        eligible = [link for link in links if candidate_url(link['url'], BASE) == link['url']]
        single_pdf = pdf_enabled and not too_many_links and len({link['url'] for link in eligible}) == 1
        for link in links:
            pdf_url = link['url']
            if not single_pdf or link not in eligible:
                pending.append({'url': pdf_url, 'estado': 'base_no_descargada' if not pdf_enabled
                                else 'fuera_de_lista' if link not in eligible else 'seleccion_pendiente'})
                continue
            # El descargador exige HTTPS, host, URL exacta, DNS público, MIME PDF,
            # firma, tamaño y SHA-256; robots se comprueba también para esta ruta.
            downloader.pdfs.add(pdf_url)
            downloader.allowed_urls.add(pdf_url)
            try:
                pdf = downloader.fetch(pdf_url, can_fetch=lambda target: robots_allowed(robots['contenido'], target))
                document = execution.accesos.filter(url_normalizada=pdf['url'], documento__isnull=False).select_related('documento').latest('id').documento
                evidence.append({'rol': 'bases_pdf', 'url': pdf_url,
                                 'url_original': link['url_original'], 'documento': document})
            except SourceBackoff:
                raise
            except (AccessError, ValueError):
                pending.append({'url': pdf_url, 'estado': 'inaccesible'})
                incident(execution, 'BASE_INACCESIBLE', 'PDF individual no disponible; se conserva la ficha HTML.',
                         severity='aviso', publication=publication)
        observed = observe(execution, publication, item, evidence, pending)
        if observed.version_id:
            from .auto_borradores import classify_candidate, prepare_automatic_draft
            version = observed.version
            assessment = classify_candidate(publication, version, allow_partial=True)
            if assessment['estado'] == 'apta' and getattr(settings, 'RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS', False):
                try:
                    _, _, review_reason = prepare_automatic_draft(publication.pk, version.pk, allow_partial=True)
                    if review_reason:
                        incident(execution, 'BORRADOR_REVISION_PENDIENTE', review_reason,
                                 severity='aviso', publication=publication)
                except Exception as exc:
                    incident(execution, 'BORRADOR_AUTO_FALLIDO', type(exc).__name__, publication=publication)
            elif assessment['estado'] != 'apta':
                incident(execution, 'CANDIDATO_PENDIENTE' if assessment['estado'] == 'pendiente' else 'CANDIDATO_FUERA_ALCANCE',
                         assessment['motivo'], severity='aviso', publication=publication)
        failures = execution.incidencias.filter(gravedad='error').exists()
        Ejecucion.objects.filter(pk=execution.pk).update(estado='parcial' if failures else 'finalizada', fin=timezone.now())
    except Exception as exc:
        # Los errores técnicos nunca se convierten en datos editoriales.
        incident(execution, 'CANDIDATO_FALLIDO', type(exc).__name__)
        Ejecucion.objects.filter(pk=execution.pk).update(estado='fallida', fin=timezone.now(), error_resumen=type(exc).__name__)
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
