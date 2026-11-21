"""Pruebas del inicio web; ningún proceso de red se ejecuta aquí."""
import json
import ctypes
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import tests as base
from .models import Acceso, Documento, Ejecucion, Publicacion, Revision
from .web_launch import LaunchBusy, launch_lock, start_worker, spawn_detached
from .web_worker import main as worker_main
from .services import configure, enable_discovery, enable_national_discovery, register_portal, set_portal_active


ROOT = '/api/gestion/rastreo/control/'


class WebControlTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake

    def _client(self, user):
        client = APIClient(enforce_csrf_checks=True)
        if user:
            client.force_login(user)
        return client

    def _isolated_child_env(self, root, case):
        config = connection.settings_dict
        self.assertEqual(config['NAME'], 'test_becanexo_db')
        self.assertIn(config['HOST'], ('127.0.0.1', 'localhost', '::1'))
        return {
            'BECANEXO_ISOLATED_ONLY_DB': 'test_becanexo_db',
            'BECANEXO_ISOLATED_CASE': case,
            'DB_NAME': 'test_becanexo_db', 'DB_USER': config['USER'],
            'DB_PASSWORD': config['PASSWORD'], 'DB_HOST': config['HOST'],
            'DB_PORT': str(config['PORT']), 'RASTREO_STORAGE_ROOT': self.temp.name,
            'DJANGO_SECRET_KEY': 'clave-sintetica-solo-pruebas',
            'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,testserver',
        }

    def _verified_child_env(self, root, case):
        extra = self._isolated_child_env(root, case)
        inherited = ('SystemRoot', 'WINDIR', 'PATH', 'PATHEXT', 'TEMP', 'TMP')
        environment = {name: os.environ[name] for name in inherited if name in os.environ}
        environment.update(extra)
        preflight = subprocess.run(
            [sys.executable, '-m', 'rastreo._isolated_web_entry', '--preflight'],
            cwd=str(Path(__file__).resolve().parent.parent), env=environment,
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(preflight.returncode, 0, preflight.stderr.splitlines()[-1:] if preflight.stderr else '')
        check = json.loads(preflight.stdout)
        self.assertEqual(check['base_efectiva'], 'test_becanexo_db')
        self.assertTrue(check['red_externa_bloqueada'])
        return extra

    def _fresh_django_request(self, mode, actor_id, root, case, extra):
        inherited = ('SystemRoot', 'WINDIR', 'PATH', 'PATHEXT', 'TEMP', 'TMP')
        environment = {name: os.environ[name] for name in inherited if name in os.environ}
        environment.update(extra)
        process = subprocess.run(
            [sys.executable, '-m', 'rastreo._isolated_request', mode, str(actor_id), root, case],
            cwd=str(Path(__file__).resolve().parent.parent), env=environment,
            capture_output=True, text=True, timeout=25,
        )
        self.assertEqual(process.returncode, 0, process.stderr.splitlines()[-1:] if process.stderr else '')
        return json.loads(process.stdout)

    def _wait_pid(self, pid, timeout_ms=30000):
        handle = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
        if not handle:
            return
        try:
            self.assertEqual(ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_ms), 0)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    def _pid_alive(self, pid):
        handle = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) != 0
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    def test_detached_worker_survives_fresh_django_process(self):
        source = self.source()
        enable_discovery(self.actor.pk, 'Índice aislado')
        enable_national_discovery(self.actor.pk, 'Índice nacional aislado')
        with tempfile.TemporaryDirectory() as root:
            extra = self._verified_child_env(root, 'reinicio')
            started = self._fresh_django_request('start', self.actor.pk, root, 'reinicio', extra)
            self.assertEqual(started['http'], 202)
            pid = started['pid']
            self.assertIsInstance(pid, int)
            try:
                self.assertTrue((Path(root) / f'fuente-{source.pk}.json').exists())
                self.assertFalse((Path(root) / f'resultado-{source.pk}.json').exists())
                restarted = self._fresh_django_request('status', self.actor.pk, root, 'reinicio', extra)
                self.assertTrue(restarted['inicio_pendiente'])
                self.assertEqual(self._fresh_django_request('repeat', self.actor.pk, root, 'reinicio', extra)['http'], 409)
                self._wait_pid(pid)
                result = json.loads((Path(root) / f'resultado-{source.pk}.json').read_text(encoding='utf-8'))
                self.assertIn(result['estado'], ('finalizada', 'parcial'))
                self.assertFalse((Path(root) / f'fuente-{source.pk}.json').exists())
                final = self._fresh_django_request('status', self.actor.pk, root, 'reinicio', extra)
                self.assertEqual(final['ultimo_inicio_web']['estado'], result['estado'])
                self.assertEqual(final['ultima_ejecucion']['id'], result['ejecucion_id'])
                self.assertEqual(Ejecucion.objects.get(pk=result['ejecucion_id']).origen, 'manual')
            finally:
                if self._pid_alive(pid):
                    os.kill(pid, signal.SIGTERM)
                    self._wait_pid(pid, 5000)

    def test_hard_terminated_worker_keeps_marker_for_review_after_restart(self):
        source = self.source()
        enable_discovery(self.actor.pk, 'Índice aislado')
        enable_national_discovery(self.actor.pk, 'Índice nacional aislado')
        with tempfile.TemporaryDirectory() as root:
            extra = self._verified_child_env(root, 'reinicio')
            started = self._fresh_django_request('start', self.actor.pk, root, 'reinicio', extra)
            self.assertEqual(started['http'], 202)
            pid = started['pid']
            marker = Path(root) / f'fuente-{source.pk}.json'
            try:
                deadline = time.monotonic() + 10
                while not Ejecucion.objects.filter(clave_idempotencia=started['clave']).exists() and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(Ejecucion.objects.filter(clave_idempotencia=started['clave'], estado='en_curso').exists())
                os.kill(pid, signal.SIGTERM)
                self._wait_pid(pid, 5000)
                self.assertTrue(marker.exists())
                self.assertFalse((Path(root) / f'resultado-{source.pk}.json').exists())
                old = timezone.now().timestamp() - 180
                os.utime(marker, (old, old))
                state = self._fresh_django_request('status', self.actor.pk, root, 'reinicio', extra)
                self.assertTrue(state['requiere_revision'])
                self.assertTrue(state['inicio_pendiente'])
                self.assertEqual(self._fresh_django_request('repeat', self.actor.pk, root, 'reinicio', extra)['http'], 409)
                self.assertEqual(Ejecucion.objects.filter(clave_idempotencia=started['clave']).count(), 1)
            finally:
                if self._pid_alive(pid):
                    os.kill(pid, signal.SIGTERM)
                    self._wait_pid(pid, 5000)

    def _run_official_child(self, case):
        source = self.source()
        enable_discovery(self.actor.pk, 'Índice aislado')
        enable_national_discovery(self.actor.pk, 'Índice nacional aislado')
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root):
            extra = self._verified_child_env(root, case)
            admin = self._client(self.actor)
            token = admin.get('/api/auth/csrf/').data['csrfToken']
            children = []

            def isolated_spawn(module, source_id, actor_id, key, folder, *, cwd):
                self.assertEqual(module, 'rastreo.web_worker')
                child = spawn_detached('rastreo._isolated_web_entry', source_id, actor_id, key, folder,
                                       cwd=cwd, environment=extra)
                children.append(child)
                return child

            with patch('rastreo.web_launch.spawn_detached', side_effect=isolated_spawn):
                response = admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token)
                self.assertEqual(response.status_code, 202)
                self.assertEqual(admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 409)
            self.assertEqual(len(children), 1)
            self.assertTrue((Path(root) / f'fuente-{source.pk}.json').exists())
            try:
                code = children[0].wait(timeout=40)
            finally:
                if children[0].poll() is None:
                    children[0].terminate()
                    children[0].wait(timeout=5)
            self.assertIsNotNone(children[0].poll())
            result = json.loads((Path(root) / f'resultado-{source.pk}.json').read_text(encoding='utf-8'))
            self.assertFalse((Path(root) / f'fuente-{source.pk}.json').exists())
            observed = admin.get(ROOT).data['ultimo_inicio_web']
            self.assertEqual(observed['clave'], response.data['clave'])
            self.assertEqual(observed['estado'], result['estado'])
            return code, result, source

    def test_detached_official_engine_isolated_and_persisted(self):
        code, result, source = self._run_official_child('exito')
        self.assertEqual(code, 0)
        self.assertIn(result['estado'], ('finalizada', 'parcial'))
        run = Ejecucion.objects.get(clave_idempotencia=result['clave'])
        self.assertEqual(run.pk, result['ejecucion_id'])
        self.assertEqual(run.origen, 'manual')
        self.assertEqual(run.estado, result['estado'])
        self.assertEqual(run.fuente_id, source.pk)
        self.assertEqual(run.configuracion_snapshot['politica_version'], 'siau-nacionales/3')
        self.assertGreater(Acceso.objects.filter(ejecucion=run).count(), 0)
        self.assertGreater(Documento.objects.count(), 0)
        self.assertGreater(Publicacion.objects.filter(fuente=source).count(), 0)
        self.assertGreater(Revision.objects.filter(fuente=source).count(), 0)

    def test_detached_worker_failure_after_accepted_request(self):
        code, result, source = self._run_official_child('fallo_hijo')
        self.assertEqual(code, 1)
        self.assertEqual(result['estado'], 'fallo_infraestructura')
        self.assertEqual(result['codigo'], 'RuntimeError')
        self.assertNotIn('mensaje sintético privado', str(result))
        self.assertFalse(Ejecucion.objects.filter(clave_idempotencia=result['clave']).exists())

    def test_permissions_and_csrf_do_not_launch_worker(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_db')
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root), \
                patch('rastreo.api_control.start_worker') as start:
            anonymous = self._client(None)
            student = self._client(self.user)
            admin = self._client(self.actor)
            self.assertEqual(anonymous.get(ROOT).status_code, 403)
            self.assertEqual(anonymous.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json').status_code, 403)
            self.assertEqual(student.get(ROOT).status_code, 403)
            token = student.get('/api/auth/csrf/').data['csrfToken']
            self.assertEqual(student.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 403)
            self.assertEqual(admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json').status_code, 403)
            self.assertEqual(admin.get(ROOT).status_code, 200)
            start.assert_not_called()

    def test_due_launch_is_nonblocking_and_never_runs_crawler_in_request(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root), \
                patch('rastreo.api_control.start_worker', return_value=uuid.uuid4()) as start:
            admin = self._client(self.actor)
            token = admin.get('/api/auth/csrf/').data['csrfToken']
            self.assertTrue(admin.get(ROOT).data['puede_iniciar'])
            response = admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.data['estado'], 'iniciando')
            start.assert_called_once_with(source.pk, self.actor.pk, 'Verificacion administrativa', False)
            self.assertEqual(Ejecucion.objects.count(), 0)

    def test_panel_selects_only_due_authorized_source_without_changing_siau(self):
        siau = self.source()
        Ejecucion.objects.create(fuente=siau, solicitado_por=self.actor, configuracion_snapshot={},
            version_extractor='prueba', inicio=timezone.now(), fin=timezone.now(), estado='finalizada')
        ups, _ = register_portal(self.actor.pk, 'ups', 'Alta sintética auditada')
        ups, _ = set_portal_active(ups.pk, self.actor.pk, 'Activación sintética auditada', True)
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root), \
                patch('rastreo.api_control.start_worker', return_value=uuid.uuid4()) as start:
            admin = self._client(self.actor)
            token = admin.get('/api/auth/csrf/').data['csrfToken']
            state = admin.get(ROOT).data
            self.assertEqual(state['fuente_id'], ups.pk)
            self.assertEqual(state['frecuencia_min'], 720)
            self.assertEqual(state['fuentes_activas'], 2)
            self.assertEqual({item['nombre'] for item in state['fuentes_registradas']}, {siau.nombre, ups.nombre})
            self.assertEqual([item['adaptador'] for item in state['conectores_sin_registro']], ['portal_ec:utpl'])
            self.assertTrue(state['puede_iniciar'])
            response = admin.post(ROOT, {'motivo': 'Validación de fuente activa'}, format='json', HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 202)
            start.assert_called_once_with(ups.pk, self.actor.pk, 'Validación de fuente activa', False)
            self.assertEqual(Ejecucion.objects.filter(fuente=ups).count(), 0)

    def test_panel_disables_start_without_active_source(self):
        self.source()
        configure(self.actor.pk, 'Desactivación sintética auditada', active=False)
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root), \
                patch('rastreo.api_control.start_worker') as start:
            admin = self._client(self.actor)
            token = admin.get('/api/auth/csrf/').data['csrfToken']
            state = admin.get(ROOT).data
            self.assertEqual(state['fuentes_activas'], 0)
            self.assertEqual(state['fuentes_registradas'][0]['nombre'], 'SIAU')
            self.assertFalse(state['fuentes_registradas'][0]['activa'])
            self.assertIn('portal_ec:utpl', [item['adaptador'] for item in state['conectores_sin_registro']])
            self.assertFalse(state['puede_iniciar'])
            self.assertEqual(admin.post(ROOT, {'motivo': 'Validación de ausencia de fuentes'},
                format='json', HTTP_X_CSRFTOKEN=token).status_code, 409)
            start.assert_not_called()

    def test_frequency_active_execution_and_pending_marker_block_launch(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root), \
                patch('rastreo.api_control.start_worker') as start:
            admin = self._client(self.actor)
            token = admin.get('/api/auth/csrf/').data['csrfToken']
            execution = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor,
                configuracion_snapshot={}, version_extractor='prueba',
                inicio=timezone.now(), fin=timezone.now(), estado='finalizada')
            response = admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 409)
            self.assertGreater(response.data['proxima_ejecucion'], timezone.now())
            with patch('rastreo.api_control.next_due', return_value=timezone.now() - timedelta(days=2)):
                active = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor,
                    configuracion_snapshot={}, version_extractor='prueba')
                self.assertEqual(admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 409)
                Ejecucion.objects.filter(pk=active.pk).update(estado='fallida', fin=timezone.now())
                marker = Path(root) / f'fuente-{source.pk}.json'
                marker.write_text('{}', encoding='utf-8')
                self.assertEqual(admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 409)
            start.assert_not_called()

    def test_launcher_uses_separate_process_and_exclusive_marker(self):
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root), \
                patch('rastreo.web_launch.subprocess.Popen') as process, \
                patch.dict(os.environ, {'DB_PASSWORD': 'secreto-sintetico', 'DJANGO_SECRET_KEY': 'clave-sintetica',
                                        'RASTREO_EXTRAORDINARIO_HABILITADO': 'False'}):
            with launch_lock():
                key = start_worker(17, 25)
                self.assertEqual((Path(root) / 'fuente-17.json').exists(), True)
                with self.assertRaises(LaunchBusy):
                    start_worker(17, 25)
            args = process.call_args.args[0]
            self.assertEqual(args[1:5], ['-m', 'rastreo.web_worker', '17', '25'])
            self.assertEqual(args[-2], str(key))
            self.assertEqual(args[-1], root)
            self.assertNotIn('becanexo_db', str(args))
            self.assertNotIn('DB_PASSWORD', process.call_args.kwargs['env'])
            self.assertNotIn('DJANGO_SECRET_KEY', process.call_args.kwargs['env'])
            self.assertEqual(process.call_args.kwargs['env']['RASTREO_EXTRAORDINARIO_HABILITADO'], 'False')

    def test_two_http_starts_launch_once_and_spawn_error_cleans_marker(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root), \
                patch('rastreo.web_launch.subprocess.Popen') as process:
            admin = self._client(self.actor)
            token = admin.get('/api/auth/csrf/').data['csrfToken']
            self.assertEqual(admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 202)
            self.assertEqual(admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 409)
            process.assert_called_once()
            self.assertEqual(Ejecucion.objects.count(), 0)
            marker = Path(root) / f'fuente-{source.pk}.json'
            marker.unlink()
            process.side_effect = OSError('fallo inocuo')
            self.assertEqual(admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 503)
            self.assertFalse(marker.exists())

    def test_stale_unconfirmed_marker_is_reported_without_auto_retry(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root):
            marker = Path(root) / f'fuente-{source.pk}.json'
            marker.write_text(json.dumps({'clave': str(uuid.uuid4())}), encoding='utf-8')
            old = timezone.now().timestamp() - 180
            os.utime(marker, (old, old))
            admin = self._client(self.actor)
            data = admin.get(ROOT).data
            self.assertTrue(data['requiere_revision'])
            self.assertFalse(data['puede_iniciar'])
            self.assertEqual(Ejecucion.objects.count(), 0)

    def test_real_detached_probe_continues_after_http_response(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root):
            admin = self._client(self.actor)
            token = admin.get('/api/auth/csrf/').data['csrfToken']

            def harmless_spawn(module, source_id, actor_id, key, folder, *, cwd):
                self.assertEqual(module, 'rastreo.web_worker')
                self.assertEqual(actor_id, self.actor.pk)
                return spawn_detached('rastreo._probe_child', folder, source_id, key, cwd=cwd)

            with patch('rastreo.web_launch.spawn_detached', side_effect=harmless_spawn):
                response = admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token)
                self.assertEqual(response.status_code, 202)
                self.assertEqual(admin.post(ROOT, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 409)
            marker = Path(root) / f'fuente-{source.pk}.json'
            self.assertTrue(marker.exists())
            deadline = time.monotonic() + 8
            result = Path(root) / f'resultado-{source.pk}.json'
            while not result.exists() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(result.exists())
            while marker.exists() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertFalse(marker.exists())
            self.assertEqual(admin.get(ROOT).data['ultimo_inicio_web']['estado'], 'finalizada')
            self.assertEqual(Ejecucion.objects.count(), 0)

    def test_worker_rechecks_frequency_under_exclusion_without_network(self):
        source = self.source()
        Ejecucion.objects.create(fuente=source, solicitado_por=self.actor,
            configuracion_snapshot={}, version_extractor='prueba',
            inicio=timezone.now(), fin=timezone.now(), estado='finalizada')
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root), \
                patch('rastreo.services.run_manual') as run:
            key = str(uuid.uuid4())
            marker = Path(root) / f'fuente-{source.pk}.json'
            marker.write_text(json.dumps({'clave': key}), encoding='utf-8')
            with patch.object(sys, 'argv', ['web_worker', str(source.pk), str(self.actor.pk), key, root]):
                self.assertEqual(worker_main(), 0)
            self.assertEqual(json.loads((Path(root) / f'resultado-{source.pk}.json').read_text())['estado'], 'omitida_frecuencia')
            self.assertFalse(marker.exists())
            run.assert_not_called()
            marker.write_text(json.dumps({'clave': key}), encoding='utf-8')
            with patch('rastreo.services.next_due', return_value=None), \
                    patch('rastreo.services.run_manual', return_value=SimpleNamespace(pk=33, estado='finalizada', refresh_from_db=lambda: None)) as allowed, \
                    patch.object(sys, 'argv', ['web_worker', str(source.pk), str(self.actor.pk), key, root]):
                self.assertEqual(worker_main(), 0)
            allowed.assert_called_once_with(source.pk, self.actor.pk, key)
            self.assertEqual(json.loads((Path(root) / f'resultado-{source.pk}.json').read_text())['ejecucion_id'], 33)

    def test_worker_runs_existing_engine_with_fake_http_in_test_database(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_db')
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root):
            key = str(uuid.uuid4())
            (Path(root) / f'fuente-{source.pk}.json').write_text(json.dumps({'clave': key}), encoding='utf-8')
            with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake), \
                    patch.object(sys, 'argv', ['web_worker', str(source.pk), str(self.actor.pk), key, root]):
                self.assertEqual(worker_main(), 0)
            run = Ejecucion.objects.get(clave_idempotencia=key)
            self.assertEqual(run.origen, 'manual')
            self.assertEqual(run.estado, 'finalizada')
            self.assertEqual(json.loads((Path(root) / f'resultado-{source.pk}.json').read_text())['ejecucion_id'], run.pk)
            self.assertFalse((Path(root) / f'fuente-{source.pk}.json').exists())

    def test_ordinary_web_request_keeps_configured_window(self):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root):
            key = str(uuid.uuid4())
            marker = {'clave': key, 'fuente_id': source.pk, 'actor_id': self.actor.pk,
                      'motivo': 'Revisión ordinaria autorizada', 'extraordinario': False,
                      'aceptada_en': timezone.now().isoformat()}
            (Path(root) / f'fuente-{source.pk}.json').write_text(json.dumps(marker), encoding='utf-8')
            with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake), \
                    patch.object(sys, 'argv', ['web_worker', str(source.pk), str(self.actor.pk), key, root]):
                self.assertEqual(worker_main(), 0)
            execution = Ejecucion.objects.get(clave_idempotencia=key)
            self.assertEqual(execution.configuracion_snapshot['solicitud_manual']['motivo'], marker['motivo'])
            self.assertNotIn('solicitud_extraordinaria', execution.configuracion_snapshot)
            from .services import next_due
            self.assertGreater(next_due(source), timezone.now() + timedelta(minutes=source.frecuencia_min - 1))

    def test_worker_reports_startup_failure_without_database_or_secrets(self):
        with tempfile.TemporaryDirectory() as root:
            key = str(uuid.uuid4())
            marker = Path(root) / 'fuente-17.json'
            marker.write_text(json.dumps({'clave': key}), encoding='utf-8')
            with patch('django.setup', side_effect=RuntimeError('mensaje privado de prueba')), \
                    patch.object(sys, 'argv', ['web_worker', '17', '25', key, root]):
                self.assertEqual(worker_main(), 1)
            result = json.loads((Path(root) / 'resultado-17.json').read_text(encoding='utf-8'))
            self.assertEqual(result['estado'], 'fallo_infraestructura')
            self.assertEqual(result['codigo'], 'RuntimeError')
            self.assertNotIn('mensaje privado', str(result))
            self.assertFalse(marker.exists())

    def test_extraordinary_window_acceptance_and_audit_receipt(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(
                RASTREO_WEB_LAUNCH_ROOT=root, RASTREO_EXTRAORDINARIO_HABILITADO=True), \
                patch('rastreo.web_launch.subprocess.Popen') as process:
            admin = self._client(self.actor)
            token = admin.get('/api/auth/csrf/').data['csrfToken']
            data = {'motivo': 'Revisar novedades nacionales'}
            self.assertTrue(admin.get(ROOT).data['rastreo_extraordinario_habilitado'])
            self.assertEqual(admin.post(ROOT, {}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 400)
            first = admin.post(ROOT, data, format='json', HTTP_X_CSRFTOKEN=token)
            self.assertEqual(first.status_code, 202)
            self.assertEqual(admin.post(ROOT, data, format='json', HTTP_X_CSRFTOKEN=token).status_code, 409)
            process.assert_called_once()
            receipt = Path(root) / f"solicitud-{source.pk}-{first.data['clave']}.json"
            stored = json.loads(receipt.read_text(encoding='utf-8'))
            self.assertEqual(stored['actor_id'], self.actor.pk)
            self.assertEqual(stored['motivo'], data['motivo'])
            self.assertTrue(stored['extraordinario'])
            (Path(root) / f'fuente-{source.pk}.json').unlink()
            self.assertEqual(admin.post(ROOT, data, format='json', HTTP_X_CSRFTOKEN=token).status_code, 409)
            self.assertGreater(admin.get(ROOT).data['proxima_manual'], timezone.now())
            stored['aceptada_en'] = (timezone.now() - timedelta(seconds=301)).isoformat()
            receipt.write_text(json.dumps(stored), encoding='utf-8')
            self.assertTrue(admin.get(ROOT).data['puede_iniciar'])
            self.assertEqual(admin.post(ROOT, data, format='json', HTTP_X_CSRFTOKEN=token).status_code, 202)
            self.assertEqual(process.call_count, 2)

    def test_extraordinary_reason_validation_daily_cap_and_disabled_default(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(RASTREO_WEB_LAUNCH_ROOT=root), \
                patch('rastreo.api_control.start_worker') as start:
            admin = self._client(self.actor)
            token = admin.get('/api/auth/csrf/').data['csrfToken']
            self.assertFalse(admin.get(ROOT).data['rastreo_extraordinario_habilitado'])
            for value in ({}, {'motivo': 'corto'}, {'motivo': 'x' * 241},
                          {'motivo': 'Revisión\ninaceptable'},
                          {'motivo': 'Motivo aceptable', 'saltar_frecuencia': True}):
                self.assertEqual(admin.post(ROOT, value, format='json', HTTP_X_CSRFTOKEN=token).status_code, 400)
            start.assert_not_called()
        # El cupo diario se reinicia a medianoche UTC: con el reloj fijo a mediodía, el resultado no depende de la
        # hora a la que se ejecute la prueba (en la última hora del día UTC el reinicio queda a menos de una hora).
        fixed_now = datetime(2026, 11, 20, 12, 0, tzinfo=dt_timezone.utc)
        with tempfile.TemporaryDirectory() as root, override_settings(
                RASTREO_WEB_LAUNCH_ROOT=root, RASTREO_EXTRAORDINARIO_HABILITADO=True),                 patch('django.utils.timezone.now', return_value=fixed_now):
            for index in range(3):
                (Path(root) / f'solicitud-{source.pk}-{uuid.uuid4()}.json').write_text(
                    json.dumps({'aceptada_en': (timezone.now() - timedelta(minutes=index * 6)).isoformat()}),
                    encoding='utf-8')
            state = self._client(self.actor).get(ROOT).data
            self.assertFalse(state['puede_iniciar'])
            self.assertGreater(state['proxima_manual'], timezone.now() + timedelta(hours=1))
            self.assertEqual(state['proxima_manual'], datetime(2026, 11, 21, 0, 0, tzinfo=dt_timezone.utc))

    def test_extraordinary_source_block_and_scheduled_calendar(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(
                RASTREO_WEB_LAUNCH_ROOT=root, RASTREO_EXTRAORDINARIO_HABILITADO=True), \
                patch('rastreo.api_control.start_worker') as start:
            scheduled = Ejecucion.objects.create(fuente=source, origen='programada', solicitado_por=None,
                configuracion_snapshot={}, version_extractor='prueba',
                inicio=timezone.now() - timedelta(hours=25), fin=timezone.now(), estado='finalizada')
            recent = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor,
                configuracion_snapshot={'solicitud_extraordinaria': {'motivo': 'prueba'}}, version_extractor='prueba',
                inicio=timezone.now() - timedelta(minutes=6), estado='en_curso')
            from .services import next_due
            # También una captura extraordinaria consume la ventana mínima.
            self.assertGreater(next_due(source), timezone.now() + timedelta(minutes=source.frecuencia_min - 7))
            admin = self._client(self.actor)
            token = admin.get('/api/auth/csrf/').data['csrfToken']
            now = timezone.now()
            Acceso.objects.create(ejecucion=recent, secuencia=1, rol='indice',
                url_original=source.url_base, url_normalizada=source.url_base,
                admitido_en=now, fin=now, http_status=503, resultado='error')
            Ejecucion.objects.filter(pk=recent.pk).update(estado='finalizada', fin=timezone.now())
            self.assertTrue(admin.get(ROOT).data['bloqueo_fuente'])
            self.assertEqual(admin.post(ROOT, {'motivo': 'Revisar bloqueo SIAU'},
                format='json', HTTP_X_CSRFTOKEN=token).status_code, 409)
            start.assert_not_called()
            self.assertEqual(Ejecucion.objects.count(), 2)

    def test_extraordinary_worker_records_context_without_publication(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as root, override_settings(
                RASTREO_WEB_LAUNCH_ROOT=root, RASTREO_EXTRAORDINARIO_HABILITADO=True):
            key = str(uuid.uuid4())
            request = {'clave': key, 'fuente_id': source.pk, 'actor_id': self.actor.pk,
                       'motivo': 'Verificación administrativa aislada', 'extraordinario': True,
                       'aceptada_en': timezone.now().isoformat()}
            (Path(root) / f'fuente-{source.pk}.json').write_text(json.dumps(request), encoding='utf-8')
            (Path(root) / f'solicitud-{source.pk}-{key}.json').write_text(json.dumps(request), encoding='utf-8')
            with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake), \
                    patch.object(sys, 'argv', ['web_worker', str(source.pk), str(self.actor.pk), key, root]):
                self.assertEqual(worker_main(), 0)
            run = Ejecucion.objects.get(clave_idempotencia=key)
            self.assertEqual(run.origen, 'manual')
            self.assertEqual(run.configuracion_snapshot['solicitud_extraordinaria']['motivo'], request['motivo'])
            self.assertEqual(run.configuracion_snapshot['solicitud_extraordinaria']['actor_id'], self.actor.pk)
            self.assertEqual(run.configuracion_snapshot['politica_version'], source.politica_version)
            self.assertEqual(json.loads((Path(root) / f'resultado-{source.pk}.json').read_text())['ejecucion_id'], run.pk)
            self.assertFalse((Path(root) / f'fuente-{source.pk}.json').exists())

    def test_retry_after_stops_source_and_delays_scheduled_window(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_db')
        source = self.source()
        calls = []

        def unavailable(url):
            calls.append(url)
            return 503, {'retry-after': '172800', 'content-type': 'text/plain'}, b''

        from .services import next_due, run_manual
        with patch('convocatorias.siau_red.Downloader.once', side_effect=unavailable):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(run.estado, 'fallida')
        self.assertEqual(len(calls), 1)
        self.assertEqual(run.accesos.count(), 1)
        self.assertEqual(run.accesos.get().http_status, 503)
        self.assertEqual(run.error_resumen, 'SourceBackoff')
        self.assertTrue(run.incidencias.filter(codigo='REINTENTO_FUENTE').exists())
        self.assertGreater(next_due(source), timezone.now() + timedelta(hours=47))
        with tempfile.TemporaryDirectory() as root, override_settings(
                RASTREO_WEB_LAUNCH_ROOT=root, RASTREO_EXTRAORDINARIO_HABILITADO=True):
            state = self._client(self.actor).get(ROOT).data
            self.assertFalse(state['puede_iniciar'])
            self.assertTrue(state['bloqueo_fuente'])

    def test_backoff_during_page_does_not_continue_to_next_page(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_db')
        source = self.source()
        from convocatorias.siau_red import ROBOTS, INDEX, PAGES
        from .services import run_manual
        calls = []

        def response(url):
            calls.append(url)
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /wp-admin/\n'
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == PAGES[0]:
                return 429, {'retry-after': '300'}, b''
            self.fail('La captura continuó después del bloqueo de la fuente.')

        with patch('convocatorias.siau_red.Downloader.once', side_effect=response):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(run.estado, 'fallida')
        self.assertEqual(calls, [ROBOTS, INDEX, PAGES[0]])
        self.assertTrue(run.accesos.filter(http_status=429).exists())
        self.assertTrue(run.incidencias.filter(codigo='REINTENTO_FUENTE').exists())
