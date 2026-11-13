"""Paginación nacional simulada: escrituras solo en bases de pruebas aisladas."""
import html
import io
import hashlib
import json
import uuid
from unittest.mock import patch
from urllib.parse import parse_qs

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, transaction, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase

from convocatorias.siau_red import Downloader, INDEX, NATIONAL_INDEX, ROBOTS
from . import tests as base
from .models import Acceso, Ejecucion, Publicacion, Revision
from .services import enable_discovery, enable_national_discovery, run_manual, set_paginated_discovery, summary
from .siau_ajax import AJAX_INDEX, ajax_request, grid_config, robots_allow_ajax


PAGE = 'https://siau.senescyt.gob.ec/oferta-de-becas-nacionales-educacion-continua-prueba/'
ROBOTS_ALLOW = b'User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n'


def card(url=PAGE):
    return (f'<article class="category-convocatorias"><h2 class="entry-title"><a href="{url}">'
            'Oferta de Becas Nacionales para Educacion Continua</a></h2></article>').encode()


def public_config(max_pages=3):
    return {'action': 'us_ajax_grid', 'infinite_scroll': 0, 'max_num_pages': max_pages,
            'pagination': 'ajax', 'template_vars': {'query_args': {
                'post_type': ['post'], 'tax_query': [{'field': 'slug', 'taxonomy': 'category',
                                                     'terms': ['convocatorias']}], 'paged': 1}}}


def index(max_pages=3):
    config = public_config(max_pages)
    return card() + (f'<div class="w-grid-json" onclick="return {html.escape(json.dumps(config))}"></div>').encode()


class AjaxContractTests(SimpleTestCase):
    def test_transport_is_bounded_and_does_not_send_credentials(self):
        class Response:
            status = 200

            def getheaders(self):
                return [('Content-Type', 'text/html')]

            def read1(self, size):
                if not hasattr(self, 'read'):
                    self.read = True
                    return b'<article></article>'
                return b''

        class Connection:
            def __init__(self, *args):
                self.request_data = None

            def request(self, *args, **kwargs):
                self.request_data = args, kwargs

            def getresponse(self):
                return Response()

            def close(self):
                pass

        conn = Connection()
        downloader = Downloader(allowed_urls={AJAX_INDEX})
        with patch('convocatorias.siau_red.public_address', return_value='1.1.1.1'), patch(
                'convocatorias.siau_red.PinnedHTTPS', return_value=conn):
            status, _, content = downloader.post_once(AJAX_INDEX, b'action=us_ajax_grid')
        self.assertEqual(status, 200)
        self.assertEqual(content, b'<article></article>')
        self.assertEqual(conn.request_data[0][0], 'POST')
        self.assertNotIn('cookie', str(conn.request_data).casefold())
        self.assertNotIn('authorization', str(conn.request_data).casefold())

    def test_public_contract_and_robots_specificity(self):
        config = grid_config(index())
        body, evidence = ajax_request(config, 2)
        self.assertEqual(parse_qs(body.decode())['action'], ['us_ajax_grid'])
        self.assertEqual(json.loads(parse_qs(body.decode())['template_vars'][0])['query_args']['paged'], 2)
        self.assertEqual(evidence['pagina'], 2)
        self.assertEqual(evidence['solicitud_sha256'], hashlib.sha256(body).hexdigest())
        self.assertNotIn('template_vars', evidence['parametros'])
        self.assertTrue(robots_allow_ajax(ROBOTS_ALLOW))
        self.assertTrue(robots_allow_ajax(ROBOTS_ALLOW + b'Disallow: /wp-admin/admin-ajax.php/private\n'))
        self.assertFalse(robots_allow_ajax(b'User-agent: *\nDisallow: /wp-admin/admin-ajax.php\nAllow: /wp-admin/\n'))
        self.assertFalse(robots_allow_ajax(b'User-agent: *\nDisallow: /wp-admin/\n'))
        self.assertTrue(robots_allow_ajax(b'User-agent: *\nDisallow: /wp-admin/*\nAllow: /wp-admin/admin-ajax.php$\n'))

    def test_unknown_or_private_contract_fails_closed(self):
        from convocatorias.siau_red import AccessError
        for bad in (b'<html></html>', index().replace(b'us_ajax_grid', b'other_action'),
                    index().replace(b'query_args', b'nonce')):
            with self.assertRaises(AccessError):
                grid_config(bad)
        self.assertFalse(robots_allow_ajax(ROBOTS_ALLOW + b'Unknown: x\n'))

    def test_sensitive_values_and_encoded_nested_data_fail_closed(self):
        from convocatorias.siau_red import AccessError
        from copy import deepcopy

        def encoded(config):
            return (f'<div class="w-grid-json" onclick="return '
                    f'{html.escape(json.dumps(config))}"></div>').encode()

        for value in ('token=synthetic', '%74oken%3Dsynthetic', '%2574oken%253Dsynthetic',
                      '&#116;oken=synthetic', 'dG9rZW49c3ludGhldGlj', 'x' * 513,
                      '{"session":"synthetic"}'):
            config = deepcopy(public_config())
            config['template_vars']['img_size'] = value
            with self.subTest(value_length=len(value)), self.assertRaises(AccessError):
                grid_config(encoded(config))
            with self.assertRaises(AccessError):
                ajax_request(config, 2)
        for path, value in ((('template_vars', 'token'), 'synthetic'),
                            (('template_vars', 'query_args', 'cookie'), 'synthetic')):
            config = deepcopy(public_config())
            target = config
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.assertRaises(AccessError):
                grid_config(encoded(config))


class AjaxPaginationTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake

    def configured(self):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        source = self.source()
        enable_discovery(self.actor.pk, 'Prueba indice')
        enable_national_discovery(self.actor.pk, 'Prueba nacionales')
        return source

    def network(self, url):
        if url == ROBOTS:
            return 200, {'content-type': 'text/plain'}, ROBOTS_ALLOW
        if url == INDEX:
            return 200, {'content-type': 'text/html'}, b'<html></html>'
        if url == NATIONAL_INDEX:
            return 200, {'content-type': 'text/html'}, index()
        if url == PAGE:
            from .test_periodico import national_ficha
            return 200, {'content-type': 'text/html'}, national_ficha()
        return self.fake(url)

    def test_migration_fills_historical_get_access(self):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        source = self.source()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        access_id = run.accesos.order_by('id').first().pk
        old = [('rastreo', '0012_permitir_rectificaciones_integracion')]
        new = [('rastreo', '0013_acceso_metodo_parametros')]
        try:
            MigrationExecutor(connection).migrate(old)
        finally:
            MigrationExecutor(connection).migrate(new)
        access = Acceso.objects.get(pk=access_id)
        self.assertEqual(access.metodo, 'GET')
        self.assertIsNone(access.parametros_publicos)

    def test_audited_transition_and_legacy_get(self):
        source = self.configured()
        with self.assertRaises(ValidationError):
            set_paginated_discovery(self.user.pk, 'Sin permiso', True)
        key = uuid.uuid4()
        source, changed = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True, key)
        self.assertTrue(changed)
        self.assertEqual(source.politica_version, 'siau-nacionales/4')
        self.assertFalse(source.aprobada_publicacion_automatica)
        self.assertFalse(set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True, key)[1])
        with self.assertRaises(ValidationError):
            set_paginated_discovery(self.actor.pk, 'Otro motivo', True, key)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.network), patch(
                'convocatorias.siau_red.Downloader.post_once', return_value=(200, {'content-type': 'text/html'}, card())):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'parcial')  # página 3 aún sin consultar
        self.assertTrue(run.accesos.filter(metodo='GET', parametros_publicos__isnull=True).exists())
        post = run.accesos.get(metodo='POST')
        self.assertEqual(post.parametros_publicos['pagina'], 2)
        self.assertIsNotNone(post.documento_id)
        self.assertNotIn('token', json.dumps(post.parametros_publicos).casefold())
        self.assertNotIn('template_vars', post.parametros_publicos['parametros'])
        with self.assertRaises(DatabaseError), transaction.atomic():
            Acceso.objects.filter(pk=post.pk).update(parametros_publicos={'pagina': 99})
        with self.assertRaises(DatabaseError), transaction.atomic():
            Ejecucion.objects.filter(pk=run.pk).update(configuracion_snapshot={'alterado': True})
        self.assertIsNone(Publicacion.objects.get(url_normalizada=PAGE).convocatoria_id)
        self.assertTrue(Revision.objects.filter(clave_accion=key).exists())
        source, changed = set_paginated_discovery(self.actor.pk, 'Reversión de prueba', False)
        self.assertTrue(changed)
        self.assertEqual(source.politica_version, 'siau-nacionales/3')
        self.assertEqual(Acceso.objects.get(pk=post.pk).parametros_publicos['pagina'], 2)

    def test_cursor_retries_failed_page_and_wraps_without_duplicates(self):
        source = self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)
        observed = []

        def post(url, body):
            page = json.loads(parse_qs(body.decode())['template_vars'][0])['query_args']['paged']
            observed.append(page)
            if len(observed) == 2:
                return 503, {'retry-after': '120'}, b''
            return 200, {'content-type': 'text/html'}, card()

        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.network), patch(
                'convocatorias.siau_red.Downloader.post_once', side_effect=post):
            runs = [run_manual(source.pk, self.actor.pk, uuid.uuid4()) for _ in range(4)]
        self.assertEqual(observed, [2, 3, 3, 2])
        runs[1].refresh_from_db()
        self.assertEqual(runs[1].estado, 'fallida')
        self.assertTrue(runs[1].incidencias.filter(codigo='REINTENTO_FUENTE').exists())
        self.assertEqual(runs[2].accesos.get(metodo='POST').parametros_publicos['pagina'], 3)
        self.assertEqual(Publicacion.objects.filter(url_normalizada=PAGE).count(), 1)
        self.assertEqual(Publicacion.objects.get(url_normalizada=PAGE).versiones.count(), 1)

    def test_reordering_and_new_cards_do_not_duplicate_publications(self):
        source = self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)
        second = PAGE.replace('continua-prueba', 'continua-segunda')
        rounds = [0]

        def network(url):
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, index() + (card(second) if rounds[0] else b'')
            if url == second:
                from .test_periodico import national_ficha
                return 200, {'content-type': 'text/html'}, national_ficha()
            return self.network(url)

        def post(url, body):
            return 200, {'content-type': 'text/html'}, card(second) + card(PAGE) if rounds[0] else card(PAGE)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network), patch(
                'convocatorias.siau_red.Downloader.post_once', side_effect=post):
            run_manual(source.pk, self.actor.pk, uuid.uuid4())
            rounds[0] = 1
            second_run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(Publicacion.objects.filter(url_normalizada__in=[PAGE, second]).count(), 2)
        self.assertEqual(Publicacion.objects.get(url_normalizada=PAGE).versiones.count(), 1)
        self.assertEqual(Publicacion.objects.get(url_normalizada=second).versiones.count(), 1)
        self.assertEqual(second_run.accesos.filter(url_normalizada=second, documento__isnull=False).count(), 1)

    def test_429_preserves_cursor_and_retry_after(self):
        source = self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.network), patch(
                'convocatorias.siau_red.Downloader.post_once', return_value=(429, {'retry-after': '180'}, b'')):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertTrue(run.incidencias.filter(codigo='REINTENTO_FUENTE').exists())
        self.assertEqual(run.accesos.get(metodo='POST').parametros_publicos['pagina'], 2)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.network), patch(
                'convocatorias.siau_red.Downloader.post_once', return_value=(200, {'content-type': 'text/html'}, card())):
            following = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(following.accesos.get(metodo='POST').parametros_publicos['pagina'], 2)

    def test_fiche_budget_and_review_only(self):
        source = self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)
        urls = [PAGE.replace('continua-prueba', f'continua-prueba-{number}') for number in range(13)]

        def network(url):
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, index() + b''.join(card(url) for url in urls)
            if url in urls:
                from .test_periodico import national_ficha
                return 200, {'content-type': 'text/html'}, national_ficha()
            return self.network(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network), patch(
                'convocatorias.siau_red.Downloader.post_once', return_value=(200, {'content-type': 'text/html'}, card())):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertLessEqual(run.accesos.filter(rol='ficha').count(), 12)
        self.assertLessEqual(run.accesos.filter(rol='bases').count(), 24)
        self.assertFalse(Publicacion.objects.exclude(convocatoria=None).exists())
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network), patch(
                'convocatorias.siau_red.Downloader.post_once', return_value=(200, {'content-type': 'text/html'}, card())):
            run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertTrue(all(Publicacion.objects.filter(url_normalizada=url).exists() for url in urls))

    def test_robots_blocks_ajax_and_v3_does_not_post(self):
        source = self.configured()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.network), patch(
                'convocatorias.siau_red.Downloader.post_once') as post:
            run_manual(source.pk, self.actor.pk, uuid.uuid4())
            post.assert_not_called()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)

        def disallowed(url):
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /wp-admin/\n'
            return self.network(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=disallowed), patch(
                'convocatorias.siau_red.Downloader.post_once') as post:
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
            post.assert_not_called()
        self.assertTrue(run.incidencias.filter(codigo='ROBOTS').exists())

    def test_rejected_private_value_is_neither_sent_nor_persisted(self):
        source = self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)
        config = public_config()
        config['template_vars']['img_size'] = 'dG9rZW49c3ludGhldGlj'
        bad_index = card() + (f'<div class="w-grid-json" onclick="return '
                              f'{html.escape(json.dumps(config))}"></div>').encode()

        def network(url):
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, bad_index
            return self.network(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network), patch(
                'convocatorias.siau_red.Downloader.post_once') as post:
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
            post.assert_not_called()
        self.assertFalse(run.accesos.filter(metodo='POST').exists())
        self.assertTrue(run.incidencias.filter(codigo='INDICE_ESTRUCTURA').exists())
        self.assertFalse(run.accesos.filter(url_normalizada=NATIONAL_INDEX, documento__isnull=False).exists())
        self.assertNotIn('synthetic', json.dumps(list(run.incidencias.values('detalle'))).casefold())

    def test_cli_transition_runs_only_on_test_database(self):
        source = self.configured()
        output = io.StringIO()
        call_command('rastreo', 'habilitar-paginacion', actor_id=self.actor.pk,
                     motivo='Prueba CLI', stdout=output)
        self.assertIn('siau-nacionales/4', output.getvalue())
        source.refresh_from_db()
        self.assertEqual(source.frecuencia_min, 1440)
