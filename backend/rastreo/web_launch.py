"""Despacho local del rastreo web; el navegador no controla el proceso trabajador.

En Windows usa `msvcrt` (bloqueo de archivo) y un proceso separado sin consola, como siempre. En Linux usa los
equivalentes estándar (`fcntl.flock` y una sesión nueva), de modo que importar este módulo, y con él las URL, no
depende de un módulo exclusivo de Windows.
"""
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

try:  # Windows
    import msvcrt
except ImportError:  # Linux y otros POSIX
    msvcrt = None
    import fcntl


def lanzamiento_web_habilitado():
    """Interruptor del demo: RASTREO_WEB_LANZAMIENTO_HABILITADO=False desactiva «Iniciar rastreo» desde la web."""
    return bool(getattr(settings, 'RASTREO_WEB_LANZAMIENTO_HABILITADO', True))


def _bloquear(handle):
    if msvcrt is not None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # BlockingIOError es un OSError


def _liberar(handle):
    if msvcrt is not None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def launch_root():
    return Path(getattr(settings, 'RASTREO_WEB_LAUNCH_ROOT', settings.BASE_DIR.parent / 'outputs' / 'rastreo' / 'web'))


def marker_path(source_id):
    return launch_root() / f'fuente-{source_id}.json'


def result_path(source_id):
    return launch_root() / f'resultado-{source_id}.json'


@contextmanager
def launch_lock():
    root = launch_root()
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'iniciar.lock').open('a+b') as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            _bloquear(handle)
        except OSError as exc:
            raise LaunchBusy('Otra solicitud de inicio está en curso.') from exc
        try:
            yield
        finally:
            handle.seek(0)
            _liberar(handle)


class LaunchBusy(Exception):
    pass


def spawn_detached(module, *arguments, cwd, environment=None):
    """Mismo lanzamiento sin consola para el trabajador y la prueba inocua."""
    # El proyecto local carga la configuración privada desde backend/.env.
    # Evitar transmitir cookies, claves y variables de proxy del servidor web.
    inherited = ('SystemRoot', 'WINDIR', 'PATH', 'PATHEXT', 'TEMP', 'TMP',
                 'RASTREO_EXTRAORDINARIO_HABILITADO')
    child_env = {name: os.environ[name] for name in inherited if name in os.environ}
    if environment is not None:
        child_env.update(environment)
    # Windows: proceso separado y sin consola (igual que siempre). POSIX: sesión nueva, desligada del servidor web.
    separado = ({'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS} if os.name == 'nt'
                else {'start_new_session': True})
    return subprocess.Popen(
        [sys.executable, '-m', module, *(str(value) for value in arguments)],
        cwd=cwd,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, env=child_env, **separado,
    )


def start_worker(source_id, actor_id, reason=None, extraordinary=False):
    """Crea marcador exclusivo antes de separar un proceso del servidor HTTP."""
    key = uuid.uuid4()
    marker = marker_path(source_id)
    accepted_at = datetime.now(timezone.utc).isoformat()
    receipt = launch_root() / f'solicitud-{source_id}-{key}.json'
    request = {'clave': str(key), 'fuente_id': source_id, 'actor_id': actor_id,
               'motivo': reason, 'extraordinario': extraordinary, 'aceptada_en': accepted_at}
    try:
        with marker.open('x', encoding='utf-8') as stream:
            json.dump(request, stream)
    except FileExistsError as exc:
        raise LaunchBusy('Hay un inicio pendiente de verificar.') from exc
    try:
        if extraordinary:
            with receipt.open('x', encoding='utf-8') as stream:
                json.dump(request, stream)
        result_path(source_id).unlink(missing_ok=True)
        spawn_detached('rastreo.web_worker', source_id, actor_id, key, launch_root(), cwd=settings.BASE_DIR)
    except (OSError, ValueError):
        marker.unlink(missing_ok=True)
        receipt.unlink(missing_ok=True)
        raise
    return key
