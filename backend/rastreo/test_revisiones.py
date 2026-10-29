import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connections, transaction, DatabaseError
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from convocatorias.siau_red import PAGES
from convocatorias.test_siau import FIXTURE
from . import tests as base
from .models import Revision, Publicacion, Version
from .revisiones import registrar, RevisionEntrada, ConflictoRevision
from .services import run_manual

ROOT = '/api/gestion/rastreo/'


class RevisionTests(TransactionTestCase):
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    run_fake = base.RastreoTests.run_fake

    def setUp(self):
        base.RastreoTests.setUp(self)
        self.source_obj = self.source()
        self.run_fake(self.source_obj)
        self.version = Version.objects.order_by('id').first()
        self.url = ROOT + f'publicaciones/{self.version.publicacion_id}/versiones/{self.version.pk}/revisiones/'
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.actor)
        self.token = self.client.get('/api/auth/csrf/').data['csrfToken']

    def payload(self, **overrides):
        return dict(dimension='extraccion', decision='aprobada', motivo='La evidencia sintética coincide.', evidencia_id=None, sustituye_id=None, clave_accion=str(uuid.uuid4()), **overrides)

    def post(self, data):
        return self.client.post(self.url, data, format='json', HTTP_X_CSRFTOKEN=self.token)

    def test_create_session_csrf_and_no_business_changes(self):
        models = [m for m in apps.get_models() if m._meta.app_label in ['usuarios', 'perfiles', 'convocatorias', 'favoritos']]
        before = {m._meta.label: list(m.objects.order_by('pk').values()) for m in models}
        config = list(Revision.objects.filter(dimension='configuracion').values())
        result = self.post(self.payload())
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['administrador']['id'], self.actor.pk)
        self.assertIn('no-store', result['Cache-Control'])
        self.assertEqual(before, {m._meta.label: list(m.objects.order_by('pk').values()) for m in models})
        self.assertEqual(config, list(Revision.objects.filter(dimension='configuracion').values()))
        self.source_obj.refresh_from_db()
        self.assertFalse(self.source_obj.aprobada_publicacion_automatica)
        self.assertFalse(Publicacion.objects.exclude(convocatoria=None).exists())

    def test_permissions_and_csrf(self):
        self.assertEqual(self.client.post(self.url, self.payload(), format='json').status_code, 403)
        for user in [None, self.user, self.actor]:
            client = APIClient(enforce_csrf_checks=True)
            if user == self.actor:
                user.is_active = False
                user.save(update_fields=['is_active'])
            if user:
                client.force_login(user)
            token = client.get('/api/auth/csrf/').data['csrfToken']
            self.assertEqual(client.get(self.url).status_code, 403)
            self.assertEqual(client.post(self.url, self.payload(), format='json', HTTP_X_CSRFTOKEN=token).status_code, 403)

    def test_invalid_fields_and_justification(self):
        for field, value in [('motivo', ''), ('motivo', '   '), ('motivo', 3), ('motivo', 'x'*5001), ('actor_id', self.actor.pk), ('decision', 'aplicada'), ('version_id', self.version.pk), ('creada_en', '2026-01-01')]:
            data = self.payload(); data[field] = value
            self.assertEqual(self.post(data).status_code, 400, field)
        self.assertEqual(self.post({}).status_code, 400)

    def test_document_membership_and_oferente_limits(self):
        evidence = self.version.documentos.first()
        data = self.payload(); data.update(dimension='documental', evidencia_id=evidence.pk)
        self.assertEqual(self.post(data).status_code, 201)
        data['evidencia_id'] = Version.objects.exclude(pk=self.version.pk).first().documentos.first().pk
        data['clave_accion'] = str(uuid.uuid4())
        self.assertEqual(self.post(data).status_code, 400)
        data.update(dimension='oferente', evidencia_id=evidence.pk, tipo_oferente='convenio', referencia='Página 1, convenio sintético')
        self.assertEqual(self.post(data).status_code, 400)
        data['tipo_oferente'] = 'entidad_ecuatoriana'
        self.assertEqual(self.post(data).status_code, 201)
        other = Version.objects.exclude(pk=self.version.pk).first()
        self.assertEqual(self.client.get(ROOT + f'publicaciones/{other.publicacion_id}/versiones/{self.version.pk}/revisiones/').status_code, 404)

    def test_idempotency_rectification_and_conflict(self):
        data = self.payload()
        first = self.post(data)
        self.assertEqual(self.post(data).status_code, 200)
        data['motivo'] = 'Contenido diferente'
        self.assertEqual(self.post(data).status_code, 409)
        correction = self.payload(); correction.update(decision='rechazada', sustituye_id=first.data['id'])
        self.assertEqual(self.post(correction).status_code, 201)
        self.assertEqual(self.post(self.payload()).status_code, 409)
        result = self.client.get(self.url).data
        self.assertEqual(result['count'], 2)
        self.assertEqual([r['decision'] for r in result['vigentes']], ['rechazada'])
        self.assertEqual(Revision.objects.get(pk=first.data['id']).decision, 'aprobada')

    def test_database_guards_and_immutability(self):
        first = self.post(self.payload()).data
        row = Revision.objects.get(pk=first['id'])
        for operation in [lambda: Revision.objects.filter(pk=row.pk).update(motivo='Mutación'), lambda: Revision.objects.filter(pk=row.pk).delete()]:
            with self.assertRaises(DatabaseError), transaction.atomic():
                operation()
        wrong = Version.objects.exclude(pk=self.version.pk).first()
        with self.assertRaises(DatabaseError), transaction.atomic():
            Revision.objects.create(actor=self.actor, version=wrong, dimension='extraccion', decision='rechazada', motivo='Prueba', detalle={}, sustituye=row)
        with self.assertRaises(DatabaseError), transaction.atomic():
            Revision.objects.create(actor=self.actor, version=self.version, evidencia=wrong.documentos.first(), dimension='documental', decision='aprobada', motivo='Prueba', detalle={})

    def test_history_no_inheritance_versions_documents_and_a_b_a(self):
        doc = self.version.documentos.first()
        data = self.payload(); data.update(dimension='documental', evidencia_id=doc.pk)
        self.post(data)
        self.assertEqual(len(self.client.get(self.url).data['vigentes']), 1)
        def changed(url):
            if url in PAGES:
                return 200, {'content-type': 'text/html'}, FIXTURE.read_bytes().replace(b'$3000', b'$1000')
            return self.fake(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=changed):
            run_manual(self.source_obj.pk, self.actor.pk, uuid.uuid4())
        self.assertFalse(self.client.get(self.url).data['ultima_observada'])
        newer = self.version.publicacion.versiones.order_by('-numero').first()
        url = ROOT + f'publicaciones/{newer.publicacion_id}/versiones/{newer.pk}/revisiones/'
        self.assertEqual(self.client.get(url).data['vigentes'], [])
        self.run_fake(self.source_obj)
        self.assertTrue(self.client.get(self.url).data['ultima_observada'])

    def test_concurrent_decisions_and_retries(self):
        def work(data, actor_id=None):
            try:
                serializer = RevisionEntrada(data=data); serializer.is_valid(raise_exception=True)
                return registrar(actor_id or self.actor.pk, self.version.pk, serializer.validated_data)[1]
            except ConflictoRevision:
                return 'conflict'
            finally:
                connections.close_all()
        data = self.payload()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(work, [data, data]))
        self.assertCountEqual(results, [True, False])
        first = Revision.objects.get(version=self.version)
        a, b = self.payload(), self.payload()
        a['sustituye_id'] = b['sustituye_id'] = first.pk
        second_actor = get_user_model().objects.create_user(email='revision-2@example.com', nombre='Otra administradora sintética', rol='administrador')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(work, [a, b], [self.actor.pk, second_actor.pk]))
        self.assertCountEqual(results, [True, 'conflict'])
