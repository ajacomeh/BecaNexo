"""Ensayo de 720 minutos exclusivamente en la base aislada."""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from convocatorias.models import Convocatoria
from convocatorias.siau_red import INDEX, NATIONAL_INDEX, ROBOTS
from . import tests as base
from .models import Ejecucion, Acceso
from .services import (enable_discovery, enable_national_discovery, next_due,
                       run_manual, run_scheduled, set_frequency, snapshot)
from .test_periodico import national_index, national_ficha, NATIONAL_PAGE


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class TwelveHourFrequencyTests(TransactionTestCase):
    setUpBase = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake

    def setUp(self):
        self.setUpBase()
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_fusion_db')
        self.source_row = self.source()
        enable_discovery(self.actor.pk, 'Índice de prueba')
        enable_national_discovery(self.actor.pk, 'Nacionales de prueba')
        self.source_row, changed = set_frequency(self.source_row.pk, self.actor.pk,
                                                 'Ensayo aislado de doce horas', 720)
        self.assertFalse(changed)
        self.assertEqual(self.source_row.politica_version, 'siau-nacionales/3')
        self.now = timezone.now().replace(microsecond=0)

    def previous(self, *, hours=12, state='finalizada', extraordinary=False):
        started = self.now - timedelta(hours=hours)
        configuration = snapshot(self.source_row.pk)
        if extraordinary:
            configuration['solicitud_extraordinaria'] = {'motivo': 'simulado'}
        return Ejecucion.objects.create(fuente=self.source_row, origen='programada',
            clave_idempotencia=uuid.uuid4(), inicio=started,
            fin=None if state == 'en_curso' else started, estado=state,
            configuracion_snapshot=configuration, version_extractor='siau-html/2')

    def test_before_and_at_twelve_hours_with_synthetic_http(self):
        previous = self.previous()
        calls = []
        def network(url):
            calls.append(url)
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, national_index()
            if url == NATIONAL_PAGE:
                return 200, {'content-type': 'text/html'}, national_ficha()
            return self.fake(url)
        with patch('rastreo.services.timezone.now', return_value=self.now - timedelta(seconds=1)), patch(
                'convocatorias.siau_red.Downloader.once', side_effect=network):
            self.assertEqual(run_scheduled(self.source_row.pk).pk, previous.pk)
        self.assertEqual(calls, [])
        with patch('rastreo.services.timezone.now', return_value=self.now), patch(
                'convocatorias.siau_red.Downloader.once', side_effect=network), patch(
                'convocatorias.siau_red.time.sleep'):
            result = run_scheduled(self.source_row.pk)
        result.refresh_from_db()
        self.assertNotEqual(result.pk, previous.pk)
        self.assertIn(result.estado, ('finalizada', 'parcial'))
        self.assertIn(NATIONAL_INDEX, calls)
        self.assertFalse(Convocatoria.objects.filter(fecha_publicacion__isnull=False).exists())
        self.source_row.refresh_from_db()
        self.assertEqual(self.source_row.politica_version, 'siau-nacionales/3')
        self.assertFalse(self.source_row.aprobada_publicacion_automatica)

    def test_retry_after_longer_than_twelve_hours_wins(self):
        self.previous()
        expected = self.now + timedelta(hours=18)
        from .models import Incidencia
        Incidencia.objects.create(fuente=self.source_row, codigo='REINTENTO_FUENTE',
                                  gravedad='aviso', detalle=expected.isoformat())
        self.assertEqual(next_due(self.source_row), expected)
        with patch('rastreo.services.timezone.now', return_value=self.now + timedelta(hours=12)), patch(
                'convocatorias.siau_red.Downloader.once') as network:
            result = run_scheduled(self.source_row.pk)
        self.assertEqual(result.pk, Ejecucion.objects.exclude(estado='omitida').order_by('-inicio').first().pk)
        network.assert_not_called()

    def test_concurrent_execution_does_not_start_another_capture(self):
        active = self.previous(hours=13, state='en_curso')
        with patch('rastreo.services.timezone.now', return_value=self.now), patch(
                'convocatorias.siau_red.Downloader.once') as network:
            result = run_scheduled(self.source_row.pk)
        self.assertEqual(result.estado, 'omitida')
        self.assertEqual(active.estado, 'en_curso')
        network.assert_not_called()

    def test_http_503_with_long_retry_after_blocks_twelve_hour_window(self):
        calls = []
        def response(url):
            calls.append(url)
            self.assertEqual(url, ROBOTS)
            return 503, {'retry-after': '64800', 'content-type': 'text/plain'}, b''
        with patch('convocatorias.siau_red.Downloader.once', side_effect=response):
            failed = run_scheduled(self.source_row.pk)
        failed.refresh_from_db()
        self.assertEqual(failed.estado, 'fallida')
        self.assertEqual(calls, [ROBOTS])
        self.assertTrue(Acceso.objects.filter(ejecucion=failed, http_status=503).exists())
        self.assertGreater(next_due(self.source_row), failed.inicio + timedelta(hours=17))
        with patch('rastreo.services.timezone.now', return_value=failed.inicio + timedelta(hours=12)), patch(
                'convocatorias.siau_red.Downloader.once') as network:
            repeated = run_scheduled(self.source_row.pk)
        self.assertEqual(repeated.pk, failed.pk)
        network.assert_not_called()

    def test_direct_manual_cli_uses_same_twelve_hour_window(self):
        previous = self.previous()
        with patch('rastreo.services.timezone.now', return_value=self.now - timedelta(seconds=1)), patch(
                'convocatorias.siau_red.Downloader.once') as network:
            early = run_manual(self.source_row.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(early.estado, 'omitida')
        network.assert_not_called()
        self.assertEqual(next_due(self.source_row), self.now)
        with patch('rastreo.services.timezone.now', return_value=self.now), patch(
                'convocatorias.siau_red.Downloader.once', side_effect=self.fake) as network, patch(
                'convocatorias.siau_red.time.sleep'):
            ready = run_manual(self.source_row.pk, self.actor.pk, uuid.uuid4())
        ready.refresh_from_db()
        self.assertNotIn(ready.estado, ('omitida', 'en_curso'))
        self.assertNotEqual(ready.pk, previous.pk)
        self.assertTrue(network.called)

    def test_extraordinary_capture_also_consumes_configured_window(self):
        previous = self.previous(extraordinary=True)
        from .web_frequency import manual_window
        with override_settings(RASTREO_EXTRAORDINARIO_HABILITADO=True,
                               RASTREO_WEB_LAUNCH_ROOT=self.temp.name):
            self.assertEqual(next_due(self.source_row), self.now)
            self.assertGreaterEqual(manual_window(self.source_row), self.now)
            with patch('rastreo.services.timezone.now', return_value=self.now - timedelta(seconds=1)), patch(
                    'convocatorias.siau_red.Downloader.once') as network:
                manual = run_manual(self.source_row.pk, self.actor.pk, uuid.uuid4(),
                                    {'modalidad': 'extraordinaria', 'motivo': 'simulado'})
                scheduled = run_scheduled(self.source_row.pk)
            self.assertEqual(manual.estado, 'omitida')
            self.assertEqual(scheduled.pk, previous.pk)
            network.assert_not_called()

    def test_429_without_retry_after_blocks_all_entrypoints(self):
        previous = self.previous(hours=13, state='en_curso')
        Acceso.objects.create(ejecucion=previous, secuencia=1, rol='indice',
            url_original=INDEX, url_normalizada=INDEX, admitido_en=previous.inicio,
            fin=previous.inicio, http_status=429, resultado='error')
        Ejecucion.objects.filter(pk=previous.pk).update(estado='fallida', fin=self.now - timedelta(hours=13))
        with patch('convocatorias.siau_red.Downloader.once') as network:
            manual = run_manual(self.source_row.pk, self.actor.pk, uuid.uuid4())
            scheduled = run_scheduled(self.source_row.pk)
            from .siau_metadatos import capturar_metadatos
            from django.core.exceptions import ValidationError
            with self.assertRaises(ValidationError):
                capturar_metadatos(self.source_row.pk, self.actor.pk, uuid.uuid4(), 'Ensayo aislado')
        self.assertEqual(manual.estado, 'omitida')
        self.assertEqual(scheduled.estado, 'omitida')
        network.assert_not_called()

    def test_login_recovery_uses_one_real_window_for_missed_hourly_triggers(self):
        """Inicio de sesión y disparador horario usan la misma ventana de 24 h."""
        self.source_row, _ = set_frequency(self.source_row.pk, self.actor.pk,
                                           'Ensayo aislado de veinticuatro horas', 1440)
        previous = self.previous(hours=72)
        calls = []
        def network(url):
            calls.append(url)
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, national_index()
            if url == NATIONAL_PAGE:
                return 200, {'content-type': 'text/html'}, national_ficha()
            return self.fake(url)
        with patch('rastreo.services.timezone.now', return_value=self.now), patch(
                'convocatorias.siau_red.Downloader.once', side_effect=network), patch(
                'convocatorias.siau_red.time.sleep'):
            recovered = run_scheduled(self.source_row.pk)
            same = run_scheduled(self.source_row.pk)
        recovered.refresh_from_db()
        self.assertNotEqual(recovered.pk, previous.pk)
        self.assertEqual(same.pk, recovered.pk)
        self.assertEqual(Ejecucion.objects.filter(fuente=self.source_row).exclude(estado='omitida').count(), 2)
        self.assertIn(NATIONAL_INDEX, calls)
        self.assertEqual(next_due(self.source_row), recovered.inicio + timedelta(hours=24))
        self.assertFalse(Convocatoria.objects.filter(fecha_publicacion__isnull=False).exists())

    def test_login_recovery_skips_when_twenty_four_hours_have_not_elapsed(self):
        self.source_row, _ = set_frequency(self.source_row.pk, self.actor.pk,
                                           'Ensayo aislado de veinticuatro horas', 1440)
        previous = self.previous(hours=23)
        with patch('rastreo.services.timezone.now', return_value=self.now), patch(
                'convocatorias.siau_red.Downloader.once') as network:
            result = run_scheduled(self.source_row.pk)
        self.assertEqual(result.pk, previous.pk)
        network.assert_not_called()
