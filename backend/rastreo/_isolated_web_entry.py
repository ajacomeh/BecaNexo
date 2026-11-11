"""Solo pruebas aisladas: guardas de BD y red antes del trabajador oficial."""
import json
import os
import socket
import sys
import time
from unittest.mock import patch


def main():
    if os.environ.get('BECANEXO_ISOLATED_ONLY_DB') != 'test_becanexo_db':
        raise RuntimeError('Falta la guarda de base aislada.')
    if os.environ.get('DB_NAME') != 'test_becanexo_db':
        raise RuntimeError('La configuración apunta fuera de la base de pruebas.')
    if os.environ.get('DB_HOST') not in ('127.0.0.1', 'localhost', '::1'):
        raise RuntimeError('Solo se admite PostgreSQL local en esta prueba.')
    if not os.environ.get('RASTREO_STORAGE_ROOT'):
        raise RuntimeError('Falta almacenamiento documental temporal.')

    original_dns = socket.getaddrinfo

    def local_dns(host, *args, **kwargs):
        if host not in ('127.0.0.1', 'localhost', '::1'):
            raise RuntimeError('Se bloqueó una resolución externa en la prueba.')
        return original_dns(host, *args, **kwargs)

    with patch.object(socket, 'getaddrinfo', side_effect=local_dns):
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        import django
        django.setup()
        from django.db import connection
        if connection.settings_dict['NAME'] != 'test_becanexo_db':
            raise RuntimeError('Django no configuró la base aislada.')
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database()')
            actual = cursor.fetchone()[0]
        if actual != 'test_becanexo_db':
            raise RuntimeError('PostgreSQL no confirmó la base aislada.')
        if sys.argv[1:] == ['--preflight']:
            print(json.dumps({'base_configurada': connection.settings_dict['NAME'],
                              'base_efectiva': actual, 'red_externa_bloqueada': True}))
            return 0

        from convocatorias.siau_red import INDEX, NATIONAL_INDEX, PAGES, PDFS, ROBOTS, Downloader
        from convocatorias.test_siau import FIXTURE
        from rastreo.web_worker import main as worker_main

        def fake_http(url):
            time.sleep(1 if os.environ.get('BECANEXO_ISOLATED_CASE') == 'reinicio' else .4)
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /wp-admin/\n'
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, b'<div onclick="{&quot;max_num_pages&quot;:1}"></div>'
            if url in PAGES:
                return 200, {'content-type': 'text/html'}, FIXTURE.read_bytes()
            if url in PDFS:
                return 200, {'content-type': 'application/pdf'}, b'%PDF-1.4\nEvidencia sintetica aislada'
            raise RuntimeError('URL inesperada bloqueada por la prueba.')

        if os.environ.get('BECANEXO_ISOLATED_CASE') == 'fallo_hijo':
            with patch('rastreo.services.run_manual', side_effect=RuntimeError('mensaje sintético privado')):
                return worker_main()
        if os.environ.get('BECANEXO_ISOLATED_CASE') not in ('exito', 'reinicio'):
            raise RuntimeError('Caso aislado no autorizado.')
        with patch.object(Downloader, 'once', side_effect=fake_http):
            return worker_main()


if __name__ == '__main__':
    raise SystemExit(main())
