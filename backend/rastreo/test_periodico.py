import io
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.db import connection, connections
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase
from django.utils import timezone

from convocatorias.siau_red import INDEX, NATIONAL_INDEX, PDFS, ROBOTS
from convocatorias.test_siau import FIXTURE
from . import tests as base
from .descubrimiento import FICHA, BASE, candidate_url, index_pages, national_index_pages, national_ficha_content
from .models import Ejecucion, Publicacion, Version, Revision
from .services import enable_discovery, enable_national_discovery, revert_national_discovery, exclusion, run_manual, run_scheduled, set_frequency, summary

NEW_PAGE = 'https://siau.senescyt.gob.ec/programa-de-becas-nacionales-prueba-sintetica/'
NEW_PDF = 'https://siau.senescyt.gob.ec/wp-content/uploads/2026/11/bases-prueba.pdf'
NATIONAL_PAGE = 'https://siau.senescyt.gob.ec/oferta-de-becas-nacionales-educacion-continua-prueba/'


def national_index(other=''):
    return (f'<article class="category-convocatorias pais-ecuador"><h2 class="entry-title">'
            f'<a href="{NATIONAL_PAGE}">Oferta de Becas Nacionales para Educación Continua</a>'
            f'</h2></article>{other}<div onclick="{{&quot;max_num_pages&quot;:1}}"></div>').encode()


def national_ficha():
    return FIXTURE.read_text(encoding='utf8').replace(
        'PROGRAMA FICTICIO PARA PRUEBAS', 'Oferta de Becas Nacionales para Educación Continua').encode()


class PeriodicTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake

    def network(self, url):
        if url == INDEX:
            html = f'<html><a href="{NEW_PAGE}">Programa de becas sintético</a></html>'
            return 200, {'content-type': 'text/html'}, html.encode()
        return self.fake(url)

    def test_index_scope_rejects_external_queries_and_unrelated_paths(self):
        self.assertEqual(index_pages(f'<a href="{NEW_PAGE}">Beca</a>'.encode()), ([NEW_PAGE], False))
        for url in ('https://evil.example/programa-de-becas-nacionales-x/',
                    NEW_PAGE + '?token=secret', 'http://siau.senescyt.gob.ec/programa-de-becas-nacionales-x/',
                    'https://siau.senescyt.gob.ec/wp-admin/secret.pdf'):
            self.assertIsNone(candidate_url(url, FICHA))
        self.assertIsNone(candidate_url(NEW_PAGE, BASE))

    def test_national_index_requires_card_title_and_safe_url(self):
        foreign = ('<article class="category-convocatorias pais-ecuador"><h2 class="entry-title">'
                   '<a href="https://siau.senescyt.gob.ec/becas-internacionales-extranjera/">'
                   'Becas Internacionales de una universidad extranjera</a></h2></article>')
        unrelated = ('<a href="https://siau.senescyt.gob.ec/becas-nacionales-noticia/">'
                     'Becas Nacionales: noticia</a>')
        self.assertEqual(national_index_pages(national_index(foreign + unrelated)), ([NATIONAL_PAGE], False))
        self.assertTrue(national_ficha_content(national_ficha()))
        self.assertFalse(national_ficha_content(FIXTURE.read_bytes()))
        page = national_index().replace(b'max_num_pages&quot;:1', b'max_num_pages&quot;:3')
        self.assertEqual(national_index_pages(page), ([NATIONAL_PAGE], True))
        self.assertEqual(national_index_pages(national_index().split(b'<div onclick=')[0]), ([NATIONAL_PAGE], True))

    def test_national_discovery_is_audited_and_records_only_reviewable_candidate(self):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        source = self.source()
        enable_discovery(self.actor.pk, 'Índice anterior en prueba')
        key = uuid.uuid4()
        source, changed = enable_national_discovery(self.actor.pk, 'Índice nacional en prueba', key)
        self.assertTrue(changed)
        self.assertEqual(source.politica_version, 'siau-nacionales/3')
        again, changed = enable_national_discovery(self.actor.pk, 'Índice nacional en prueba', key)
        self.assertEqual(again.pk, source.pk)
        self.assertFalse(changed)
        self.assertEqual(Revision.objects.filter(dimension='configuracion').count(), 4)
        with self.assertRaises(ValidationError):
            enable_national_discovery(self.user.pk, 'Sin permiso')

        def network(url):
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, national_index()
            if url == NATIONAL_PAGE:
                return 200, {'content-type': 'text/html'}, national_ficha()
            return self.fake(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            first = run_manual(source.pk, self.actor.pk, uuid.uuid4())
            with patch('rastreo.services.timezone.now',
                       return_value=first.inicio + timedelta(minutes=source.frecuencia_min)):
                repeat = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(first)['estado'], 'finalizada')
        self.assertEqual(Publicacion.objects.count(), 3)
        publication = Publicacion.objects.get(url_normalizada=NATIONAL_PAGE)
        self.assertEqual(publication.versiones.count(), 1)
        self.assertEqual(publication.versiones.get().documentos.filter(rol='ficha_html').count(), 1)
        self.assertEqual(first.observaciones.filter(publicacion=publication, resultado='nueva').count(), 1)
        self.assertEqual(repeat.observaciones.filter(publicacion=publication, resultado='sin_cambios').count(), 1)
        self.assertTrue(first.accesos.filter(url_normalizada=NATIONAL_INDEX, rol='indice', documento__isnull=False).exists())
        self.assertFalse(Publicacion.objects.exclude(convocatoria=None).exists())
        self.assertFalse(Revision.objects.filter(dimension='documental').exists())

    def test_national_card_does_not_persist_changed_international_page(self):
        source = self.source()
        enable_discovery(self.actor.pk, 'Índice anterior en prueba')
        enable_national_discovery(self.actor.pk, 'Índice nacional en prueba')

        def network(url):
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, national_index()
            if url == NATIONAL_PAGE:
                return 200, {'content-type': 'text/html'}, national_ficha().replace(
                    b'Oferta de Becas Nacionales', b'Oferta de Becas Internacionales')
            return self.fake(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertFalse(Publicacion.objects.filter(url_normalizada=NATIONAL_PAGE).exists())
        self.assertTrue(run.incidencias.filter(codigo='FICHA_FUERA_ALCANCE').exists())

    def test_national_discovery_runs_scheduled_once_and_respects_frequency(self):
        source = self.source()
        enable_discovery(self.actor.pk, 'Índice anterior en prueba')
        enable_national_discovery(self.actor.pk, 'Índice nacional en prueba')

        def network(url):
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, national_index()
            if url == NATIONAL_PAGE:
                return 200, {'content-type': 'text/html'}, national_ficha()
            return self.fake(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as calls:
            execution = run_scheduled(source.pk)
            skipped = run_scheduled(source.pk)
        self.assertEqual(execution.pk, skipped.pk)
        self.assertEqual(execution.origen, 'programada')
        self.assertIsNone(execution.solicitado_por_id)
        self.assertEqual(Ejecucion.objects.count(), 1)
        self.assertEqual(Publicacion.objects.filter(url_normalizada=NATIONAL_PAGE).count(), 1)
        self.assertEqual(len(calls.call_args_list), execution.accesos.count())

    def test_national_ficha_blocked_by_robots_has_no_identity(self):
        source = self.source()
        enable_discovery(self.actor.pk, 'Índice anterior en prueba')
        enable_national_discovery(self.actor.pk, 'Índice nacional en prueba')

        def network(url):
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /oferta-de-becas-nacionales-educacion-continua-prueba/\n'
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, national_index()
            return self.fake(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as calls:
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertFalse(Publicacion.objects.filter(url_normalizada=NATIONAL_PAGE).exists())
        self.assertNotIn(NATIONAL_PAGE, [args[0][0] for args in calls.call_args_list])
        self.assertTrue(run.incidencias.filter(codigo='ROBOTS').exists())

    def test_national_policy_reversion_is_audited_and_keeps_history(self):
        source = self.source()
        enable_discovery(self.actor.pk, 'Índice anterior en prueba')
        enable_national_discovery(self.actor.pk, 'Índice nacional en prueba')
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        with self.assertRaises(ValidationError):
            revert_national_discovery(self.actor.pk, '   ')
        active = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor,
                                          configuracion_snapshot={}, version_extractor='prueba')
        with self.assertRaises(ValidationError):
            revert_national_discovery(self.actor.pk, 'No revertir durante ejecución')
        Ejecucion.objects.filter(pk=active.pk).update(estado='fallida', fin=timezone.now(), error_resumen='Prueba de exclusión')
        before = (Publicacion.objects.count(), Version.objects.count(), Ejecucion.objects.count())
        key = uuid.uuid4()
        source, changed = revert_national_discovery(self.actor.pk, 'Revertir índice en prueba', key)
        self.assertTrue(changed)
        self.assertEqual(source.politica_version, 'siau-indice/2')
        again, changed = revert_national_discovery(self.actor.pk, 'Revertir índice en prueba', key)
        self.assertFalse(changed)
        self.assertEqual(again.pk, source.pk)
        audit = Revision.objects.get(clave_accion=key)
        self.assertEqual(audit.detalle['antes']['politica_version'], 'siau-nacionales/3')
        self.assertEqual(audit.detalle['despues']['politica_version'], 'siau-indice/2')
        with self.assertRaises(ValidationError):
            revert_national_discovery(self.actor.pk, 'Motivo diferente', key)
        self.assertEqual((Publicacion.objects.count(), Version.objects.count(), Ejecucion.objects.count()), before)
        self.assertEqual(run.pk, Ejecucion.objects.get(pk=run.pk).pk)
        with self.assertRaises(ValidationError):
            revert_national_discovery(self.user.pk, 'Sin permiso')
        enable_national_discovery(self.actor.pk, 'Reactivar en prueba')
        output = io.StringIO()
        call_command('rastreo', 'revertir-nacionales', actor_id=self.actor.pk,
                     motivo='Reversión por CLI en prueba', clave=str(uuid.uuid4()), stdout=output)
        self.assertIn('"politica_version": "siau-indice/2"', output.getvalue())
        self.assertEqual((Publicacion.objects.count(), Version.objects.count(), Ejecucion.objects.count()), before)

    def test_national_zip_bases_remain_pending_without_losing_html_evidence(self):
        source = self.source()
        enable_discovery(self.actor.pk, 'Índice anterior en prueba')
        enable_national_discovery(self.actor.pk, 'Índice nacional en prueba')

        def network(url):
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, national_index()
            if url == NATIONAL_PAGE:
                html = national_ficha().replace(b'bn_4to_nivel_2026_13102026_vf-1.pdf', b'bases-occitec.zip')
                return 200, {'content-type': 'text/html'}, html
            return self.fake(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as calls:
            execution = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        # Un enlace de bases fuera de la lista cerrada es un aviso por diseño: la corrida no queda «parcial».
        self.assertEqual(summary(execution)['estado'], 'finalizada')
        publication = Publicacion.objects.get(url_normalizada=NATIONAL_PAGE)
        version = publication.versiones.get()
        self.assertEqual(version.documentos.filter(rol='ficha_html').count(), 1)
        self.assertFalse(version.documentos.filter(rol='bases_pdf').exists())
        self.assertTrue(execution.incidencias.filter(codigo='BASE_NO_PERMITIDA', publicacion=publication).exists())
        self.assertFalse(any(args[0][0].endswith('.zip') for args in calls.call_args_list))
        self.assertIsNone(publication.convocatoria_id)

    @base.ventana_cumplida()
    def test_discovery_requires_audited_policy_and_preserves_history(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_db')
        source = self.source()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.network):
            legacy = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(Publicacion.objects.count(), 2)
        self.assertFalse(Publicacion.objects.filter(url_normalizada=NEW_PAGE).exists())
        source, changed = enable_discovery(self.actor.pk, 'Ampliar índice en prueba')
        self.assertTrue(changed)
        self.assertEqual(source.politica_version, 'siau-indice/2')
        self.assertEqual(Revision.objects.filter(dimension='configuracion').count(), 3)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.network):
            discovered = run_manual(source.pk, self.actor.pk, uuid.uuid4())
            repeated = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(discovered)['estado'], 'finalizada')
        self.assertEqual(Publicacion.objects.count(), 3)
        self.assertEqual(discovered.observaciones.filter(resultado='nueva').count(), 1)
        self.assertEqual(repeated.observaciones.filter(resultado='sin_cambios').count(), 3)
        self.assertEqual(Version.objects.count(), 3)
        self.assertEqual(legacy.observaciones.count(), 2)
        self.assertFalse(Publicacion.objects.exclude(convocatoria=None).exists())
        self.assertEqual(Revision.objects.exclude(dimension='configuracion').count(), 0)

        def changed(url):
            if url == NEW_PAGE:
                html = FIXTURE.read_text(encoding='utf8').replace('$3000', '$2500')
                return 200, {'content-type': 'text/html'}, html.encode()
            return self.network(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=changed):
            altered = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(altered.observaciones.filter(resultado='cambio_relevante').count(), 1)
        self.assertEqual(Version.objects.count(), 4)
        self.assertEqual(Publicacion.objects.get(url_normalizada=NEW_PAGE).versiones.count(), 2)

    def test_scheduled_run_has_no_fake_actor_and_respects_frequency(self):
        source = self.source()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake):
            first = run_scheduled(source.pk)
            same = run_scheduled(source.pk)
        first.refresh_from_db()
        self.assertEqual(first.pk, same.pk)
        self.assertEqual(Ejecucion.objects.count(), 1)
        self.assertEqual(first.origen, 'programada')
        self.assertIsNone(first.solicitado_por_id)
        self.assertEqual(first.estado, 'finalizada')
        future = timezone.now() + timedelta(days=2)
        with patch('rastreo.services.timezone.now', return_value=future), patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake):
            second = run_scheduled(source.pk)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(second.observaciones.filter(resultado='sin_cambios').count(), 2)
        self.assertEqual(Version.objects.count(), 2)

    def test_scheduled_network_failure_is_recorded_without_publications(self):
        source = self.source()
        with patch('convocatorias.siau_red.Downloader.once', return_value=(404, {}, b'')):
            execution = run_scheduled(source.pk)
        execution.refresh_from_db()
        self.assertEqual(execution.estado, 'fallida')
        self.assertIsNone(execution.solicitado_por_id)
        self.assertFalse(Publicacion.objects.exists())
        self.assertTrue(execution.incidencias.exists())

    def test_new_pdf_is_exact_evidence_and_not_an_approval(self):
        source = self.source()
        enable_discovery(self.actor.pk, 'Ampliar índice en prueba')

        def network(url):
            if url == NEW_PAGE:
                html = FIXTURE.read_text(encoding='utf8').replace(PDFS[1].split('.ec')[1], NEW_PDF)
                return 200, {'content-type': 'text/html'}, html.encode()
            if url == NEW_PDF:
                return 200, {'content-type': 'application/pdf'}, b'%PDF-1.4\nBases nuevas sinteticas'
            return self.network(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'finalizada')
        version = Publicacion.objects.get(url_normalizada=NEW_PAGE).versiones.get()
        self.assertEqual(version.documentos.get(rol='bases_pdf').url_normalizada, NEW_PDF)
        self.assertFalse(Revision.objects.filter(dimension='documental', version=version).exists())
        self.assertTrue(run.incidencias.filter(codigo='REVISION_DOCUMENTAL_PENDIENTE').exists())

    def test_management_scheduler_runs_once_when_due(self):
        source = self.source()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake):
            call_command('rastreo', 'programado', fuente_id=source.pk, stdout=io.StringIO())
            result = io.StringIO()
            call_command('rastreo', 'programado', fuente_id=source.pk, stdout=result)
        self.assertIn('no_corresponde_aun', result.getvalue())
        self.assertEqual(Ejecucion.objects.count(), 1)
        self.assertEqual(Ejecucion.objects.get().origen, 'programada')

    def test_programming_status_is_read_only_and_uses_test_database(self):
        source = self.source()
        before = Ejecucion.objects.count()
        output = io.StringIO()
        call_command('rastreo', 'estado-programacion', fuente_id=source.pk, stdout=output)
        status = json.loads(output.getvalue())
        self.assertEqual(status['base'], 'test_becanexo_db')
        self.assertEqual(status['fuente_id'], source.pk)
        self.assertEqual(status['frecuencia_min'], source.frecuencia_min)
        self.assertFalse(status['aprobada_publicacion_automatica'])
        self.assertEqual(status['ejecuciones_en_curso'], 0)
        self.assertIsNone(status['ultima_ejecucion'])
        self.assertEqual(Ejecucion.objects.count(), before)

    def test_robots_blocks_new_candidate_without_fabricating_publication(self):
        source = self.source()
        enable_discovery(self.actor.pk, 'Ampliar índice en prueba')

        def network(url):
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /programa-de-becas-nacionales-prueba-sintetica/\n'
            return self.network(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as calls:
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(run.observaciones.count(), 2)
        self.assertFalse(Publicacion.objects.filter(url_normalizada=NEW_PAGE).exists())
        self.assertTrue(run.incidencias.filter(codigo='ROBOTS').exists())
        self.assertNotIn(NEW_PAGE, [args[0][0] for args in calls.call_args_list])

    def test_index_parser_failure_keeps_known_pages_with_incidence(self):
        source = self.source()
        enable_discovery(self.actor.pk, 'Ampliar índice en prueba')
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake), patch('rastreo.services.index_pages', side_effect=ValueError('sintético')):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'parcial')
        self.assertTrue(run.incidencias.filter(codigo='INDICE_ESTRUCTURA').exists())
        self.assertEqual(run.observaciones.count(), 2)

    def test_parallel_scheduled_attempt_is_omitted_without_network(self):
        source = self.source()

        def contender():
            connections.close_all()
            try:
                self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_db')
                return run_scheduled(source.pk).pk
            finally:
                connections.close_all()

        with exclusion(source.pk) as locked:
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                execution_id = pool.submit(contender).result(timeout=15)
        execution = Ejecucion.objects.get(pk=execution_id)
        self.assertEqual(execution.estado, 'omitida')
        self.assertEqual(execution.origen, 'programada')
        self.assertFalse(execution.accesos.exists())

    def test_index_limit_reports_partial_coverage(self):
        source = self.source()
        enable_discovery(self.actor.pk, 'Ampliar índice en prueba')
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.network), patch('rastreo.services.index_pages', return_value=([NEW_PAGE], True)):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'parcial')
        self.assertTrue(run.incidencias.filter(codigo='INDICE_LIMITE', gravedad='error').exists())

    def test_frequency_change_is_audited_and_idempotent(self):
        source = self.source()
        key = uuid.uuid4()
        changed, did_change = set_frequency(source.pk, self.actor.pk, 'Frecuencia de prueba', 1440, key)
        self.assertTrue(did_change)
        self.assertEqual(changed.frecuencia_min, 1440)
        same, did_change = set_frequency(source.pk, self.actor.pk, 'Frecuencia de prueba', 1440, key)
        self.assertFalse(did_change)
        self.assertEqual(same.pk, source.pk)
        audit = Revision.objects.get(clave_accion=key)
        self.assertEqual(audit.detalle['antes']['frecuencia_min'], 720)
        self.assertEqual(audit.detalle['despues']['frecuencia_min'], 1440)
        with self.assertRaises(ValidationError):
            set_frequency(source.pk, self.user.pk, 'Sin permiso', 720)
        with self.assertRaises(ValidationError):
            set_frequency(source.pk, self.actor.pk, 'Demasiado frecuente', 1)
        with patch('rastreo.services.Revision.objects.create', side_effect=RuntimeError('sintético')):
            with self.assertRaises(RuntimeError):
                set_frequency(source.pk, self.actor.pk, 'Revisión no guardada', 720)
        source.refresh_from_db()
        self.assertEqual(source.frecuencia_min, 1440)
        output = io.StringIO()
        call_command('rastreo', 'configurar-frecuencia', fuente_id=source.pk, actor_id=self.actor.pk,
                     motivo='Frecuencia por CLI', frecuencia_min=720, stdout=output)
        self.assertIn('"frecuencia_min": 720', output.getvalue())
