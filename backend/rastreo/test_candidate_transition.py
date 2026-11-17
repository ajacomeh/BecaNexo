"""Transición individual; HTTP simulado y escrituras solo en base aislada."""
import hashlib
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from convocatorias.models import BorradorRastreo, Institucion
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

    def test_partial_without_deadline_or_requirements_stays_private_and_pending(self):
        run, _ = self.execute(fiche(requirements=False, deadline=False))
        self.assertEqual(run.estado, 'finalizada')
        origin = BorradorRastreo.objects.get(publicacion__url_normalizada=URL)
        self.assertIsNone(origin.convocatoria.cierre_dia)
        self.assertIn('Verificar requisitos', ' '.join(origin.pendientes_iniciales))
        from .auto_borradores import pending_for_publication
        self.assertTrue(pending_for_publication(origin.convocatoria, origin))

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

    def test_idempotency_and_policy_gate(self):
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
        self.assertEqual(calls, [])
