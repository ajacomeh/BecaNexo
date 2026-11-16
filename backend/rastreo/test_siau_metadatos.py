"""Metadatos de tarjetas SIAU: respuestas simuladas y base aislada."""
import uuid
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs
import json

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from . import tests as base
from .models import CandidatoIndice, Documento, Publicacion, Version, Ejecucion, Incidencia
from .services import enable_discovery, enable_national_discovery
from .siau_metadatos import report, consultar_una_vez, capturar_metadatos, last_completed_page
from .siau_ajax import AJAX_INDEX
from convocatorias.siau_red import ROBOTS, NATIONAL_INDEX, AccessError
from convocatorias.models import Convocatoria


def cards(*pairs):
    return ''.join(f'<article class="category-convocatorias"><h2 class="entry-title">'
                   f'<a href="https://siau.senescyt.gob.ec/{slug}/">{title}</a></h2></article>'
                   for slug, title in pairs).encode()


class MetadataReportTests(SimpleTestCase):
    def test_live_reader_uses_only_public_index_and_one_ajax_page(self):
        from .test_ajax_pagination import index
        seen = []

        def get(url):
            seen.append(url)
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, (
                    b'User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n')
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, index()
            raise AssertionError('No se debe descargar ninguna ficha.')

        with patch('rastreo.siau_metadatos.Downloader.once', side_effect=get), patch(
                'rastreo.siau_metadatos.Downloader.post_once', return_value=(
                    200, {'content-type': 'text/html'}, cards(('becas-pagina-dos', 'Becas Página Dos')))) as post:
            result = consultar_una_vez()
        self.assertEqual(seen, [ROBOTS, NATIONAL_INDEX])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], AJAX_INDEX)
        self.assertEqual(result['documentos_descargados'], 0)

    def test_robots_block_prevents_index_and_ajax(self):
        with patch('rastreo.siau_metadatos.Downloader.once', return_value=(
                200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /wp-admin/\n')) as get, patch(
                'rastreo.siau_metadatos.Downloader.post_once') as post:
            with self.assertRaises(AccessError):
                consultar_una_vez()
        self.assertEqual(get.call_count, 1)
        post.assert_not_called()

    def test_keeps_only_factual_index_fields_and_deduplicates(self):
        first = cards(('programa-de-becas-ejemplo', 'Programa de Becas Ejemplo'),
                      ('noticia-general', 'Noticia general'))
        second = cards(('programa-de-becas-ejemplo', 'Programa de Becas Ejemplo'),
                       ('becas-ejemplo-dos', 'Becas Ejemplo Dos'))
        result = report(first, second)
        self.assertEqual(len(result['candidatos']), 2)
        self.assertEqual({item['pagina'] for item in result['candidatos']}, {1, 2})
        self.assertTrue(all(item['estado'] == 'pendiente' and len(item['respuesta_sha256']) == 64
                            for item in result['candidatos']))
        self.assertFalse(result['contenido_conservado'])
        self.assertEqual(result['documentos_descargados'], 0)
        self.assertEqual(result['borradores_creados'], 0)

    def test_budget_is_shared_between_pages(self):
        first = cards(*[(f'becas-primera-{i}', f'Becas Primera {i}') for i in range(20)])
        second = cards(*[(f'becas-segunda-{i}', f'Becas Segunda {i}') for i in range(20)])
        result = report(first, second)
        self.assertEqual(len(result['candidatos']), 12)
        self.assertEqual([item['pagina'] for item in result['candidatos']].count(1), 6)
        self.assertEqual([item['pagina'] for item in result['candidatos']].count(2), 6)
        self.assertTrue(result['cobertura_parcial'])

    def test_progresses_one_ajax_page_and_skips_known_cards(self):
        from .test_ajax_pagination import index
        first = index() + cards(('beca-indice-nueva', 'Beca Índice Nueva'))
        seen = []

        def get(url):
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, (
                    b'User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n')
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, first
            raise AssertionError('No se deben leer fichas.')

        def post(url, body):
            page = json.loads(parse_qs(body.decode())['template_vars'][0])['query_args']['paged']
            seen.append(page)
            return 200, {'content-type': 'text/html'}, cards((f'beca-pagina-{page}', f'Beca Página {page}'))

        with patch('rastreo.siau_metadatos.Downloader.once', side_effect=get), patch(
                'rastreo.siau_metadatos.Downloader.post_once', side_effect=post):
            first_run = consultar_una_vez()
            known = {item['url'] for item in first_run['candidatos']}
            second_run = consultar_una_vez(first_run['pagina_ajax'], known)
            third_run = consultar_una_vez(second_run['pagina_ajax'], known | {
                item['url'] for item in second_run['candidatos']})
        self.assertEqual(seen, [2, 3, 2])
        self.assertEqual(first_run['pagina_ajax'], 2)
        self.assertEqual([item['pagina'] for item in second_run['candidatos']], [3])
        self.assertEqual(third_run['candidatos'], [])
        self.assertEqual(second_run['duplicados_conocidos'], 2)
        self.assertEqual(second_run['documentos_descargados'], 0)


class MetadataCaptureTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source

    def test_audited_preview_does_not_create_fiches_documents_or_drafts(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_fusion_db')
        previous_offers = Convocatoria.objects.count()
        source = self.source()
        enable_discovery(self.actor.pk, 'Preparar índice de pruebas')
        enable_national_discovery(self.actor.pk, 'Preparar nacionales de pruebas')
        sample = report(cards(('programa-de-becas-ejemplo', 'Programa de Becas Ejemplo')))
        key = uuid.uuid4()
        with patch('rastreo.siau_metadatos.consultar_una_vez', return_value=sample):
            run = capturar_metadatos(source.pk, self.actor.pk, key, 'Prueba aislada')
            same = capturar_metadatos(source.pk, self.actor.pk, key, 'Prueba aislada')
        self.assertEqual(same.pk, run.pk)
        self.assertEqual(CandidatoIndice.objects.count(), 1)
        self.assertEqual(CandidatoIndice.objects.get().ultima_ejecucion_id, run.pk)
        self.assertEqual(run.configuracion_snapshot['consulta_limitada']['modo'], 'metadatos_indice/4')
        self.assertEqual(Publicacion.objects.count(), 0)
        self.assertEqual(Version.objects.count(), 0)
        self.assertEqual(Documento.objects.count(), 0)
        self.assertEqual(Convocatoria.objects.count(), previous_offers)
        with patch('rastreo.siau_metadatos.consultar_una_vez') as read:
            with self.assertRaises(ValidationError):
                capturar_metadatos(source.pk, self.actor.pk, uuid.uuid4(), 'Intento prematuro')
            read.assert_not_called()

    def test_completed_cursor_survives_failed_run_without_advancing(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_fusion_db')
        source = self.source()
        enable_discovery(self.actor.pk, 'Preparar índice de pruebas')
        enable_national_discovery(self.actor.pk, 'Preparar nacionales de pruebas')
        sample = report(cards(('beca-uno', 'Beca Uno')),
                        cards(('beca-dos', 'Beca Dos')), ajax_page=2, max_pages=3)
        with patch('rastreo.siau_metadatos.consultar_una_vez', return_value=sample):
            run = capturar_metadatos(source.pk, self.actor.pk, uuid.uuid4(), 'Primera consulta aislada')
        run.refresh_from_db()
        self.assertEqual(last_completed_page(source), 2)
        started = timezone.now()
        failed = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor, origen='manual',
                                          inicio=started, estado='fallida', fin=started + timedelta(seconds=1),
                                          version_extractor='siau-index-meta/1',
                                          configuracion_snapshot={'consulta_limitada': {'modo': 'metadatos_indice/4'}})
        Incidencia.objects.create(fuente=source, ejecucion=failed, codigo='METADATOS_FALLIDOS',
                                  gravedad='error', detalle='AccessError')
        self.assertEqual(last_completed_page(source), 2)
        self.assertEqual(CandidatoIndice.objects.filter(ultima_ejecucion=run).count(), 2)
