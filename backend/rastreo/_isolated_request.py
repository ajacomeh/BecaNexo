"""Solo pruebas: una solicitud Django en un proceso independiente y aislado."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch


def main():
    if len(sys.argv) != 5:
        return 2
    mode, actor_id, root, case = sys.argv[1:]
    if os.environ.get('BECANEXO_ISOLATED_ONLY_DB') != 'test_becanexo_db' or os.environ.get('DB_NAME') != 'test_becanexo_db':
        raise RuntimeError('La solicitud aislada requiere la base de pruebas.')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.db import connection
    from django.test import override_settings
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from rastreo.web_launch import spawn_detached

    if connection.settings_dict['NAME'] != 'test_becanexo_db':
        raise RuntimeError('Configuración de base inesperada.')
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        if cursor.fetchone()[0] != 'test_becanexo_db':
            raise RuntimeError('Conexión efectiva fuera de la base de pruebas.')
    root = Path(root)
    if not root.is_dir() or os.environ.get('RASTREO_STORAGE_ROOT') is None:
        raise RuntimeError('Almacenamiento aislado no confirmado.')
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(get_user_model().objects.get(pk=int(actor_id)))
    path = '/api/gestion/rastreo/control/'
    with override_settings(RASTREO_WEB_LAUNCH_ROOT=str(root)):
        token = client.get('/api/auth/csrf/').data['csrfToken']
        if mode == 'start':
            children = []
            def isolated_spawn(module, source_id, user_id, key, folder, *, cwd):
                if module != 'rastreo.web_worker' or str(folder) != str(root):
                    raise RuntimeError('Lanzamiento fuera del contrato aislado.')
                names = ('BECANEXO_ISOLATED_ONLY_DB', 'DB_NAME', 'DB_USER', 'DB_PASSWORD',
                         'DB_HOST', 'DB_PORT', 'RASTREO_STORAGE_ROOT', 'DJANGO_SECRET_KEY',
                         'DJANGO_ALLOWED_HOSTS')
                extra = {name: os.environ[name] for name in names}
                extra['BECANEXO_ISOLATED_CASE'] = case
                child = spawn_detached('rastreo._isolated_web_entry', source_id, user_id, key,
                                       folder, cwd=cwd, environment=extra)
                children.append(child.pid)
                return child
            with patch('rastreo.web_launch.spawn_detached', side_effect=isolated_spawn):
                response = client.post(path, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token)
            print(json.dumps({'http': response.status_code, 'clave': response.data.get('clave'),
                              'pid': children[0] if children else None}))
        elif mode == 'status':
            response = client.get(path)
            state = response.data
            print(json.dumps({'http': response.status_code, 'inicio_pendiente': state.get('inicio_pendiente'),
                              'requiere_revision': state.get('requiere_revision'),
                              'ejecucion_activa': state.get('ejecucion_activa'),
                              'ultimo_inicio_web': state.get('ultimo_inicio_web'),
                              'ultima_ejecucion': state.get('ultima_ejecucion')}, default=str))
        elif mode == 'repeat':
            response = client.post(path, {'motivo': 'Verificacion administrativa'}, format='json', HTTP_X_CSRFTOKEN=token)
            print(json.dumps({'http': response.status_code}))
        else:
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
