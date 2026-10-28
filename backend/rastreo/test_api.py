import uuid
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from convocatorias.test_siau import FIXTURE
from convocatorias.siau_red import PAGES
from . import tests as base
from .models import Publicacion, Version, Documento, Ejecucion
from .services import run_manual

ROOT = '/api/gestion/rastreo/'


class ConsultaRastreoTests(TransactionTestCase):
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    run_fake = base.RastreoTests.run_fake

    def setUp(self):
        base.RastreoTests.setUp(self)
        self.source_obj = self.source()
        self.run = self.run_fake(self.source_obj)
        self.publication = Publicacion.objects.order_by('id').first()
        self.version = self.publication.versiones.get()
        self.document = Documento.objects.first()
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.actor)

    def urls(self):
        p, v, e = self.publication.pk, self.version.pk, self.run.pk
        return ['fuentes/', 'publicaciones/', f'publicaciones/{p}/', f'publicaciones/{p}/versiones/',
                f'publicaciones/{p}/versiones/{v}/', f'publicaciones/{p}/versiones/{v}/documentos/',
                f'publicaciones/{p}/observaciones/', 'ejecuciones/', f'ejecuciones/{e}/',
                f'ejecuciones/{e}/accesos/', f'ejecuciones/{e}/incidencias/', f'documentos/{self.document.pk}/descarga/']

    def test_permissions_every_endpoint_and_no_sensitive_fields(self):
        for path in self.urls():
            response = self.client.get(ROOT + path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn('no-store', response['Cache-Control'])
            if 'descarga' not in path:
                for private in ('clave_almacenamiento', 'configuracion_snapshot', 'solicitado_por', 'transaccion_id', 'etag', 'last_modified'):
                    self.assertNotIn(private, response.content.decode())
        for user in (None, self.user, self.actor):
            client = APIClient()
            if user == self.actor:
                user.is_active = False
                user.save(update_fields=['is_active'])
            if user:
                client.force_authenticate(user=user)
            for path in self.urls():
                self.assertEqual(client.get(ROOT + path).status_code, 403, path)

    def test_filters_validation_pagination_and_bounded_queries(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(ROOT + 'publicaciones/?page_size=1')
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['results']), 1)
        self.assertLessEqual(len(queries), 5)
        self.assertEqual(self.client.get(ROOT + f'publicaciones/?fuente={self.source_obj.pk}&q=FICTICIO').data['count'], 2)
        self.assertEqual(self.client.get(ROOT + 'publicaciones/?q=ausente').data['count'], 0)
        for params in ('page=0', 'page_size=51', 'page=x', 'page=1&page=2', 'fuente=0', 'q=' + 'x' * 201, 'ruta=privada'):
            self.assertEqual(self.client.get(ROOT + 'publicaciones/?' + params).status_code, 400)
        self.assertEqual(self.client.get(ROOT + 'publicaciones/999999999999999999999999/').status_code, 400)
        self.assertEqual(self.client.get(ROOT + 'publicaciones/999999/').status_code, 404)

    def test_a_b_a_uses_observations_not_highest_version_id(self):
        def changed(url):
            if url in PAGES:
                return 200, {'content-type': 'text/html'}, FIXTURE.read_bytes().replace(b'$3000', b'$1000')
            return self.fake(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=changed):
            run_manual(self.source_obj.pk, self.actor.pk, uuid.uuid4())
        self.run_fake(self.source_obj)
        response = self.client.get(ROOT + f'publicaciones/{self.publication.pk}/')
        self.assertEqual(response.data['version_observada_id'], self.version.pk)
        self.assertGreater(self.publication.versiones.order_by('-id').first().pk, self.version.pk)
        history = self.client.get(ROOT + f'publicaciones/{self.publication.pk}/observaciones/').data['results']
        self.assertEqual([r['version_id'] for r in history][::2], [self.version.pk, self.version.pk])

    def test_execution_without_publications_and_document_counts(self):
        execution = Ejecucion.objects.create(fuente=self.source_obj, solicitado_por=self.actor, configuracion_snapshot={}, version_extractor='test')
        response = self.client.get(ROOT + f'ejecuciones/{execution.pk}/')
        self.assertEqual(response.data['publicaciones_observadas'], 0)
        self.assertEqual(response.data['documentos_distintos'], 0)
        actual = self.client.get(ROOT + f'ejecuciones/{self.run.pk}/').data
        self.assertEqual(actual['accesos'], self.run.accesos.count())
        self.assertEqual(actual['documentos_distintos'], self.run.accesos.exclude(documento=None).values('documento').distinct().count())

    def test_exact_version_documents_and_wrong_parent(self):
        other = Version.objects.exclude(publicacion=self.publication).get()
        self.assertEqual(self.client.get(ROOT + f'publicaciones/{self.publication.pk}/versiones/{other.pk}/').status_code, 404)
        data = self.client.get(ROOT + f'publicaciones/{self.publication.pk}/versiones/{self.version.pk}/documentos/').data
        self.assertEqual({x['id'] for x in data['results']}, set(self.version.documentos.values_list('documento_id', flat=True)))

    def test_download_html_attachment_missing_corrupt_and_invalid_id(self):
        doc = self.version.documentos.get(rol='ficha_html').documento
        path = ROOT + f'documentos/{doc.pk}/descarga/'
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('sandbox', response['Content-Security-Policy'])
        file = Path(self.temp.name) / doc.clave_almacenamiento
        self.assertEqual(response.content, file.read_bytes())
        file.write_bytes(b'inconsistente')
        response = self.client.get(path)
        self.assertEqual(response.status_code, 409)
        self.assertNotIn(self.temp.name, response.content.decode())
        file.unlink()
        self.assertEqual(self.client.get(path).status_code, 409)
        self.assertEqual(self.client.get(ROOT + 'documentos/999999/descarga/').status_code, 404)
        self.assertEqual(self.client.get(path + '?path=../../backend/.env').status_code, 400)

    def test_read_queries_and_rejected_writes_do_not_change_records(self):
        models = [m for m in apps.get_models() if m._meta.app_label in ['rastreo', 'usuarios', 'perfiles', 'convocatorias', 'favoritos']]
        before = {m._meta.label: list(m.objects.order_by('pk').values()) for m in models}
        for path in self.urls():
            self.client.get(ROOT + path)
            self.assertIn(self.client.post(ROOT + path, {}, format='json').status_code, (403, 405))
        self.assertEqual(before, {m._meta.label: list(m.objects.order_by('pk').values()) for m in models})

    def test_publication_without_title_uses_url_without_inventing_content(self):
        p = Publicacion.objects.create(fuente=self.source_obj, url_original='https://example.org/sin-titulo/',
            url_normalizada='https://example.org/sin-titulo/', normalizacion_version='test')
        data = self.client.get(ROOT + f'publicaciones/{p.pk}/').data
        self.assertEqual(data['titulo'], '/sin-titulo/')
        self.assertIsNone(data['version_observada_id'])
        self.assertEqual(self.client.get(ROOT + f'publicaciones/{p.pk}/versiones/').data['count'], 0)

    def test_download_rejects_linked_parent_without_reading_file(self):
        with patch('rastreo.api.verify_file') as verify, patch('pathlib.Path.is_symlink', return_value=True):
            response = self.client.get(ROOT + f'documentos/{self.document.pk}/descarga/')
        self.assertEqual(response.status_code, 409)
        verify.assert_not_called()
