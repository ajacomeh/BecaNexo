"""Desbloqueo administrativo tras HTTP 429/503; todo HTTP es simulado."""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from convocatorias.siau_red import INDEX
from . import tests as base
from .models import Revision
from .services import run_manual
from .web_frequency import UNLOCK_ACTION, source_blocked, unlock_source

MOTIVO = 'Revisé la respuesta 429 y las condiciones de la fuente.'


class DesbloqueoFuenteTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake

    def blocked_source(self):
        source = self.source()

        def network(url):
            if url == INDEX:
                return 429, {'retry-after': '120'}, b''
            return self.fake(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertTrue(run.accesos.filter(http_status=429).exists())
        self.assertTrue(source_blocked(source))
        return source, run

    def test_unlock_requires_admin_and_reason_and_records_status_and_date(self):
        source, run = self.blocked_source()
        with self.assertRaises(ValidationError):
            unlock_source(source.pk, self.user.pk, MOTIVO, uuid.uuid4())
        with self.assertRaises(ValidationError):
            unlock_source(source.pk, self.actor.pk, 'corto', uuid.uuid4())
        self.assertFalse(Revision.objects.filter(detalle__accion=UNLOCK_ACTION).exists())
        key = uuid.uuid4()
        row, created = unlock_source(source.pk, self.actor.pk, MOTIVO, key)
        self.assertTrue(created)
        self.assertEqual((row.actor_id, row.fuente_id, row.dimension, row.decision, row.motivo),
                         (self.actor.pk, source.pk, 'configuracion', 'aplicada', MOTIVO))
        self.assertEqual(row.detalle['http_status'], 429)
        self.assertEqual(row.detalle['ejecucion_id'], run.pk)
        blocking = run.accesos.filter(http_status=429).order_by('secuencia', 'id').first()
        self.assertEqual(row.detalle['bloqueado_en'], blocking.fin.isoformat())
        self.assertIsNotNone(row.detalle['reintento_desde'])
        self.assertFalse(source_blocked(source))
        # Idempotente con la misma clave y contenido; conflicto con otro contenido.
        self.assertEqual(unlock_source(source.pk, self.actor.pk, MOTIVO, key), (row, False))
        with self.assertRaises(ValidationError):
            unlock_source(source.pk, self.actor.pk, MOTIVO + ' Otro motivo.', key)
        with self.assertRaises(ValidationError):
            unlock_source(source.pk, self.actor.pk, MOTIVO, uuid.uuid4())
        self.assertEqual(Revision.objects.filter(detalle__accion=UNLOCK_ACTION).count(), 1)

    def test_unlock_keeps_retry_after_and_frequency(self):
        source, _run = self.blocked_source()
        unlock_source(source.pk, self.actor.pk, MOTIVO, uuid.uuid4())
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake):
            immediate = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(immediate.estado, 'omitida')
        self.assertFalse(immediate.incidencias.filter(detalle__contains='429/503').exists())
        later = timezone.now() + timedelta(minutes=source.frecuencia_min + 5)
        with patch('rastreo.services.timezone.now', return_value=later), patch(
                'convocatorias.siau_red.Downloader.once', side_effect=self.fake):
            following = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertNotEqual(following.estado, 'omitida')

    def test_unlock_is_rejected_without_block(self):
        source = self.source()
        with self.assertRaises(ValidationError):
            unlock_source(source.pk, self.actor.pk, MOTIVO, uuid.uuid4())

    def test_api_shows_block_and_unlocks_only_with_admin_session_and_csrf(self):
        source, run = self.blocked_source()
        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        state = admin.get('/api/gestion/rastreo/control/').data
        self.assertTrue(state['bloqueo_fuente'])
        self.assertEqual(state['bloqueos'][0]['http_status'], 429)
        self.assertEqual(state['bloqueos'][0]['ejecucion_id'], run.pk)
        path = f'/api/gestion/rastreo/fuentes/{source.pk}/desbloquear/'
        body = {'motivo': MOTIVO, 'clave_accion': str(uuid.uuid4())}
        self.assertIn(APIClient(enforce_csrf_checks=True).post(path, body, format='json').status_code, (401, 403))
        self.assertEqual(admin.post(path, body, format='json').status_code, 403)
        applicant = APIClient(enforce_csrf_checks=True)
        applicant.force_login(self.user)
        token = applicant.get('/api/auth/csrf/').data['csrfToken']
        self.assertEqual(applicant.post(path, body, format='json', HTTP_X_CSRFTOKEN=token).status_code, 403)
        token = admin.get('/api/auth/csrf/').data['csrfToken']
        self.assertEqual(admin.post(path, {'motivo': MOTIVO}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 400)
        self.assertEqual(admin.post(path, {**body, 'motivo': 'corto'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 400)
        response = admin.post(path, body, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data['actor_id'], response.data['detalle']['http_status']), (self.actor.pk, 429))
        self.assertEqual(admin.post(path, body, format='json', HTTP_X_CSRFTOKEN=token).status_code, 200)
        state = admin.get('/api/gestion/rastreo/control/').data
        self.assertFalse(state['bloqueo_fuente'])
        self.assertEqual(state['bloqueos'], [])
        self.assertEqual(admin.post('/api/gestion/rastreo/fuentes/999999/desbloquear/', body, format='json',
                                    HTTP_X_CSRFTOKEN=token).status_code, 404)
