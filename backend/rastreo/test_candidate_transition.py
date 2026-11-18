"""Transición individual; HTTP simulado y escrituras solo en base aislada."""
import hashlib
import io
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
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_fusion_db')
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
        self.assertIsNone(origin.convocatoria.institucion_id)
        self.assertEqual(run.configuracion_snapshot['solicitud_manual']['candidato_id'], self.candidate.pk)

    @override_settings(RASTREO_CANDIDATO_PDF_HABILITADO=True)
    def test_siau_and_generic_portal_keep_private_drafts_and_frequency_separate(self):
        from .services import register_generic_portal, set_portal_active, set_frequency, run_manual, next_due
        from convocatorias.services import publicas
        from datetime import timedelta
        from .test_evidencia_pdf import pdf_pages
        import json

        self.source, _ = set_frequency(self.source.pk, self.actor.pk, 'Intervalo SIAU del ensayo', 1440)
        siau_key = uuid.uuid4()
        pdf_url = 'https://siau.senescyt.gob.ec/wp-content/uploads/2026/11/bases-demo-multifuente.pdf'
        siau_html = fiche().replace(b'</section>', f'<a href="{pdf_url}">BASES</a></section>'.encode())
        pdf = pdf_pages(['Bases sinteticas de beca nacional', 'Requisitos generales',
                         'Ser ciudadano ecuatoriano', 'Cierre 20 de noviembre de 2026'])
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
            b'<h4>Requisitos</h4><p>Ser estudiante ecuatoriano activo.</p>'
            b'<p>Cierre: 12 de noviembre de 2027.</p></html>')
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
        from .auto_borradores import pending_for_publication
        self.assertTrue(pending_for_publication(origin.convocatoria, origin))

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
        self.assertTrue(any('institución oferente' in note for note in pending_for_publication(offer, origin)))
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
        self.assertTrue(any('participación ecuatoriana' in note for note in pending_for_publication(offer, origin)))

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
