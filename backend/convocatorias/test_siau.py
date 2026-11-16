import hashlib
import io
import json
import socket
import ssl
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from .siau_bases import REVIEWS, annotate_pdf, compare_pdf
from .siau_extraccion import extract_html, fecha, validate_observation, menciones_academicas
from .siau_red import AccessError, Downloader, INDEX, PAGES, PDFS, ROBOTS, public_address, validate_url, retry_after_at

FIXTURE = Path(__file__).parent / 'fixtures/siau/ficha_sintetica.html'


def observation(text=None):
    return validate_observation(extract_html({
        'contenido': (text if text is not None else FIXTURE.read_text(encoding='utf8')).encode(),
        'url': PAGES[1], 'consulta_utc': '2026-10-26T12:00:00+00:00',
    }), date(2026, 10, 26))


class ExtractionTests(SimpleTestCase):
    def test_different_deadlines_by_modality_do_not_become_shared_open_date(self):
        raw = FIXTURE.read_text(encoding='utf8').replace(
            '25 de octubre, 2026',
            'Programa presencial: 01 de noviembre, 2026</p><p>Programa en linea o hibrida: 30 de noviembre, 2026')
        item = observation(raw)
        self.assertIsNone(item['cierre']['fecha'])
        self.assertEqual([row['fecha'] for row in item['cierres_por_modalidad']], ['2026-11-01', '2026-11-30'])
        self.assertEqual(item['vigencia_observada'], 'desconocida')
        self.assertTrue(any('Cierres diferentes por modalidad' in text for text in item['advertencias']))

    def test_posgrado_and_technological_masters_keep_context(self):
        mentions = menciones_academicas('Programa de Posgrado: programas de maestrías y especializaciones, y maestrías tecnológicas en institutos superiores tecnológicos universitarios.', 'Contar con un título previo de grado. Contar con tercer nivel técnico tecnológico universitario.', PAGES[1])
        offered = [m['expresion_original'] for m in mentions if m['funcion'] == 'oferta_mencionada']
        self.assertEqual(offered, ['maestrías', 'especializaciones', 'maestrías tecnológicas'])
        self.assertTrue(any(m['funcion'] == 'incidental' and 'tecnológicos' in m['expresion_original'] for m in mentions))
        self.assertTrue(any(m['funcion'] == 'formacion_previa' and m['expresion_original'] == 'grado' for m in mentions))
        self.assertTrue(all(m['nivel_normalizado'] is None and m['contexto_original'] for m in mentions))

    def test_ambiguous_mentions_are_not_offered_levels(self):
        mentions = menciones_academicas('Historia de la maestría tecnológica. Posgrado.', '', PAGES[1])
        self.assertTrue(all(m['funcion'] == 'contexto_por_revisar' for m in mentions))
        self.assertEqual(mentions[0]['expresion_original'], 'maestría tecnológica')

    def test_prior_degree_clause_does_not_turn_target_master_into_prior_degree(self):
        mentions = menciones_academicas('', 'Contar con título previo de grado para cursar una maestría tecnológica. No contar con el mismo grado académico.', PAGES[1])
        self.assertEqual([m['funcion'] for m in mentions], ['formacion_previa', 'contexto_por_revisar', 'incidental'])

    def test_fields_with_evidence_and_without_cartesian_options(self):
        item = observation()
        self.assertEqual(item['titulo']['texto_original'], 'PROGRAMA FICTICIO PARA PRUEBAS')
        self.assertIn('MINEDEC', item['entidad_html']['texto_original'])
        self.assertEqual(item['estudios']['destino']['texto_original'], 'Ecuador')
        self.assertEqual(item['estudios']['modalidad']['texto_original'], 'En línea')
        self.assertEqual(item['estudios']['niveles_mencionados'], ['maestrías', 'especializaciones'])
        self.assertEqual(item['opciones'], [])
        self.assertEqual(item['cierre']['url'], PAGES[1])
        self.assertEqual(item['sha256'], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
        self.assertEqual(item['enlaces_bases'][0]['url'], PDFS[1])

    def test_expired_date_has_day_precision_no_time_or_publication(self):
        item = observation()
        self.assertEqual(item['vigencia_observada'], 'vencida')
        self.assertEqual(item['cierre']['fecha'], '2026-10-25')
        self.assertEqual(item['cierre']['precision'], 'dia')
        self.assertIsNone(item['cierre']['hora'])
        self.assertIsNone(item['cierre']['zona_horaria'])
        self.assertIsNone(item['fecha_publicacion'])

    def test_absent_invalid_and_ambiguous_dates_not_permanent(self):
        for value in ('', '31 de febrero de 2026', 'próximamente', '01/02/26'):
            with self.subTest(value=value):
                self.assertIsNone(fecha(value)['fecha'])
        item = observation(FIXTURE.read_text(encoding='utf8').replace('25 de octubre, 2026', 'Sin fecha'))
        self.assertEqual(item['vigencia_observada'], 'desconocida')

    def test_percent_cap_and_unspecified_currency_are_preserved_together(self):
        benefit = observation()['beneficio']
        self.assertEqual(benefit['porcentajes'], ['100%'])
        self.assertEqual(benefit['cantidades'], [{'original': '$3000', 'valor_literal': '3000', 'moneda': None, 'tipo': 'tope'}])
        self.assertIn('Diferencia a cargo', benefit['texto_original'])
        self.assertEqual(benefit['conceptos'], ['matrícula', 'aranceles'])

    def test_explicit_usd_amount_and_period_preserved(self):
        text = FIXTURE.read_text(encoding='utf8').replace('Se cubre el 100% de matrícula y aranceles hasta un valor de $3000.', 'Manutención por una sola vez: USD 828.97.')
        benefit = observation(text)['beneficio']
        self.assertEqual(benefit['cantidades'][0]['moneda'], 'USD')
        self.assertEqual(benefit['cantidades'][0]['tipo'], 'monto_mencionado')
        self.assertIn('por una sola vez', benefit['texto_original'])

    def test_unsupported_requirements_notes_and_external_documents_not_lost(self):
        item = observation()
        self.assertIn('sancionado por desistimiento', item['requisitos']['texto_original'])
        self.assertIn('Nota adicional no estructurable', item['requisitos']['texto_original'])
        self.assertIn('Adjuntar certificado', item['postulacion_y_documentos']['texto_original'])
        self.assertNotIn('Contenido ajeno', item['requisitos']['texto_original'])
        self.assertNotIn('throw new Error', item['texto_ficha'])

    def test_unknown_structure_and_entity_not_inferred_from_navigation(self):
        item = observation('<html><nav>MINEDEC</nav><p>Nuevo diseño</p></html>')
        self.assertEqual(item['entidad_html']['texto_original'], '')
        self.assertFalse(item['seccion_completa'])
        self.assertTrue(any('Estructura inesperada' in x for x in item['advertencias']))

    def test_application_url_not_silently_repaired(self):
        item = observation()
        self.assertTrue(item['enlaces_postulacion'][0]['url'].endswith('login.'))
        self.assertTrue(any('termina en punto' in x for x in item['advertencias']))

    def test_pdf_notes_require_exact_url_and_hash(self):
        self.assertEqual(annotate_pdf(PDFS[1], 'changed')['estado'], 'revision_manual_pendiente')
        self.assertEqual(annotate_pdf('https://example.com/', REVIEWS[PDFS[1]]['sha256'])['estado'], 'revision_manual_pendiente')
        self.assertEqual(annotate_pdf(PDFS[1], REVIEWS[PDFS[1]]['sha256'])['estado'], 'inspeccion_manual_parcial')

    def test_pdf_conflict_keeps_both_dates_and_provenance(self):
        item = observation()
        review = annotate_pdf(PDFS[0], REVIEWS[PDFS[0]]['sha256'])
        compare_pdf(item, review)
        comparison = item['comparaciones_bases'][0]
        self.assertEqual(comparison['resultado'], 'diferencia_para_revision')
        self.assertEqual(comparison['html']['fecha'], '2026-10-25')
        self.assertEqual(comparison['pdf']['fecha'], '2026-06-28')
        self.assertEqual(comparison['pdf']['url'], PDFS[0])
        self.assertEqual(item['cierre']['fecha'], '2026-10-25')

    def test_pdf_economic_difference_does_not_replace_html(self):
        item = observation(FIXTURE.read_text(encoding='utf8').replace('$3000', '$2000'))
        compare_pdf(item, annotate_pdf(PDFS[1], REVIEWS[PDFS[1]]['sha256']))
        comparison = item['comparaciones_bases'][1]
        self.assertEqual(comparison['resultado'], 'diferencia_para_revision')
        self.assertEqual(comparison['html']['cantidades'][0]['original'], '$2000')
        self.assertEqual(comparison['pdf']['tope_literal'], '$3000')


class NetworkTests(SimpleTestCase):
    @patch('convocatorias.siau_red.public_address', return_value='8.8.8.8')
    @patch('convocatorias.siau_red.PinnedHTTPS')
    def test_robots_and_portal_share_request_start_limiter(self, connection, dns):
        clock = [100.0]
        starts = []
        def sleep(seconds):
            clock[0] += seconds
        def request(*args, **kwargs):
            starts.append(clock[0])
            clock[0] += 0.8
        connection.return_value.request.side_effect = request
        response = connection.return_value.getresponse.return_value
        response.status = 200
        response.getheaders.return_value = []
        response.read1.return_value = b''
        downloader = Downloader()
        with patch('convocatorias.siau_red.time.monotonic', side_effect=lambda: clock[0]), patch('convocatorias.siau_red.time.sleep', side_effect=sleep):
            downloader.fetch(ROBOTS)
            downloader.fetch(INDEX)
        self.assertEqual(starts, [100.0, 102.0])
        self.assertEqual([r['inicio_peticion_monotonic'] for r in downloader.history], starts)
        self.assertTrue(all('inicio_peticion_utc' in r for r in downloader.history))

    def test_closed_url_list(self):
        for url in ('http://siau.senescyt.gob.ec/convocatorias/', 'file:///etc/passwd',
                    'https://127.0.0.1/', 'https://[::1]/', 'https://10.0.0.1/',
                    'https://siau.senescyt.gob.ec.evil/convocatorias/', INDEX + '?foo=bar',
                    'https://user:password@siau.senescyt.gob.ec/convocatorias/',
                    'https://pusak.fomentoacademico.gob.ec/cas/login', INDEX + '#fragment', 'https://[invalid'):
            with self.subTest(url=url), self.assertRaises(AccessError):
                validate_url(url)

    def test_dns_mixed_private_loopback_and_linklocal_blocked(self):
        for ip in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', 'fc00::1', '224.0.0.1'):
            records = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443)),
                       (socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))]
            with patch('convocatorias.siau_red.socket.getaddrinfo', return_value=records), self.assertRaises(AccessError):
                public_address('siau.senescyt.gob.ec')

    def test_external_redirect_blocked_before_second_request(self):
        downloader = Downloader()
        with patch.object(downloader, 'once', return_value=(302, {'location': 'http://127.0.0.1/'}, b'')) as request:
            with self.assertRaises(AccessError):
                downloader.fetch(PAGES[0])
            self.assertEqual(request.call_count, 1)

    def test_allowed_redirect_still_checks_robots(self):
        downloader = Downloader()
        with patch.object(downloader, 'once', return_value=(302, {'location': PAGES[1]}, b'')) as request:
            with self.assertRaises(AccessError):
                downloader.fetch(PAGES[0], can_fetch=lambda url: url == PAGES[0])
            self.assertEqual(request.call_count, 1)

    def test_malformed_redirect_is_controlled(self):
        downloader = Downloader()
        with patch.object(downloader, 'once', return_value=(302, {'location': 'https://[invalid'}, b'')):
            with self.assertRaisesMessage(AccessError, 'mal formada'):
                downloader.fetch(PAGES[0])

    def test_http_errors_and_retry_limit(self):
        for status, attempts in ((404, 1), (403, 1), (429, 1), (503, 1)):
            downloader = Downloader()
            with patch.object(downloader, 'once', return_value=(status, {}, b'')) as request:
                with self.assertRaisesMessage(AccessError, f'HTTP {status}'):
                    downloader.fetch(PAGES[0])
                self.assertEqual(request.call_count, attempts)

    def test_retry_after_blocks_immediate_retry(self):
        moment = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        self.assertEqual(retry_after_at({'retry-after': '300'}, moment),
                         datetime(2026, 11, 11, 12, 5, tzinfo=timezone.utc))
        self.assertEqual(retry_after_at({'retry-after': 'Wed, 11 Nov 2026 13:00:00 GMT'}, moment),
                         datetime(2026, 11, 11, 13, tzinfo=timezone.utc))
        self.assertIsNone(retry_after_at({'retry-after': 'invalid'}, moment))
        for status in (429, 503):
            downloader = Downloader()
            with patch.object(downloader, 'once', return_value=(status, {'retry-after': '300'}, b'')) as request:
                with self.assertRaises(AccessError):
                    downloader.fetch(PAGES[0])
                request.assert_called_once()

    def test_timeout_bounded_and_tls_error_not_bypassed(self):
        for error, attempts in ((TimeoutError(), 2), (ssl.SSLError(), 1)):
            downloader = Downloader()
            with patch.object(downloader, 'once', side_effect=error) as request:
                with self.assertRaises(AccessError):
                    downloader.fetch(PAGES[0])
                self.assertEqual(request.call_count, attempts)

    @patch('convocatorias.siau_red.public_address', return_value='8.8.8.8')
    @patch('convocatorias.siau_red.PinnedHTTPS')
    def test_size_limit_and_connection_closed(self, connection, dns):
        response = connection.return_value.getresponse.return_value
        response.getheaders.return_value = [('content-length', str(2 * 1024 * 1024 + 1))]
        with self.assertRaisesMessage(AccessError, 'tamaño'):
            Downloader().once(PAGES[0])
        connection.return_value.close.assert_called_once()
        response.read1.assert_not_called()

    @patch('convocatorias.siau_red.public_address', return_value='8.8.8.8')
    @patch('convocatorias.siau_red.PinnedHTTPS')
    def test_stream_without_content_length_is_also_bounded(self, connection, dns):
        response = connection.return_value.getresponse.return_value
        response.getheaders.return_value = []
        response.read1.return_value = b'x' * 65536
        with self.assertRaisesMessage(AccessError, 'tamaño'):
            Downloader().once(PAGES[0])
        self.assertEqual(response.read1.call_count, 33)


class CommandTests(SimpleTestCase):
    # SimpleTestCase prohíbe TODAS las consultas BD: ni lectura ni escritura.
    def fake_fetch(self, url, can_fetch=lambda url: True):
        if not can_fetch(url):
            raise AccessError('robots impide acceso')
        content, mime = FIXTURE.read_bytes(), 'text/html'
        if url == ROBOTS:
            content, mime = b'User-agent: *\nDisallow: /wp-admin/\n', 'text/plain'
        if url in PDFS:
            content, mime = b'%PDF-1.4\nFIXTURE SINTETICA NO DOCUMENTO REAL', 'application/pdf'
        return {'contenido': content, 'url': url, 'url_solicitada': url,
                'consulta_utc': '2026-10-26T12:00:00+00:00', 'content_type': mime}

    def test_command_writes_only_files_no_database_and_never_pusak(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(BASE_DIR=Path(folder) / 'backend'), patch('convocatorias.siau_red.Downloader.fetch', side_effect=self.fake_fetch) as fetch:
            call_command('previsualizar_siau', stdout=io.StringIO())
            report = json.loads(next(Path(folder).rglob('informe.json')).read_text(encoding='utf8'))
            self.assertEqual(len(report['fichas']), 2)
            self.assertEqual(report['estado'], 'completa_con_revision_manual_pendiente')
            self.assertEqual(report['fichas'][0]['bases'][0]['estado'], 'revision_manual_pendiente')
            self.assertFalse(any('pusak' in call.args[0] for call in fetch.call_args_list))
            self.assertEqual(sum(call.args[0] in PDFS for call in fetch.call_args_list), 1)
            self.assertTrue(next(Path(folder).rglob('informe.txt')).exists())

    def test_robots_failure_stops_and_records_real_error_without_fixture_fallback(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(BASE_DIR=Path(folder) / 'backend'), patch('convocatorias.siau_red.Downloader.fetch', side_effect=AccessError('HTTP 403')) as fetch:
            with self.assertRaises(CommandError):
                call_command('previsualizar_siau', stdout=io.StringIO())
            self.assertEqual(fetch.call_count, 1)
            report = json.loads(next(Path(folder).rglob('informe.json')).read_text(encoding='utf8'))
            self.assertEqual(report['estado'], 'fallida')
            self.assertEqual(report['fichas'], [])
            self.assertIn('403', report['incidencias'][0]['error'])

    def test_unlisted_base_is_not_downloaded(self):
        original = self.fake_fetch
        def changed(url, **kwargs):
            result = original(url, **kwargs)
            if url in PAGES:
                result['contenido'] = result['contenido'].replace(PDFS[1].split('.ec')[1].encode(), b'https://127.0.0.1/base.pdf')
            return result
        with tempfile.TemporaryDirectory() as folder, override_settings(BASE_DIR=Path(folder) / 'backend'), patch('convocatorias.siau_red.Downloader.fetch', side_effect=changed) as fetch:
            with self.assertRaises(CommandError):
                call_command('previsualizar_siau', stdout=io.StringIO())
            self.assertEqual(fetch.call_count, 4)  # robots, índice, dos fichas
            report = json.loads(next(Path(folder).rglob('informe.json')).read_text(encoding='utf8'))
            self.assertEqual(report['estado'], 'parcial')

    def test_malformed_html_link_records_failure_and_retains_original(self):
        original = self.fake_fetch
        def changed(url, **kwargs):
            result = original(url, **kwargs)
            if url in PAGES:
                result['contenido'] = result['contenido'].replace(b'https://pusak.fomentoacademico.gob.ec/cas/login.', b'https://[invalid')
            return result
        with tempfile.TemporaryDirectory() as folder, override_settings(BASE_DIR=Path(folder) / 'backend'), patch('convocatorias.siau_red.Downloader.fetch', side_effect=changed):
            with self.assertRaises(CommandError):
                call_command('previsualizar_siau', stdout=io.StringIO())
            report = json.loads(next(Path(folder).rglob('informe.json')).read_text(encoding='utf8'))
            self.assertEqual(report['estado'], 'fallida')
            self.assertEqual(len(report['incidencias']), 2)
            self.assertEqual(len(list(Path(folder).rglob('ficha-*.html'))), 2)
