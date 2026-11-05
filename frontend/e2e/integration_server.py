"""Disposable validation harness. Refuses any database other than test_becanexo_db."""
import os
import sys
import json
from pathlib import Path
from io import StringIO
import tempfile
import uuid
from unittest.mock import patch

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
from django.conf import settings
settings.DATABASES['default']['NAME'] = 'test_becanexo_db'
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
settings.CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:5173']
settings.SESSION_COOKIE_SECURE = False
settings.CSRF_COOKIE_SECURE = False
import django
django.setup()
from django.db import connection
if connection.settings_dict['NAME'] != 'test_becanexo_db':
    raise RuntimeError('Solo se permite test_becanexo_db')
with connection.cursor() as cursor:
    cursor.execute('SELECT current_database()')
    if cursor.fetchone()[0] != 'test_becanexo_db':
        raise RuntimeError('Conexion fuera de la base de pruebas')

def validate_storage(value):
    storage = Path(value).resolve()
    if storage.parent != Path(tempfile.gettempdir()).resolve() or not storage.name.startswith('becanexo-validation-') or not storage.is_dir():
        raise RuntimeError('Se requiere un directorio temporal propio')
    return str(storage)
from django.core.management import call_command

if sys.argv[1] == 'seed':
    data = json.load(sys.stdin)
    settings.RASTREO_STORAGE_ROOT = validate_storage(data['storage'])
    if data.get('reset_test_db') is not True:
        raise RuntimeError('Se requiere confirmacion explicita de reinicio de pruebas')
    call_command('flush', interactive=False, stdout=StringIO())
    call_command('cargar_catalogos', stdout=StringIO())
    call_command('cargar_catalogos_convocatorias', stdout=StringIO())
    from usuarios.models import Usuario
    from convocatorias.demo_avances import load, EMAIL
    actor = Usuario.objects.create_user(data['admin'], 'Administracion sintetica', password=data['password'], rol='administrador')
    result = load(actor.pk, preview=False)
    student = Usuario.objects.get(email=EMAIL)
    student.set_password(data['password'])
    student.save(update_fields=['password'])
    # Only synthetic fixture bytes: no external HTTP and no real source execution.
    from rastreo.services import configure, run_manual
    from rastreo.tests import RastreoTests
    from rastreo.models import Version
    configure(actor.pk, 'Fuente sintetica para prueba aislada')
    source, _ = configure(actor.pk, 'Activacion sintetica aislada', active=True)
    fake = RastreoTests().fake
    with patch('convocatorias.siau_red.Downloader.once', side_effect=fake):
        run_manual(source.pk, actor.pk, uuid.uuid4())
    version = Version.objects.first()
    print(json.dumps({'student': EMAIL, 'offer': result['escenarios'][0]['id'], 'publication': version.publicacion_id, 'version': version.pk}))
elif sys.argv[1] == 'cleanup':
    if sys.argv[2:] != ['--test-db-only']:
        raise RuntimeError('Limpieza requiere --test-db-only')
    # La conexión y current_database ya se verificaron arriba antes de actuar.
    call_command('flush', interactive=False, stdout=StringIO())
elif sys.argv[1] == 'serve':
    settings.RASTREO_STORAGE_ROOT = validate_storage(sys.argv[2])
    call_command('runserver', '127.0.0.1:8765', use_reloader=False)

else:
    raise RuntimeError("Modo desconocido")
