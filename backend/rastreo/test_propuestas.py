import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from django.db import connections, transaction, DatabaseError
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from convocatorias.models import Convocatoria
from . import tests as base
from .models import Version, Propuesta, PropuestaRevision, Publicacion
from .propuestas import guardar
from .revisiones import ConflictoRevision


class PropuestaTests(TransactionTestCase):
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    run_fake = base.RastreoTests.run_fake

    def setUp(self):
        base.RastreoTests.setUp(self)
        self.source_obj = self.source()
        self.run_fake(self.source_obj)
        self.version = Version.objects.first()
        self.publication = self.version.publicacion
        self.url = f'/api/gestion/rastreo/publicaciones/{self.publication.pk}/propuesta/'
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.actor)
        self.token = self.client.get('/api/auth/csrf/').data['csrfToken']

    def payload(self):
        return dict(clave_accion=str(uuid.uuid4()), version_id=self.version.pk,
                    observacion_base_id=self.publication.observaciones.first().pk, revisiones=[], datos={}, procedencia=[])

    def post(self, body):
        return self.client.post(self.url, body, format='json', HTTP_X_CSRFTOKEN=self.token)

    def test_incomplete_edit_history_and_no_catalog_writes(self):
        before = list(Convocatoria.objects.values())
        first = self.post(self.payload())
        self.assertEqual(first.status_code, 201, first.data)
        self.assertFalse(first.data['pendientes']['puede_crear'])
        body = self.payload(); body['datos'] = {'titulo': 'Trabajo pendiente'}
        second = self.client.patch(f'/api/gestion/rastreo/propuestas/{first.data["id"]}/', body, format='json', HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data['sustituye_id'], first.data['id'])
        self.assertEqual(Propuesta.objects.get(pk=first.data['id']).datos, {})
        self.assertEqual(self.client.get(self.url).data['count'], 2)
        self.assertEqual(before, list(Convocatoria.objects.values()))
        self.assertFalse(Publicacion.objects.exclude(convocatoria=None).exists())

    def test_invalid_and_foreign_references(self):
        self.assertEqual(self.client.get('/api/gestion/rastreo/propuestas/0/').status_code, 400)
        for update in ({'actor_id': self.user.pk}, {'datos': {'titulo': 3}}, {'datos': {'aprobada': True}}, {'version_id': Version.objects.exclude(pk=self.version.pk).first().pk}, {'procedencia': [{'campo': 'titulo', 'evidencia_id': 999999, 'motivo': 'x', 'localizador': 'p1'}]}):
            body = self.payload(); body.update(update)
            self.assertEqual(self.post(body).status_code, 400)
        self.assertEqual(Propuesta.objects.count(), 0)

    def test_idempotency_and_conflicts(self):
        body = self.payload()
        result = self.post(body)
        self.assertEqual(self.post(body).data['id'], result.data['id'])
        body['datos'] = {'titulo': 'Otro'}
        self.assertEqual(self.post(body).status_code, 409)
        self.assertEqual(self.post(self.payload()).status_code, 409)
        self.assertEqual(Propuesta.objects.count(), 1)

    def test_immutability_and_rollback(self):
        obj, _ = guardar(self.actor.pk, self.publication.pk, self.payload())
        with self.assertRaises(DatabaseError), transaction.atomic():
            Propuesta.objects.filter(pk=obj.pk).update(datos={})
        with self.assertRaises(DatabaseError), transaction.atomic():
            Propuesta.objects.filter(pk=obj.pk).delete()
        with patch('rastreo.propuestas.PropuestaRevision.objects.bulk_create', side_effect=RuntimeError('fallo sintético')):
            with self.assertRaises(RuntimeError):
                guardar(self.actor.pk, self.publication.pk, self.payload(), obj.pk)
        self.assertEqual(Propuesta.objects.count(), 1)
        self.assertEqual(PropuestaRevision.objects.count(), 0)

    def test_permissions_and_csrf(self):
        self.assertEqual(self.client.post(self.url, self.payload(), format='json').status_code, 403)
        for user in (None, self.user, self.actor):
            c = APIClient(enforce_csrf_checks=True)
            if user == self.actor:
                user.is_active = False; user.save(update_fields=['is_active'])
            if user:
                c.force_login(user)
            self.assertEqual(c.get(self.url).status_code, 403)

    def test_literals_and_revalidation_preserve_snapshot(self):
        body = self.payload()
        body['datos'] = {'cierre_original': '25 de octubre de 2026', 'beneficios': [{'id': 'b1', 'tope': '$3000'}]}
        result = self.post(body)
        self.assertEqual(result.status_code, 201, result.data)
        codes = {i['codigo'] for i in result.data['pendientes']['pendientes_publicacion']}
        self.assertTrue({'PRECISION_TEMPORAL', 'TOPE_NO_REPRESENTADO', 'AMBITO_DESCONOCIDO'} <= codes)
        doc = self.version.documentos.first().documento
        from pathlib import Path
        Path(self.temp.name, doc.clave_almacenamiento).unlink()
        valid = self.client.post(f'/api/gestion/rastreo/propuestas/{result.data["id"]}/validar/', {}, format='json', HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(valid.status_code, 200, valid.data)
        self.assertTrue(valid.data['contexto_cambio'])
        self.assertEqual(Propuesta.objects.get(pk=result.data['id']).pendientes, result.data['pendientes'])

    def test_concurrent_successors(self):
        first, _ = guardar(self.actor.pk, self.publication.pk, self.payload())
        bodies = [self.payload(), self.payload()]
        def worker(body):
            connections.close_all()
            try:
                guardar(self.actor.pk, self.publication.pk, body, first.pk)
                return 'ok'
            except ConflictoRevision:
                return 'conflict'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, bodies))
        self.assertCountEqual(results, ['ok', 'conflict'])
        self.assertEqual(Propuesta.objects.count(), 2)

    def test_observation_and_review_context_changes_without_mutating_history(self):
        from .revisiones import registrar
        obj, _ = guardar(self.actor.pk, self.publication.pk, self.payload())
        saved = obj.pendientes
        registrar(self.actor.pk, self.version.pk, dict(dimension='extraccion', decision='aprobada', motivo='Revisión sintética', evidencia_id=None, sustituye_id=None, clave_accion=uuid.uuid4()))
        self.run_fake(self.source_obj)
        from .propuestas import evaluar
        result = evaluar(self.version, obj.observacion_base_id, obj.datos, obj.procedencia, [])
        self.assertTrue({'CONTEXTO_OBSOLETO', 'REVISION_CAMBIADA'} <= {v['codigo'] for v in result['bloqueos']})
        obj.refresh_from_db(); self.assertEqual(obj.pendientes, saved)

    def test_a_b_a_selects_exact_observed_version(self):
        from .propuestas import latest
        from convocatorias.siau_red import PDFS
        original = self.fake
        def changed(url):
            if url in PDFS:
                return 200, {'content-type': 'application/pdf'}, b'%PDF-1.4\nOtra evidencia sintetica'
            return original(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=changed):
            from .services import run_manual
            run_manual(self.source_obj.pk, self.actor.pk, uuid.uuid4())
        other = latest(self.publication.pk)
        self.assertNotEqual(other.version_id, self.version.pk)
        self.run_fake(self.source_obj)
        returned = latest(self.publication.pk)
        self.assertEqual(returned.version_id, self.version.pk)
        self.assertGreater(returned.pk, other.pk)

    def test_foreign_review_and_closed_relations(self):
        from .revisiones import registrar
        review, _ = registrar(self.actor.pk, self.version.pk, dict(dimension='extraccion', decision='aprobada', motivo='Evidencia sintética', evidencia_id=None, sustituye_id=None, clave_accion=uuid.uuid4()))
        body = self.payload(); body['revisiones'] = [review.pk]
        obj, _ = guardar(self.actor.pk, self.publication.pk, body)
        with self.assertRaises(DatabaseError), transaction.atomic():
            PropuestaRevision.objects.filter(propuesta=obj).delete()
        empty_body = self.payload()
        successor, _ = guardar(self.actor.pk, self.publication.pk, empty_body, obj.pk)
        with self.assertRaises(DatabaseError), transaction.atomic():
            PropuestaRevision.objects.create(propuesta=successor, revision=review)

    def test_scopes_countries_partial_and_ownership(self):
        from perfiles.models import Pais
        Pais.objects.create(codigo='EC', nombre='Ecuador')
        Pais.objects.create(codigo='PE', nombre='Perú')
        body = self.payload()
        body['datos'] = {'opciones': [{'id': 'o1', 'paises': ['EC'], 'destinos': 'Literal conservado'}],
                         'beneficios': [{'id': 'b1', 'ambito': 'pendiente'}],
                         'requisitos': [{'id': 'r1', 'ambito': 'destino', 'opcion': 'o1', 'destino': 'EC'}]}
        saved = self.post(body)
        self.assertEqual(saved.status_code, 201, saved.data)
        stored = self.client.get(f'/api/gestion/rastreo/propuestas/{saved.data["id"]}/').data
        self.assertEqual(stored['datos']['beneficios'][0]['ambito'], 'pendiente')
        self.assertEqual(stored['datos']['requisitos'][0]['destino'], 'EC')
        self.assertTrue(any(p['codigo'] == 'AMBITO_DESCONOCIDO' for p in stored['pendientes']['pendientes_publicacion']))
        url = f'/api/gestion/rastreo/propuestas/{saved.data["id"]}/'
        for changes in ({'destino': 'PE'}, {'opcion': 'ajena'}, {'ambito': 'comun'}):
            invalid = {**body, 'clave_accion': str(uuid.uuid4()), 'datos': {**body['datos'], 'requisitos': [{**body['datos']['requisitos'][0], **changes}]}}
            self.assertEqual(self.client.patch(url, invalid, format='json', HTTP_X_CSRFTOKEN=self.token).status_code, 400)
        incomplete = {**body, 'clave_accion': str(uuid.uuid4()), 'datos': {**body['datos'], 'requisitos': [{'id': 'r1', 'ambito': 'destino'}]}}
        result = self.client.patch(url, incomplete, format='json', HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertTrue(any(p['codigo'] == 'AMBITO_INCOMPLETO' for p in result.data['pendientes']['pendientes_publicacion']))

    def test_pagination_pending_ids_methods_and_all_business_preserved(self):
        from django.apps import apps
        models = [m for m in apps.get_models() if m._meta.app_label in ('convocatorias', 'usuarios', 'perfiles', 'favoritos')]
        before = {m._meta.label: list(m.objects.order_by('pk').values()) for m in models}
        first, _ = guardar(self.actor.pk, self.publication.pk, self.payload())
        second, _ = guardar(self.actor.pk, self.publication.pk, self.payload(), first.pk)
        third, _ = guardar(self.actor.pk, self.publication.pk, self.payload(), second.pk)
        self.assertEqual(first.pendientes, third.pendientes)
        for item in third.pendientes['bloqueos'] + third.pendientes['pendientes_publicacion']:
            self.assertEqual(set(item), {'id', 'codigo', 'campo', 'motivo', 'condicion_resolucion'})
        self.assertEqual(self.client.get(self.url, {'page_size': 1, 'page': 2}).data['results'][0]['id'], second.pk)
        self.assertEqual(self.client.get(self.url, {'page_size': 1, 'page': 3}).data['results'][0]['id'], first.pk)
        self.assertEqual(self.client.get(self.url, {'page_size': 1, 'page': 4}).data['results'], [])
        self.assertEqual(self.client.post(f'/api/gestion/rastreo/propuestas/{first.pk}/', {}, format='json', HTTP_X_CSRFTOKEN=self.token).status_code, 405)
        self.assertEqual(before, {m._meta.label: list(m.objects.order_by('pk').values()) for m in models})

    def test_exact_document_review_and_revision_foreign_rejected(self):
        from .revisiones import registrar
        foreign = Version.objects.exclude(pk=self.version.pk).first()
        review, _ = registrar(self.actor.pk, foreign.pk, dict(dimension='extraccion', decision='aprobada', motivo='Sintético', evidencia_id=None, sustituye_id=None, clave_accion=uuid.uuid4()))
        body = self.payload(); body['revisiones'] = [review.pk]
        self.assertEqual(self.post(body).status_code, 400)
        evidence = self.version.documentos.first()
        body = self.payload(); body['datos'] = {'titulo': 'Transcrito'}
        body['procedencia'] = [{'campo': 'titulo', 'evidencia_id': evidence.pk, 'localizador': 'Encabezado', 'motivo': 'Transcripción exacta'}]
        result = self.post(body)
        self.assertEqual(result.status_code, 201)
        self.assertTrue(any(p['campo'] == f'evidencia.{evidence.pk}' and p['codigo'] == 'BASES_PENDIENTES' for p in result.data['pendientes']['bloqueos']))

    def test_direct_database_origin_guard(self):
        obj, _ = guardar(self.actor.pk, self.publication.pk, self.payload())
        fields = {f.name: getattr(obj, f.name) for f in Propuesta._meta.fields if f.name not in ('id', 'clave_accion', 'sustituye', 'version')}
        with self.assertRaises(DatabaseError), transaction.atomic():
            Propuesta.objects.create(**fields, clave_accion=uuid.uuid4(), sustituye=obj, version=Version.objects.exclude(pk=self.version.pk).first())
