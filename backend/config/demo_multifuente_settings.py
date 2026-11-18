"""Configuracion exclusiva del ensayo visual sintetico; nunca apunta a desarrollo."""
from .settings import *  # noqa: F403,F401
import os

DATABASES['default']['NAME'] = 'test_becanexo_fusion_db'
DATABASES['default']['TEST'] = {'NAME': 'test_becanexo_fusion_db'}
ALLOWED_HOSTS = ['127.0.0.1']
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:5174']
SESSION_COOKIE_NAME = 'becanexo_demo_multifuente_session'
CSRF_COOKIE_NAME = 'becanexo_demo_multifuente_csrf'
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
# Solo en esta base aislada; el backend de correo en memoria impide tráfico SMTP.
AVISOS_CORREO_HABILITADOS = True
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''
BECANEXO_PUBLIC_BASE_URL = 'http://127.0.0.1:5174'
RASTREO_STORAGE_ROOT = os.environ.get('BECANEXO_DEMO_STORAGE_ROOT', '')
DEBUG = False
