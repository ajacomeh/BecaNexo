"""Transición individual; HTTP simulado y escrituras solo en base aislada."""
import hashlib
import io
import json
import os
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from convocatorias.models import BorradorRastreo, Convocatoria, Institucion
from convocatorias.services import publicas
from convocatorias.siau_red import ROBOTS
from perfiles.models import Pais
from . import tests as base
from .models import CandidatoIndice, Ejecucion, Publicacion
from .services import enable_discovery, enable_national_discovery, run_candidate, set_paginated_discovery, snapshot


URL = 'https://siau.senescyt.gob.ec/beca-universidad-ecuatoriana-demo/'
TITLE = 'Beca Universidad Ecuatoriana Demo'
ROBOTS_TEXT = b'User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n'


def fiche(*, requirements=True, deadline=True, foreign=False, deadline_text='20 de noviembre de 2026'):
    offerer = ('Universidad Extranjera ofrece esta beca.' if foreign
               else 'Universidad Ecuatoriana Demo ofrece esta beca a estudiantes ecuatorianos.')
    parts = [f'<h1 class="entry-title">{TITLE}</h1><section>',
             '<p>¿Quiénes pueden aplicar?</p>',
             f'<p>{offerer} Programa de estudios de grado con apoyo académico verificable.</p>',
             '<p>¿Cuál es la cobertura?</p><p>Apoyo en matrícula.</p>']
    if deadline:
        parts.extend(['<p>POSTULA HASTA</p>', f'<p>{deadline_text}</p>'])
    if requirements:
        parts.extend(['<p>REQUISITOS GENERALES</p>', '<ol><li>Ser ciudadano ecuatoriano.</li></ol>'])
    parts.append('</section>')
    return ''.join(parts).encode()


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class CandidateTransitionTests(TransactionTestCase):
    setUpBase = base.RastreoTests.setUp
    source = base.RastreoTests.source

    def setUp(self):
        self.setUpBase()
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        source = self.source()
        enable_discovery(self.actor.pk, 'Índice sintético')
        enable_national_discovery(self.actor.pk, 'Nacionales sintéticas')
        self.source, _ = set_paginated_discovery(self.actor.pk, 'Paginación sintética', True)
        previous = timezone.now() - timedelta(days=2)
        self.metadata_run = Ejecucion.objects.create(fuente=self.source, solicitado_por=self.actor,
            origen='manual', inicio=previous, fin=previous, estado='finalizada',
            configuracion_snapshot=snapshot(self.source.pk), version_extractor='siau-metadatos/1')
        self.candidate = CandidatoIndice.objects.create(fuente=self.source, ultima_ejecucion=self.metadata_run,
            url_normalizada=URL, titulo_publico=TITLE, pagina=2, respuesta_sha256=hashlib.sha256(b'index').hexdigest())
        country = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})[0]
        Institucion.objects.create(nombre='Universidad Ecuatoriana Demo', sector='publico', pais=country)

    def execute(self, html=None, status=200, headers=None, key=None):
        calls = []
        def network(url):
            calls.append(url)
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, ROBOTS_TEXT
            self.assertEqual(url, URL)
            return status, headers or {'content-type': 'text/html'}, html or fiche()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_candidate(self.candidate.pk, self.actor.pk, key or uuid.uuid4(), 'Validación sintética')
        run.refresh_from_db()
        return run, calls

    def test_valid_candidate_creates_private_draft_with_evidence(self):
        run, calls = self.execute()
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(calls, [ROBOTS, URL])
        publication = Publicacion.objects.get(fuente=self.source, url_normalizada=URL)
        origin = BorradorRastreo.objects.get(publicacion=publication)
        self.assertEqual(origin.version.documentos.filter(rol='ficha_html').count(), 1)
        self.assertEqual(origin.convocatoria.estado, 'borrador')
        self.assertFalse(publicas().filter(pk=origin.convocatoria_id).exists())
        # El llenado asigna la entidad cuando la ficha nombra a una existente (el oferente ya no queda siempre vacío).
        self.assertEqual(origin.convocatoria.institucion.nombre, 'Universidad Ecuatoriana Demo')
        self.assertEqual(run.configuracion_snapshot['solicitud_manual']['candidato_id'], self.candidate.pk)

    @override_settings(RASTREO_CANDIDATO_PDF_HABILITADO=True)
    def test_siau_and_generic_portal_keep_private_drafts_and_frequency_separate(self):
        from .services import register_generic_portal, set_portal_active, set_frequency, run_manual, next_due
        from convocatorias.services import publicas
        from datetime import timedelta
        from .test_evidencia_pdf import pdf_pages
        self.source, _ = set_frequency(self.source.pk, self.actor.pk, 'Intervalo SIAU del ensayo', 1440)
        siau_key = uuid.uuid4()
        pdf_url = 'https://siau.senescyt.gob.ec/wp-content/uploads/2026/11/bases-demo-multifuente.pdf'
        closure = timezone.localdate() + timedelta(days=30)
        month = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
                 'septiembre', 'octubre', 'noviembre', 'diciembre')[closure.month - 1]
        closure_text = f'{closure.day} de {month} de {closure.year}'
        siau_html = fiche(deadline_text=closure_text).replace(
            b'</ol>', b'<li>Contar con estudios de grado concluidos.</li></ol>').replace(
            b'</section>', f'<a href="{pdf_url}">BASES</a></section>'.encode())
        pdf = pdf_pages(['Bases sinteticas de beca nacional', 'Requisitos generales',
                         'Ser ciudadano ecuatoriano', 'Estudios de grado concluidos',
                         f'Cierre {closure_text}'])
        siau_calls = []
        def siau_network(url):
            siau_calls.append(url)
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, ROBOTS_TEXT
            if url == URL:
                return 200, {'content-type': 'text/html'}, siau_html
            self.assertEqual(url, pdf_url)
            return 200, {'content-type': 'application/pdf'}, pdf
        with patch('convocatorias.siau_red.Downloader.once', side_effect=siau_network):
            siau_run = run_candidate(self.candidate.pk, self.actor.pk, siau_key, 'Validación sintética')
        siau_run.refresh_from_db()
        self.assertEqual(siau_run.estado, 'finalizada')
        self.assertEqual(siau_calls, [ROBOTS, URL, pdf_url])
        generic_index = 'https://becas.universidad.edu.ec/becas/'
        generic, _ = register_generic_portal(
            self.actor.pk, 'Universidad institucional sintética', generic_index,
            'becas.universidad.edu.ec', 'Acceso simulado exclusivamente en la base aislada',
            max_pages=1, max_depth=0, max_cards=2, access_verified=True)
        self.assertFalse(generic.activa)
        set_portal_active(generic.pk, self.actor.pk, 'Activación del fixture aislado', True)
        generic_html = (b'<html><h2>Estudiantes de nuevo ingreso</h2>'
            b'<h3>Beca de merito academico</h3>'
            b'<p>Universidad institucional sintetica ofrece esta beca a ciudadanos ecuatorianos.</p>'
            b'<h4>Requisitos</h4><p>Ser estudiante ecuatoriano activo.</p>' +
            f'<p>Cierre: {closure_text}.</p></html>'.encode())
        generic_calls = []
        def generic_network(url):
            generic_calls.append(url)
            if url == 'https://becas.universidad.edu.ec/robots.txt':
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /privado/\n'
            self.assertEqual(url, generic_index)
            return 200, {'content-type': 'text/html'}, generic_html

        generic_key = uuid.uuid4()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=generic_network):
            generic_run = run_manual(generic.pk, self.actor.pk, generic_key)
        generic_run.refresh_from_db()
        self.assertEqual(generic_run.estado, 'finalizada')
        self.assertEqual(generic_calls, ['https://becas.universidad.edu.ec/robots.txt', generic_index])

        origins = list(BorradorRastreo.objects.select_related('publicacion', 'convocatoria').order_by('id'))
        self.assertEqual(len(origins), 2)
        self.assertEqual({row.publicacion.fuente_id for row in origins}, {self.source.pk, generic.pk})
        self.assertEqual(len({row.convocatoria.clave_deduplicacion for row in origins}), 2)
        self.assertTrue(all(row.convocatoria.revision == 'pendiente' for row in origins))
        self.assertFalse(publicas().exists())
        self.assertEqual(Publicacion.objects.filter(fuente=self.source).count(), 1)
        self.assertEqual(Publicacion.objects.filter(fuente=generic).count(), 1)
        self.assertEqual(BorradorRastreo.objects.get(publicacion__fuente=self.source)
                         .version.documentos.filter(rol='bases_pdf').count(), 1)
        self.assertEqual(next_due(self.source), siau_run.inicio + timedelta(minutes=self.source.frecuencia_min))
        self.assertEqual(next_due(generic), generic_run.inicio + timedelta(minutes=generic.frecuencia_min))
        self.assertNotEqual(self.source.frecuencia_min, generic.frecuencia_min)
        with patch('convocatorias.siau_red.Downloader.once') as network:
            self.assertEqual(run_candidate(self.candidate.pk, self.actor.pk, siau_key,
                                           'Validación sintética').pk, siau_run.pk)
            self.assertEqual(run_manual(generic.pk, self.actor.pk, generic_key).pk, generic_run.pk)
            network.assert_not_called()
        self.assertEqual((Publicacion.objects.count(), BorradorRastreo.objects.count(),
                          Convocatoria.objects.count()), (2, 2, 2))
        admin = APIClient()
        admin.force_login(self.actor)
        publications_api = admin.get('/api/gestion/rastreo/publicaciones/')
        runs_api = admin.get('/api/gestion/rastreo/ejecuciones/')
        drafts_api = admin.get('/api/gestion/convocatorias/?revision=pendiente')
        self.assertEqual([response.status_code for response in
                          (publications_api, runs_api, drafts_api)], [200, 200, 200])
        self.assertEqual((publications_api.data['count'], drafts_api.data['count']), (2, 2))
        self.assertEqual(APIClient().get('/api/becas/').data['count'], 0)
        print(json.dumps({'demo': 'multifuente_sintetica',
                          'fuentes': [{'id': row.pk, 'adaptador': row.adaptador,
                                       'frecuencia_min': row.frecuencia_min}
                                      for row in (self.source, generic)],
                          'ejecuciones': [siau_run.pk, generic_run.pk],
                          'publicaciones': [row.publicacion_id for row in origins],
                          'versiones': [row.version_id for row in origins],
                          'borradores_privados': [row.convocatoria_id for row in origins],
                          'api_admin': {'publicaciones': publications_api.data['count'],
                                        'ejecuciones': runs_api.data['count'],
                                        'borradores': drafts_api.data['count']},
                          'catalogo_publico': 0}, ensure_ascii=False))
        if os.environ.get('BECANEXO_DEMO_VISUAL') == '1':
            from getpass import getpass
            from http.cookiejar import CookieJar
            from pathlib import Path
            from urllib.request import Request, build_opener, HTTPCookieProcessor
            import secrets
            import socket
            import subprocess
            import sys
            import time

            self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
            smoke = os.environ.get('BECANEXO_DEMO_VISUAL_SMOKE') == '1'
            password = secrets.token_urlsafe(18) if smoke else getpass(
                'Contraseña TEMPORAL para rastreo-admin@example.com (mínimo 12 caracteres): ')
            if len(password) < 12:
                raise ValueError('La contraseña temporal debe tener al menos 12 caracteres.')
            self.actor.set_password(password)
            self.actor.save(update_fields=['password'])
            demo = self.prepare_integral_visual(origins, password)
            repo = Path(__file__).resolve().parents[2]
            for port in (8001, 5174):
                with socket.socket() as probe:
                    probe.settimeout(1)
                    if probe.connect_ex(('127.0.0.1', port)) == 0:
                        raise RuntimeError(f'El puerto {port} ya tiene un servidor; cierra esa demostración antes de iniciar otra.')
            environment = os.environ.copy()
            environment['BECANEXO_DEMO_STORAGE_ROOT'] = self.temp.name
            environment['AVISOS_CORREO_HABILITADOS'] = 'False'
            environment['GMAIL_SMTP_USER'] = ''
            environment['GMAIL_APP_PASSWORD'] = ''
            processes = []
            try:
                processes.append(subprocess.Popen(
                    [sys.executable, 'manage.py', 'runserver', '127.0.0.1:8001', '--noreload',
                     '--settings=config.demo_multifuente_settings'],
                    cwd=repo / 'backend', env=environment, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL))
                processes.append(subprocess.Popen(
                    ['node', 'node_modules/vite/bin/vite.js', '--config', 'vite.demo-multifuente.config.js',
                     '--host', '127.0.0.1', '--port', '5174'],
                    cwd=repo / 'frontend', env=environment, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL))
                opener = build_opener(HTTPCookieProcessor(CookieJar()))
                for url in ('http://127.0.0.1:8001/api/auth/csrf/', 'http://127.0.0.1:5174/'):
                    for _ in range(40):
                        if any(proc.poll() is not None for proc in processes):
                            raise RuntimeError('Un servidor de demostración terminó antes de estar disponible.')
                        try:
                            with opener.open(url, timeout=2) as response:
                                if response.status == 200:
                                    break
                        except (OSError, TimeoutError):
                            time.sleep(0.25)
                    else:
                        raise RuntimeError(f'El servidor de demostración no respondió: {url}')
                with opener.open('http://127.0.0.1:8001/api/auth/csrf/') as response:
                    csrf = json.load(response)['csrfToken']
                login = Request('http://127.0.0.1:8001/api/auth/login/',
                    data=json.dumps({'email': self.actor.email, 'password': password}).encode(),
                    headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf,
                             'Origin': 'http://127.0.0.1:5174'}, method='POST')
                with opener.open(login) as response:
                    self.assertEqual(response.status, 200)
                with opener.open('http://127.0.0.1:8001/api/gestion/rastreo/publicaciones/') as response:
                    self.assertEqual(json.load(response)['count'], 2)
                with opener.open('http://127.0.0.1:8001/api/gestion/convocatorias/?revision=pendiente') as response:
                    self.assertEqual(json.load(response)['count'], 1)
                for origin in origins:
                    documents_url = (f'http://127.0.0.1:8001/api/gestion/rastreo/publicaciones/'
                                     f'{origin.publicacion_id}/versiones/{origin.version_id}/documentos/')
                    with opener.open(documents_url) as response:
                        self.assertGreaterEqual(json.load(response)['count'], 1)
                with opener.open('http://127.0.0.1:8001/api/becas/') as response:
                    self.assertEqual(json.load(response)['count'], 1)
                for suffix, expected, notices in (('apto', 'cumple', 1), ('no-apto', 'no_cumple', 0)):
                    applicant = build_opener(HTTPCookieProcessor(CookieJar()))
                    with applicant.open('http://127.0.0.1:8001/api/auth/csrf/') as response:
                        applicant_csrf = json.load(response)['csrfToken']
                    request = Request('http://127.0.0.1:8001/api/auth/login/',
                        data=json.dumps({'email': f'postulante-{suffix}@example.com',
                                         'password': password}).encode(),
                        headers={'Content-Type': 'application/json', 'X-CSRFToken': applicant_csrf,
                                 'Origin': 'http://127.0.0.1:5174'}, method='POST')
                    with applicant.open(request) as response:
                        self.assertEqual(response.status, 200)
                    with applicant.open('http://127.0.0.1:8001/api/becas/recomendaciones/') as response:
                        recommendation = json.load(response)['results']
                    self.assertEqual(recommendation[0]['elegibilidad'], expected)
                    self.assertEqual(recommendation[0]['afinidad']['estado'], 'calculada')
                    with applicant.open('http://127.0.0.1:8001/api/notificaciones/') as response:
                        self.assertEqual(json.load(response)['count'], notices)
                print('DEMOSTRACIÓN VISUAL AISLADA: http://127.0.0.1:5174/login')
                print('Cuentas temporales: rastreo-admin@example.com, postulante-apto@example.com, postulante-no-apto@example.com.')
                print('Usa la contraseña temporal elegida solo en esta terminal; cierra sesión para cambiar de cuenta.')
                print('Panel: http://127.0.0.1:5174/gestion/rastreo')
                print(f'Beca publicada: http://127.0.0.1:5174/becas/{demo["convocatoria"]}')
                print('Postulantes: http://127.0.0.1:5174/inicio y http://127.0.0.1:5174/notificaciones')
                print('Cierre: regresa a esta terminal y pulsa Enter; se cerrarán servidores y fixtures.')
                if not smoke:
                    try:
                        input('Pulsa Enter para cerrar la demostración: ')
                    except (EOFError, KeyboardInterrupt):
                        print('Cierre solicitado; limpiando la demostración aislada.')
            finally:
                for proc in reversed(processes):
                    if proc.poll() is None:
                        if os.name == 'nt':
                            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                check=False, timeout=10)
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)

    def prepare_integral_visual(self, origins, password):
        """Completa solo el fixture aislado mediante la API editorial vigente."""
        from django.contrib.auth import get_user_model
        from django.core import mail
        from notificaciones.correo import procesar_pendientes
        from notificaciones.models import EntregaCorreo, Notificacion, PreferenciaCorreo
        from perfiles.models import Area, Formacion, Perfil, PerfilArea, Preferencia
        from convocatorias.models import Evento, TipoRequisito

        call_command('cargar_catalogos_convocatorias', verbosity=0)
        ec = Pais.objects.get(codigo='EC')
        area = Area.objects.create(nombre='Educación sintética de demostración')
        users = []
        for suffix, level, career, mode in (
            ('apto', 'grado', 'Pedagogía sintética', 'virtual'),
            ('no-apto', 'bachillerato', 'Bachillerato sintético', 'presencial'),
        ):
            user = get_user_model().objects.create_user(
                email=f'postulante-{suffix}@example.com', nombre=f'Postulante {suffix}', password=password)
            profile = Perfil.objects.create(usuario=user, nacionalidad=ec,
                descripcion=f'Interés en educación y formación académica {career}.')
            Formacion.objects.create(perfil=profile, nivel=level, carrera=career,
                titulo_obtenido=True, estado_estudios='concluidos')
            PerfilArea.objects.create(perfil=profile, area=area)
            Preferencia.objects.create(perfil=profile, nivel=level, modalidad=mode)
            users.append(user)
        eligible, incompatible = users
        PreferenciaCorreo.objects.create(usuario=eligible, habilitada=True)
        self.assertFalse(PreferenciaCorreo.objects.filter(usuario=incompatible, habilitada=True).exists())

        admin = APIClient(enforce_csrf_checks=True)
        csrf = admin.get('/api/auth/csrf/').data['csrfToken']
        login = admin.post('/api/auth/login/', {'email': self.actor.email, 'password': password},
            format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(login.status_code, 200, login.data)
        csrf = login.data['csrfToken']
        origin = next(row for row in origins if row.publicacion.fuente_id == self.source.pk)
        offer = origin.convocatoria
        publish_path = f'/api/gestion/convocatorias/{offer.pk}/publicar/'
        blocked = admin.post(publish_path, {}, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(blocked.status_code, 400, blocked.data)
        self.assertFalse(publicas().filter(pk=offer.pk).exists())
        institution = Institucion.objects.get(nombre='Universidad Ecuatoriana Demo')
        update = admin.patch(f'/api/gestion/convocatorias/{offer.pk}/',
            {'institucion': institution.pk, 'url_oficial': origin.publicacion.url_original,
             'areas': [area.pk]}, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(update.status_code, 200, update.data)
        option = admin.post(f'/api/gestion/convocatorias/{offer.pk}/opciones/',
            {'nivel': 'grado', 'modalidad': 'virtual', 'programa': 'Programa sintético de grado',
             'paises': [ec.pk]}, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(option.status_code, 201, option.data)
        requirement = admin.post(f'/api/gestion/convocatorias/{offer.pk}/requisitos/',
            {'tipo_requisito': TipoRequisito.objects.get(codigo='FORMACION').pk,
             'texto_original': 'Contar con estudios de grado concluidos.',
             'valor_estructurado': {'niveles_admitidos': ['grado'], 'estado_exigido': 'concluidos',
                                    'titulo_obtenido': True},
             'modo_comprobacion': 'dato_declarado', 'obligatorio': True, 'validado': True,
             'referencia_bases': origin.publicacion.url_original},
            format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(requirement.status_code, 201, requirement.data)
        published = admin.post(publish_path, {}, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(published.status_code, 200, published.data)
        offer.refresh_from_db()
        self.assertTrue(publicas().filter(pk=offer.pk).exists())
        self.assertTrue(Evento.objects.filter(convocatoria=offer, actor=self.actor, accion='publicar').exists())

        results = {}
        for suffix, user, expected in (('apto', eligible, 'cumple'), ('no-apto', incompatible, 'no_cumple')):
            client = APIClient()
            self.assertTrue(client.login(email=user.email, password=password))
            comparison = client.get(f'/api/becas/{offer.pk}/comparacion/')
            recommendation = client.get('/api/becas/recomendaciones/')
            inbox = client.get('/api/notificaciones/')
            self.assertEqual((comparison.status_code, recommendation.status_code, inbox.status_code),
                             (200, 200, 200))
            self.assertEqual(comparison.data['opciones'][0]['resultado'], expected)
            row = next(item for item in recommendation.data['results'] if item['convocatoria']['id'] == offer.pk)
            self.assertEqual(row['elegibilidad'], expected)
            self.assertEqual(row['afinidad']['estado'], 'calculada')
            self.assertEqual(inbox.data['count'], 1 if suffix == 'apto' else 0)
            results[suffix] = {'comparacion': expected, 'afinidad': row['afinidad']['estado'],
                               'notificaciones': inbox.data['count']}
        self.assertEqual(Notificacion.objects.count(), 1)
        self.assertEqual(EntregaCorreo.objects.count(), 1)
        self.assertEqual(EntregaCorreo.objects.get().notificacion.usuario_id, eligible.pk)
        self.assertEqual(procesar_pendientes(limite=1)['enviados'], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [eligible.email])
        again = admin.post(publish_path, {}, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual((Publicacion.objects.count(), BorradorRastreo.objects.count(),
                          Notificacion.objects.count(), EntregaCorreo.objects.count()), (2, 2, 1, 1))
        self.assertEqual(procesar_pendientes(limite=1)['enviados'], 0)
        print(json.dumps({'demo_integral': 'sintetica', 'convocatoria_publicada': offer.pk,
                          'borrador_privado': next(row.convocatoria_id for row in origins if row.pk != origin.pk),
                          'perfiles': results, 'correo_simulado': 'enviado_en_memoria',
                          'destinatario': eligible.email, 'duplicados': 0}, ensure_ascii=False))
        return {'convocatoria': offer.pk}

    def test_individual_candidate_under_v3_keeps_ordinary_policy(self):
        set_paginated_discovery(self.actor.pk, 'Conservar rastreo ordinario /3', False)
        run, calls = self.execute()
        self.source.refresh_from_db()
        self.assertEqual(self.source.politica_version, 'siau-nacionales/3')
        self.assertEqual(run.configuracion_snapshot['politica_version'], 'siau-nacionales/3')
        self.assertEqual(calls, [ROBOTS, URL])
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(Publicacion.objects.count(), 1)
        self.assertEqual(BorradorRastreo.objects.count(), 1)
        self.assertFalse(publicas().exists())

    def test_cli_processes_one_candidate_under_v3_with_idempotency(self):
        set_paginated_discovery(self.actor.pk, 'Conservar rastreo ordinario /3', False)
        key = uuid.uuid4()
        calls = []
        def network(url):
            calls.append(url)
            return ((200, {'content-type': 'text/plain'}, ROBOTS_TEXT) if url == ROBOTS
                    else (200, {'content-type': 'text/html'}, fiche()))
        output = io.StringIO()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            call_command('rastreo', 'procesar-candidato', candidato_id=self.candidate.pk,
                         actor_id=self.actor.pk, clave=str(key), motivo='Validación sintética', stdout=output)
            repeated = run_candidate(self.candidate.pk, self.actor.pk, key, 'Validación sintética')
        self.assertEqual(calls, [ROBOTS, URL])
        self.assertEqual(repeated.estado, 'finalizada')
        self.assertIn('"estado": "finalizada"', output.getvalue())
        self.assertEqual(Ejecucion.objects.filter(fuente=self.source).count(), 2)

    def test_partial_without_deadline_or_requirements_stays_private_and_pending(self):
        run, _ = self.execute(fiche(requirements=False, deadline=False))
        self.assertEqual(run.estado, 'finalizada')
        origin = BorradorRastreo.objects.get(publicacion__url_normalizada=URL)
        self.assertIsNone(origin.convocatoria.cierre_dia)
        self.assertIn('Verificar requisitos', ' '.join(origin.pendientes_iniciales))
        # pending_for_publication solo revisa el enlace oficial; los demás faltantes (p. ej. la opción de estudio)
        # los informa errores_publicacion, que es lo que bloquea publicar.
        from convocatorias.services import errores_publicacion
        self.assertTrue(any('opción activa' in note for note in errores_publicacion(origin.convocatoria, estricto=False)))

    def test_national_fiche_without_identified_offerer_creates_editable_private_draft(self):
        from .auto_borradores import prepare_automatic_draft, pending_for_publication
        title = 'Programa de Becas Nacionales de prueba'
        self.candidate.titulo_publico = title
        self.candidate.save(update_fields=['titulo_publico'])
        html = fiche(requirements=False, deadline=False).replace(TITLE.encode(), title.encode()).replace(
            b'Universidad Ecuatoriana Demo ofrece esta beca a estudiantes ecuatorianos.',
            b'Este programa apoya estudios de grado; la institucion oferente debe verificarse.')
        run, _ = self.execute(html)
        self.assertEqual(run.estado, 'finalizada')
        origin = BorradorRastreo.objects.get(publicacion__url_normalizada=URL)
        offer = origin.convocatoria
        self.assertIsNone(offer.institucion_id)
        self.assertTrue(any('entidad oferente' in note for note in origin.pendientes_iniciales))
        # La entidad oferente la exige errores_publicacion (pending_for_publication solo revisa el enlace oficial).
        from convocatorias.services import errores_publicacion
        self.assertTrue(any('institución oferente' in note for note in errores_publicacion(offer, estricto=False)))
        repeated, created, _ = prepare_automatic_draft(origin.publicacion_id, origin.version_id, allow_partial=True)
        self.assertFalse(created)
        self.assertEqual(repeated.pk, origin.pk)
        self.assertEqual(BorradorRastreo.objects.count(), 1)
        self.assertFalse(publicas().filter(pk=offer.pk).exists())
        self.assertEqual(APIClient().get(f'/api/becas/{offer.pk}/').status_code, 404)
        from convocatorias.services import publicar
        from rest_framework.exceptions import ValidationError as PublicationError
        with self.assertRaises(PublicationError):
            publicar(offer)

        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        token = admin.get('/api/auth/csrf/').data['csrfToken']
        institution = Institucion.objects.get(nombre='Universidad Ecuatoriana Demo')
        response = admin.patch(f'/api/gestion/convocatorias/{offer.pk}/',
            {'institucion': institution.pk}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.data)
        offer.refresh_from_db()
        self.assertEqual(offer.institucion_id, institution.pk)
        self.assertFalse(publicas().filter(pk=offer.pk).exists())
        # La participación ecuatoriana ya no es un paso aparte: publicar exige la entidad ecuatoriana seleccionada
        # (mismo criterio que test_auto_borradores).
        self.assertFalse(any('participación ecuatoriana' in note for note in pending_for_publication(offer, origin)))

    def test_foreign_offerer_is_only_detected_publication(self):
        run, _ = self.execute(fiche(foreign=True))
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(Publicacion.objects.count(), 1)
        self.assertEqual(BorradorRastreo.objects.count(), 0)
        self.assertTrue(run.incidencias.filter(codigo='CANDIDATO_PENDIENTE').exists())

    def test_closed_opportunity_keeps_evidence_without_open_catalog_entry(self):
        run, _ = self.execute(fiche(deadline_text='20 de noviembre de 2020'))
        self.assertEqual(run.estado, 'finalizada')
        origin = BorradorRastreo.objects.get(publicacion__url_normalizada=URL)
        self.assertEqual(origin.convocatoria.cierre_dia.isoformat(), '2020-11-20')
        self.assertFalse(publicas().filter(pk=origin.convocatoria_id).exists())

    def test_existing_publication_uses_same_identity(self):
        existing = Publicacion.objects.create(fuente=self.source, url_original=URL,
            url_normalizada=URL, normalizacion_version='urls-cerradas/1')
        run, _ = self.execute()
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(Publicacion.objects.get(url_normalizada=URL).pk, existing.pk)
        self.assertEqual(Publicacion.objects.count(), 1)

    def test_http_backoff_has_no_publication_or_draft(self):
        run, _ = self.execute(status=429, headers={'retry-after': '3600'})
        self.assertEqual(run.estado, 'fallida')
        self.assertEqual(Publicacion.objects.count(), 0)
        self.assertEqual(BorradorRastreo.objects.count(), 0)
        self.assertTrue(run.incidencias.filter(codigo='REINTENTO_FUENTE').exists())

    def test_http_503_without_retry_after_blocks_next_attempt(self):
        first, calls = self.execute(status=503)
        self.assertEqual(first.estado, 'fallida')
        self.assertEqual(calls, [ROBOTS, URL])
        second, calls = self.execute()
        self.assertEqual(second.estado, 'omitida')
        self.assertEqual(calls, [])
        self.assertEqual(Publicacion.objects.count(), 0)

    def test_v3_individual_http_503_blocks_next_attempt(self):
        set_paginated_discovery(self.actor.pk, 'Conservar rastreo ordinario /3', False)
        first, calls = self.execute(status=503)
        self.assertEqual(first.estado, 'fallida')
        self.assertEqual(calls, [ROBOTS, URL])
        second, calls = self.execute()
        self.assertEqual(second.estado, 'omitida')
        self.assertEqual(calls, [])
        self.assertFalse(Publicacion.objects.exists())

    def test_idempotency_and_frequency_gate(self):
        key = uuid.uuid4()
        first, _ = self.execute(key=key)
        second, calls = self.execute(key=key)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(calls, [])
        self.assertEqual(Publicacion.objects.count(), 1)
        with self.assertRaises(ValidationError):
            run_candidate(self.candidate.pk, self.actor.pk, key, 'Otro motivo')
        set_paginated_discovery(self.actor.pk, 'Revertir solo en pruebas', False)
        omitted, calls = self.execute()
        self.assertEqual(omitted.estado, 'omitida')
        self.assertIn('frecuencia', omitted.error_resumen)
        self.assertEqual(calls, [])
