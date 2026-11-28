"""Compatibilidad con Linux y ajustes de producción, sin cambiar el comportamiento en Windows ni los valores por defecto."""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from rastreo import web_launch

BACKEND = Path(settings.BASE_DIR)
CONTROL = '/api/gestion/rastreo/control/'


def ejecutar(codigo, extra_env=None, settings_module=None):
    """Proceso Python nuevo (las importaciones no contaminan la suite); devuelve la última línea de su salida."""
    env = {**os.environ, **(extra_env or {})}
    if settings_module:
        env['DJANGO_SETTINGS_MODULE'] = settings_module
    r = subprocess.run([sys.executable, '-c', codigo], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise AssertionError(f'El proceso falló:\n{r.stderr[-3000:]}')
    return r.stdout.strip().splitlines()[-1]


class SinMsvcrtTests(SimpleTestCase):
    def test_urls_cargan_y_resuelven_sin_msvcrt(self):
        # Como en Linux: msvcrt no existe y fcntl sí (aquí, simulado). Se bloquea tras django.setup(), porque en
        # Windows la propia biblioteca estándar lo usa al arrancar.
        salida = ejecutar(
            "import json, sys, types, django\n"
            "django.setup()\n"
            "sys.modules['msvcrt'] = None\n"
            "sys.modules['fcntl'] = types.SimpleNamespace(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8, flock=lambda fd, op: None)\n"
            "for nombre in [m for m in sys.modules if m.startswith('rastreo.') or m == 'config.urls']:\n"
            "    del sys.modules[nombre]\n"
            "from django.urls import resolve, reverse\n"
            "import config.urls, rastreo.web_launch as w\n"
            "print(json.dumps({'msvcrt': w.msvcrt is None, 'control': resolve('/api/gestion/rastreo/control/').func.view_class.__name__,"
            " 'becas': resolve('/api/becas/').func.view_class.__name__, 'admin': reverse('admin:index')}))")
        self.assertEqual(json.loads(salida), {'msvcrt': True, 'control': 'ControlRastreo', 'becas': 'Consulta', 'admin': '/admin/'})


class BloqueoYProcesoTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_windows_sigue_usando_msvcrt(self):
        if os.name != 'nt':
            self.skipTest('Solo en Windows')
        self.assertIsNotNone(web_launch.msvcrt)
        with override_settings(RASTREO_WEB_LAUNCH_ROOT=self.temp.name), web_launch.launch_lock():
            with self.assertRaises(web_launch.LaunchBusy):  # el mismo bloqueo exclusivo de siempre
                with web_launch.launch_lock():
                    pass

    def test_posix_usa_flock_y_un_segundo_intento_queda_ocupado(self):
        fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8, flock=MagicMock())
        with override_settings(RASTREO_WEB_LAUNCH_ROOT=self.temp.name), patch.object(web_launch, 'msvcrt', None), \
                patch.object(web_launch, 'fcntl', fcntl, create=True):
            with web_launch.launch_lock():
                pass
            self.assertEqual([c.args[1] for c in fcntl.flock.call_args_list], [2 | 4, 8])
            fcntl.flock.side_effect = BlockingIOError()
            with self.assertRaises(web_launch.LaunchBusy):
                with web_launch.launch_lock():
                    pass

    def test_proceso_separado_segun_la_plataforma(self):
        with patch('rastreo.web_launch.subprocess.Popen') as popen:
            with patch.object(web_launch.os, 'name', 'posix'):
                web_launch.spawn_detached('rastreo._probe_child', cwd=self.temp.name)
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            self.assertNotIn('creationflags', popen.call_args.kwargs)
            if os.name == 'nt':  # en Windows, las mismas banderas de siempre
                with patch.object(web_launch.os, 'name', 'nt'):
                    web_launch.spawn_detached('rastreo._probe_child', cwd=self.temp.name)
                self.assertEqual(popen.call_args.kwargs['creationflags'], subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
                self.assertNotIn('start_new_session', popen.call_args.kwargs)


class InterruptorLanzamientoTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(email='admin-linux@example.com', nombre='Admin', password=None, rol='administrador')
        self.client = APIClient()
        self.client.force_login(self.admin)

    def test_por_defecto_todo_sigue_igual(self):
        self.assertTrue(settings.RASTREO_WEB_LANZAMIENTO_HABILITADO)
        data = self.client.get(CONTROL).json()
        self.assertNotIn('lanzamiento_web_habilitado', data)  # la respuesta de siempre, sin campos nuevos
        with patch('rastreo.api_control.start_worker') as start:  # el POST sigue su camino normal (aquí: sin fuentes)
            r = self.client.post(CONTROL, {'motivo': 'Verificacion administrativa'}, format='json')
        self.assertEqual(r.status_code, 409)
        self.assertNotIn('lanzamiento_web_habilitado', r.json())
        start.assert_not_called()

    @override_settings(RASTREO_WEB_LANZAMIENTO_HABILITADO=False)
    def test_desactivado_responde_claro_sin_lanzar(self):
        with patch('rastreo.api_control.launch_lock') as lock, patch('rastreo.api_control.start_worker') as start:
            r = self.client.post(CONTROL, {'motivo': 'Verificacion administrativa'}, format='json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json(), {'detail': 'El rastreo desde la web está desactivado en este entorno.', 'lanzamiento_web_habilitado': False})
        lock.assert_not_called()
        start.assert_not_called()
        data = self.client.get(CONTROL).json()
        self.assertEqual((data['puede_iniciar'], data['lanzamiento_web_habilitado']), (False, False))
        self.assertEqual(data['motivo_no_disponible'], 'El rastreo desde la web está desactivado en este entorno.')


def script_descarga():
    spec = importlib.util.spec_from_file_location('download_semantic_model', BACKEND / 'scripts' / 'download_semantic_model.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class Avx2Tests(SimpleTestCase):
    def setUp(self):
        self.m = script_descarga()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def cpuinfo(self, texto):
        path = Path(self.temp.name) / f'cpuinfo-{len(list(Path(self.temp.name).iterdir()))}'
        path.write_text(texto, encoding='utf-8')
        return path

    def test_linux_lee_proc_cpuinfo(self):
        con = self.cpuinfo('processor\t: 0\nflags\t\t: fpu sse2 avx avx2 fma\n\nprocessor\t: 1\nflags\t\t: fpu sse2 avx avx2\n')
        sin = self.cpuinfo('processor\t: 0\nflags\t\t: fpu sse2 avx\n')
        self.assertIs(self.m.tiene_avx2('linux', con), True)
        self.assertIs(self.m.tiene_avx2('linux', sin), False)
        self.assertIsNone(self.m.tiene_avx2('linux', Path(self.temp.name) / 'no-existe'))
        self.assertIsNone(self.m.tiene_avx2('linux', self.cpuinfo('processor\t: 0\nmodel name\t: x\n')))
        self.assertIsNone(self.m.tiene_avx2('darwin'))

    def test_windows_usa_la_api_de_siempre(self):
        fake = SimpleNamespace(windll=SimpleNamespace(kernel32=SimpleNamespace(IsProcessorFeaturePresent=MagicMock(return_value=1))))
        with patch.object(self.m, 'ctypes', fake):
            self.assertIs(self.m.tiene_avx2('win32'), True)
            fake.windll.kernel32.IsProcessorFeaturePresent.return_value = 0
            self.assertIs(self.m.tiene_avx2('win32'), False)
        fake.windll.kernel32.IsProcessorFeaturePresent.assert_called_with(40)

    def test_main_falla_sin_avx2_y_avisa_si_no_se_sabe(self):
        with patch.object(self.m, 'tiene_avx2', return_value=False), patch.object(self.m, 'snapshot_download') as descarga:
            with self.assertRaises(SystemExit) as error:
                self.m.main()
        self.assertIn('AVX2 no está disponible', str(error.exception))
        descarga.assert_not_called()
        aviso = io.StringIO()
        with patch.object(self.m, 'tiene_avx2', return_value=None), patch.object(self.m, 'snapshot_download', side_effect=RuntimeError('alto')), \
                patch.object(self.m.shutil, 'disk_usage', return_value=SimpleNamespace(free=10**10)), \
                patch.object(self.m, 'ROOT', Path(self.temp.name) / 'modelo'), redirect_stderr(aviso):
            with self.assertRaisesRegex(RuntimeError, 'alto'):  # sigue hasta la descarga (aquí detenida)
                self.m.main()
        self.assertIn('no se pudo comprobar si el procesador tiene AVX2', aviso.getvalue())

    def test_la_verificacion_de_huellas_no_cambia(self):
        self.assertEqual(self.m.EXPECTED_SHA256['onnx/model_quint8_avx2.onnx'], '98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f')
        self.assertEqual(self.m.EXPECTED_SHA256['tokenizer.json'], '2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8')


LEER_AJUSTES = ("import json, django; django.setup(); from django.conf import settings as s\n"
                "print(json.dumps({'proxy': s.SECURE_PROXY_SSL_HEADER, 'redirect': s.SECURE_SSL_REDIRECT, 'hsts': s.SECURE_HSTS_SECONDS,"
                " 'sub': s.SECURE_HSTS_INCLUDE_SUBDOMAINS, 'preload': s.SECURE_HSTS_PRELOAD, 'static': s.STATIC_ROOT,"
                " 'proxies': s.REST_FRAMEWORK.get('NUM_PROXIES'), 'web': s.RASTREO_WEB_LANZAMIENTO_HABILITADO,"
                " 'cookie': s.SESSION_COOKIE_SECURE, 'csrf_cookie': s.CSRF_COOKIE_SECURE, 'origins': s.CSRF_TRUSTED_ORIGINS}))")
NUEVAS = ('DJANGO_BEHIND_PROXY', 'DJANGO_SECURE_SSL_REDIRECT', 'DJANGO_SECURE_HSTS_SECONDS', 'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS',
          'DJANGO_SECURE_HSTS_PRELOAD', 'DJANGO_STATIC_ROOT', 'DJANGO_NUM_PROXIES', 'RASTREO_WEB_LANZAMIENTO_HABILITADO')


class AjustesProduccionTests(SimpleTestCase):
    def leer(self, **env):
        base = {k: v for k, v in os.environ.items() if k not in NUEVAS}
        with patch.dict(os.environ, base, clear=True):
            return json.loads(ejecutar(LEER_AJUSTES, env, 'config.settings'))

    def test_sin_variables_los_valores_de_siempre(self):
        v = self.leer()
        self.assertEqual({k: v[k] for k in ('proxy', 'redirect', 'hsts', 'sub', 'preload', 'static', 'proxies', 'web')},
                         {'proxy': None, 'redirect': False, 'hsts': 0, 'sub': False, 'preload': False, 'static': None, 'proxies': None, 'web': True})

    def test_con_variables_de_produccion(self):
        v = self.leer(DJANGO_BEHIND_PROXY='True', DJANGO_SECURE_SSL_REDIRECT='True', DJANGO_SECURE_HSTS_SECONDS='3600',
                      DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS='True', DJANGO_SECURE_HSTS_PRELOAD='True', DJANGO_STATIC_ROOT='/srv/becanexo/static',
                      DJANGO_NUM_PROXIES='1', RASTREO_WEB_LANZAMIENTO_HABILITADO='False', SESSION_COOKIE_SECURE='True', CSRF_COOKIE_SECURE='True',
                      DJANGO_CSRF_TRUSTED_ORIGINS='https://demo.example.org')
        self.assertEqual(v, {'proxy': ['HTTP_X_FORWARDED_PROTO', 'https'], 'redirect': True, 'hsts': 3600, 'sub': True, 'preload': True,
                             'static': '/srv/becanexo/static', 'proxies': 1, 'web': False, 'cookie': True, 'csrf_cookie': True,
                             'origins': ['https://demo.example.org']})
