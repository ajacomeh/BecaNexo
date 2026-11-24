"""Configuración de pruebas para integración continua y ejecución local de la suite. Sin secretos.

Hereda config.settings (que lee DB_NAME, DB_USER, DB_PASSWORD, DB_HOST y DB_PORT del entorno o de backend/.env)
y fija valores seguros para pruebas:
- correo exclusivamente en memoria (locmem), sin credenciales;
- almacén documental del rastreo en una carpeta temporal (RASTREO_STORAGE_ROOT_PRUEBAS si se indica; si no, una nueva).
  Nunca se usa RASTREO_STORAGE_ROOT del .env local, que apunta al archivo real;
- indicadores de rastreo y correo en sus valores seguros por defecto, ignorando los de un .env local.
DJANGO_SECRET_KEY debe venir del entorno (en CI, un valor ficticio solo de prueba).
"""
import tempfile
from pathlib import Path

from .settings import *  # noqa: F401,F403
from .settings import env

DEBUG = False

# Base de pruebas: el ejecutor crea test_becanexo_db a partir de la conexión configurada.
DATABASES['default']['TEST'] = {'NAME': env('DB_TEST_NAME', default='test_becanexo_db')}

# Correo exclusivamente en memoria, sin credenciales.
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''
DEFAULT_FROM_EMAIL = 'BecaNexo <no-reply@example.invalid>'

# Almacén documental temporal, fuera del repositorio y nunca el archivo real.
_storage = env('RASTREO_STORAGE_ROOT_PRUEBAS', default='') or tempfile.mkdtemp(prefix='becanexo-rastreo-')
Path(_storage).mkdir(parents=True, exist_ok=True)
RASTREO_STORAGE_ROOT = str(Path(_storage).resolve())

# Indicadores operativos con los valores seguros por defecto del código.
RASTREO_EXTRAORDINARIO_HABILITADO = False
RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS = False
RASTREO_CANDIDATO_PDF_HABILITADO = False
AVISOS_CORREO_HABILITADOS = False
