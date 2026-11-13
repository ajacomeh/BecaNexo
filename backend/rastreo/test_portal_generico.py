"""Portales ficticios y red simulada; escrituras solo en la base aislada autorizada."""
import tempfile
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from convocatorias.models import BorradorRastreo
from .models import Fuente, Incidencia, Publicacion, Revision
from .portal_fuentes import generic_portal, portal_for_source
from .services import register_generic_portal, verify_generic_access, run_manual, set_portal_active


HOST = 'becas.universidad.edu.ec'
SEED = f'https://{HOST}/becas/'
INDEX = b'<html><h1>Becas</h1><a href="/becas/listado">Becas disponibles</a></html>'
FICHE = (b'<html><h1>Beca de movilidad para ecuatorianos</h1>'
         b'<p>Dirigida a ciudadanos ecuatorianos.</p><h2>Requisitos</h2>'
         b'<p>Ser estudiante activo y ciudadano ecuatoriano.</p>'
         b'<p>Cierre: 12 de noviembre de 2026</p></html>')


class GenericContractTests(SimpleTestCase):
    def test_closed_source_limits(self):
        portal = generic_portal('Universidad', SEED, HOST, 4, 2, 3, True)
        self.assertTrue(portal.generico)
        for seed, host in [('http://' + HOST + '/becas/', HOST),
                           ('https://other.edu.ec/becas/', HOST),
                           ('https://' + HOST + '/becas/?token=x', HOST),
                           ('https://localhost/becas/', 'localhost')]:
            with self.assertRaises(ValueError):
                generic_portal('Universidad', seed, host)
        with self.assertRaises(ValueError):
            generic_portal('Universidad', SEED, HOST, 13)


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class GenericRunTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_fusion_db')
        self.actor = get_user_model().objects.create_user(email='generic-admin@example.com', nombre='Admin', rol='administrador')
        self.user = get_user_model().objects.create_user(email='generic-user@example.com', nombre='User')
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        storage = override_settings(RASTREO_STORAGE_ROOT=temp.name)
        storage.enable()
        self.addCleanup(storage.disable)

    def register(self, verified=True, max_pages=8):
        return register_generic_portal(self.actor.pk, 'Universidad sintética', SEED, HOST,
            'Acceso público y robots verificados en entorno simulado',
            max_pages=max_pages, access_verified=verified)[0]

    def test_inactive_until_access_is_confirmed_and_audited(self):
        with self.assertRaises(ValidationError):
            register_generic_portal(self.user.pk, 'Universidad', SEED, HOST, 'Intento')
        source = self.register(False)
        self.assertFalse(source.activa)
        with self.assertRaises(ValidationError):
            set_portal_active(source.pk, self.actor.pk, 'Sin verificación', True)
        self.assertEqual(Revision.objects.filter(fuente=source).count(), 1)
        with patch('convocatorias.siau_red.Downloader.once') as network:
            self.assertEqual(run_manual(source.pk, self.actor.pk, uuid.uuid4()).estado, 'omitida')
            network.assert_not_called()
        source, changed = verify_generic_access(source.pk, self.actor.pk,
            'Condiciones públicas y robots.txt revisados en el portal sintético')
        self.assertTrue(changed)
        self.assertFalse(source.activa)
        self.assertEqual(Revision.objects.filter(fuente=source).count(), 2)
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)

    def test_paginated_individual_sections_duplicate_news_and_incomplete(self):
        source = self.register()
        self.assertEqual(portal_for_source(source).max_profundidad, 2)
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        listing = (b'<html><h1>Becas</h1><a href="/becas/ficha">Beca movilidad</a>'
                   b'<a href="/becas/ficha">Beca repetida</a>'
                   b'<a href="/becas/noticia">Noticia de becas</a>'
                   b'<a href="/becas/incompleta">Beca sin datos</a>'
                   b'<h2>Beca de apoyo para ecuatorianos</h2>'
                   b'<p>Requisitos: ser ciudadano ecuatoriano. Cierre: 12 de noviembre de 2026.</p>'
                   b'<h2>Beca de investigacion para ecuatorianos</h2>'
                   b'<p>Requisitos: ser estudiante ecuatoriano. Cierre: 12 de noviembre de 2026.</p></html>')
        responses = {SEED: INDEX, f'https://{HOST}/becas/listado': listing,
                     f'https://{HOST}/becas/ficha': FICHE,
                     f'https://{HOST}/becas/noticia': b'<html><h1>Noticia de becas</h1><p>Ganadores.</p></html>',
                     f'https://{HOST}/becas/incompleta': b'<html><h1>Beca sin datos</h1><p>Informaci\xc3\xb3n pendiente.</p></html>'}
        def network(url):
            if url == f'https://{HOST}/robots.txt':
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /privado/\n'
            self.assertIn(url, responses)
            return 200, {'content-type': 'text/html'}, responses[url]
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(Publicacion.objects.filter(fuente=source).count(), 4)
        self.assertEqual(BorradorRastreo.objects.filter(publicacion__fuente=source).count(), 3)
        self.assertTrue(Incidencia.objects.filter(fuente=source, codigo='CANDIDATO_PENDIENTE').exists())
        self.assertTrue(Incidencia.objects.filter(fuente=source, codigo='CANDIDATO_DESCARTADO').exists())
        self.assertFalse(Publicacion.objects.filter(fuente=source, url_original__endswith='noticia').exists())

    def test_page_limit_and_http_backoff(self):
        source = self.register(max_pages=1)
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        def network(url):
            if url.endswith('/robots.txt'):
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow:\n'
            return 200, {'content-type': 'text/html'}, INDEX
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as requested:
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(requested.call_count, 2)
        self.assertTrue(run.incidencias.filter(codigo='INDICE_LIMITE').exists())
        self.assertEqual(Publicacion.objects.filter(fuente=source).count(), 0)
        with patch('rastreo.services.next_due', return_value=None):
            with patch('convocatorias.siau_red.Downloader.once', side_effect=lambda url: (
                    (200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow:\n')
                    if url.endswith('/robots.txt') else (503, {'retry-after': '120'}, b''))):
                later = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        later.refresh_from_db()
        self.assertEqual(later.estado, 'fallida')
        self.assertTrue(later.incidencias.filter(codigo='REINTENTO_FUENTE').exists())

    def test_robots_blocks_generic_page_without_publication(self):
        source = self.register()
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        def network(url):
            if url.endswith('/robots.txt'):
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /becas/listado\n'
            self.assertEqual(url, SEED)
            return 200, {'content-type': 'text/html'}, INDEX
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as requested:
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(Publicacion.objects.filter(fuente=source).count(), 0)
        self.assertTrue(run.incidencias.filter(codigo='ROBOTS').exists())
        self.assertEqual(requested.call_count, 2)
