"""Frecuencia de 12 horas en SIAU: piso de 720 minutos, ventana de la tarea y «Próxima disponibilidad» del panel.

HTTP siempre simulado; escribe solo en la base de pruebas aislada.
"""
import tempfile
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import tests as base
from .models import Ejecucion, FRECUENCIA_MINIMA_MIN
from .services import enable_discovery, enable_national_discovery, next_due, run_scheduled, set_frequency, snapshot

PANEL = '/api/gestion/rastreo/control/'


class FrecuenciaSiau12hTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake

    def siau(self, minutos=720):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        source = self.source()
        enable_discovery(self.actor.pk, 'Prueba índice')
        enable_national_discovery(self.actor.pk, 'Prueba nacionales')
        if source.frecuencia_min != minutos:
            source, _ = set_frequency(source.pk, self.actor.pk, 'Frecuencia de la prueba', minutos)
        return source

    def captura_previa(self, source, inicio):
        return Ejecucion.objects.create(fuente=source, origen='programada', clave_idempotencia=uuid.uuid4(), inicio=inicio, fin=inicio,
                                        estado='finalizada', configuracion_snapshot=snapshot(source.pk), version_extractor='siau-html/2')

    def test_piso_de_720_minutos_y_techo_semanal_para_siau(self):
        self.assertEqual(FRECUENCIA_MINIMA_MIN, 720)
        source = self.siau(minutos=1440)
        for invalida in (60, 719, 10081):
            with self.assertRaises(ValidationError):
                set_frequency(source.pk, self.actor.pk, 'Fuera de los límites', invalida)
        source.refresh_from_db()
        self.assertEqual(source.frecuencia_min, 1440)
        source, cambio = set_frequency(source.pk, self.actor.pk, 'Doce horas', 720)
        self.assertTrue(cambio)
        self.assertEqual(source.frecuencia_min, 720)

    def test_la_tarea_omite_antes_de_12_horas_sin_crear_ejecuciones_y_captura_despues(self):
        source = self.siau()
        ahora = timezone.now().replace(microsecond=0)
        previa = self.captura_previa(source, ahora - timedelta(hours=11, minutes=59))
        self.assertEqual(next_due(source), previa.inicio + timedelta(hours=12))
        with patch('rastreo.services.timezone.now', return_value=ahora), patch('convocatorias.siau_red.Downloader.once') as red:
            resultado = run_scheduled(source.pk)
            red.assert_not_called()
        # «No corresponde aún»: devuelve la última captura y no añade filas a la lista de ejecuciones.
        self.assertEqual(resultado.pk, previa.pk)
        self.assertEqual(Ejecucion.objects.filter(fuente=source).count(), 1)
        despues = ahora + timedelta(minutes=1)
        with patch('rastreo.services.timezone.now', return_value=despues), \
                patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake) as red, \
                patch('convocatorias.siau_red.time.sleep'):
            nueva = run_scheduled(source.pk)
        nueva.refresh_from_db()
        self.assertNotEqual(nueva.pk, previa.pk)
        self.assertIn(nueva.estado, ('finalizada', 'parcial'))
        self.assertTrue(red.called)

    def test_proxima_disponibilidad_del_panel_usa_la_ventana_de_12_horas(self):
        source = self.siau()
        ahora = timezone.now().replace(microsecond=0)
        previa = self.captura_previa(source, ahora - timedelta(hours=3))
        cliente = APIClient()
        cliente.force_login(self.actor)
        with tempfile.TemporaryDirectory() as raiz, override_settings(RASTREO_WEB_LAUNCH_ROOT=raiz, RASTREO_EXTRAORDINARIO_HABILITADO=False):
            with patch('django.utils.timezone.now', return_value=ahora):
                estado = cliente.get(PANEL).data
            self.assertFalse(estado['puede_iniciar'])
            self.assertEqual(estado['proxima_manual'], previa.inicio + timedelta(hours=12))
            self.assertEqual(estado['frecuencia_min'], 720)
            with patch('django.utils.timezone.now', return_value=previa.inicio + timedelta(hours=12, seconds=1)):
                estado = cliente.get(PANEL).data
            self.assertTrue(estado['puede_iniciar'])
