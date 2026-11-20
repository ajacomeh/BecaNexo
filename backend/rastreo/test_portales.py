"""Contratos de portales oficiales con red simulada y base aislada."""
import tempfile
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from convocatorias.models import BorradorRastreo, Convocatoria, Institucion
from convocatorias.services import publicas
from perfiles.models import Pais
from .models import Fuente, Incidencia, Publicacion, Revision, Version
from .portal_fuentes import PORTALES, admitted_url, extract_portal, extract_section, links, sections, choose_candidates
from .services import register_portal, run_manual, run_scheduled, set_portal_active


UTPL = PORTALES['utpl']
FICHA = 'https://becas.utpl.edu.ec/tipos-de-becas/beca-sintetica'
PDF = 'https://becas.utpl.edu.ec/documentos/bases.pdf'
INDEX_HTML = f'<html><a href="{FICHA}">Conoce más</a><a href="https://otro.example/beca">Otra</a></html>'.encode()
FICHA_HTML = (f'<html><main><h1>Beca sintética para ciudadanos ecuatorianos</h1>'
              '<p>Universidad ecuatoriana sintetica ofrece esta beca a personas ecuatorianas.</p>'
              '<h2>Requisitos</h2><p>Ser ciudadano ecuatoriano y estudiante activo.</p>'
              '<h2>Beneficio</h2><p>Cobertura parcial de matrícula.</p>'
              '<p>Cierre: 12 de noviembre de 2026</p>'
              f'<a href="{PDF}">Bases</a></main></html>').encode()


class PortalParserTests(SimpleTestCase):
    def test_closed_host_and_html_extraction(self):
        self.assertEqual(links(INDEX_HTML, UTPL.indice, UTPL), [FICHA])
        self.assertFalse(admitted_url(UTPL, FICHA + '?session=secret'))
        self.assertFalse(admitted_url(UTPL, 'https://becas.utpl.edu.ec:invalido/tipos-de-becas/beca'))
        item = extract_portal({'url': FICHA, 'consulta_utc': '2026-11-12T00:00:00Z', 'contenido': FICHA_HTML}, UTPL)
        self.assertEqual(item['cierre']['fecha'], '2026-11-12')
        self.assertEqual(item['enlaces_bases'][0]['url'], PDF)
        self.assertEqual(item['entidad_html']['texto_original'], '')
        self.assertTrue(item['seccion_completa'])

    def test_utpl_repeated_cards_are_deduplicated_and_rotate(self):
        urls = [f'{UTPL.indice}/beca-{number}' for number in range(18)]
        cards = ''.join(f'<a href="{url}">Conoce más</a>' for url in [*urls, *urls[:5]])
        found = links(f'<html>{cards}</html>'.encode(), UTPL.indice, UTPL)
        self.assertEqual(len(found), 18)  # 23 tarjetas, 18 URL distintas.
        first, truncated = choose_candidates(found, {}, UTPL.max_fichas)
        self.assertTrue(truncated)
        second, _ = choose_candidates(found, {url: '2026-11-12' for url in first}, UTPL.max_fichas)
        self.assertEqual(first, urls[:12])
        self.assertEqual(second[:6], urls[12:])

    def test_utpl_realistic_detail_keeps_coverage_and_postulation_reference(self):
        detail = UTPL.indice + '/abanderados-escoltas-mejores-egresados'
        html = (b'<html><h1>Abanderados, Escoltas y Mejores Egresados</h1>'
                b'<p>Esta beca aplica a estudiantes de grado.</p>'
                b'<p>PORCENTAJE</p><p>30% - 40% de descuento en matricula.</p>'
                b'<h2>Requisitos especificos</h2><p>Certificado de abanderado.</p>'
                b'<a href="https://ssb-prod.srv.utpl.edu.ec/solicitudes">Postular ahora</a>'
                b'</html>')
        item = extract_portal({'url': detail, 'consulta_utc': '2026-11-12T10:00:00Z', 'contenido': html}, UTPL)
        self.assertEqual(item['tipo_oportunidad'], 'tipo_de_beca_vigencia_desconocida')
        self.assertIn('30% - 40%', item['beneficio']['texto_original'])
        self.assertIn('Certificado', item['requisitos']['texto_original'])
        self.assertEqual(item['enlaces_postulacion'][0]['url'], 'https://ssb-prod.srv.utpl.edu.ec/solicitudes')
        self.assertIsNone(item['cierre']['fecha'])

    def test_ups_sections_have_stable_individual_identity_and_status(self):
        portal = PORTALES['ups']
        html = (b'<html><h4>Conoce las becas de grado</h4>'
                b'<h4>Beca Equidad Social</h4><p>Cobertura segun quintil.</p>'
                b'<h4>Beca Permanente</h4><p>Programa permanente para estudiantes.</p>'
                b'<h4>Beca Merito</h4><p>Requisitos: ciudadanos ecuatorianos.</p>'
                b'<p>Cierre: 12 de noviembre de 2026</p></html>')
        found = sections(html, portal)
        self.assertEqual(len(found), 3)
        self.assertEqual(len({section.identidad for section in found}), 3)
        items = [extract_section({'url': portal.indice, 'consulta_utc': '2026-11-12T10:00:00Z', 'contenido': html}, portal, section)
                 for section in found]
        self.assertEqual([item['tipo_oportunidad'] for item in items],
                         ['tipo_de_beca_vigencia_desconocida', 'programa_permanente', 'convocatoria_con_cierre'])
        self.assertEqual(items[-1]['vigencia_al_consultar'], 'abierta')

    def test_ups_literal_benefit_without_coverage_label_remains_pending(self):
        portal = PORTALES['ups']
        html = (b'<html><h4>Beca Distincion Academica</h4>'
                b'<p>Se otorgara el 30% de beneficio para asignaturas academicas.</p>'
                b'<p>Requisitos: promedio academico de 95/100.</p></html>')
        found = sections(html, portal)
        self.assertEqual(len(found), 1)
        item = extract_section({'url': portal.indice, 'consulta_utc': '2026-11-13T12:00:00Z',
                                'contenido': html}, portal, found[0])
        self.assertIn('30% de beneficio', item['beneficio']['texto_original'])
        self.assertEqual(item['tipo_oportunidad'], 'tipo_de_beca_vigencia_desconocida')
        self.assertIsNone(item['cierre']['fecha'])


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class PortalRunTests(TransactionTestCase):
    def setUp(self):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        self.actor = get_user_model().objects.create_user(email='portal-admin@example.com', nombre='Administrador prueba', rol='administrador')
        self.user = get_user_model().objects.create_user(email='portal-user@example.com', nombre='Postulante prueba')
        ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        Institucion.objects.create(nombre='Universidad ecuatoriana sintetica', sector='publico', pais=ec)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = override_settings(RASTREO_STORAGE_ROOT=self.temp.name)
        self.storage.enable()
        self.addCleanup(self.storage.disable)

    def source(self):
        source, changed = register_portal(self.actor.pk, 'utpl', 'Alta de fuente sintética')
        self.assertTrue(changed)
        self.assertFalse(source.activa)
        self.assertEqual(source.frecuencia_min, 720)
        return source

    def network(self, url):
        if url == UTPL.robots:
            return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /private/\n'
        if url == UTPL.indice:
            return 200, {'content-type': 'text/html'}, INDEX_HTML
        if url == FICHA:
            return 200, {'content-type': 'text/html'}, FICHA_HTML
        if url == PDF:
            return 200, {'content-type': 'application/pdf'}, b'%PDF-1.4\ncontenido sintetico'
        raise AssertionError('Red fuera de la lista simulada')

    def test_registration_permissions_audit_and_private_draft(self):
        with self.assertRaises(ValidationError):
            register_portal(self.user.pk, 'utpl', 'No autorizado')
        source = self.source()
        with patch('convocatorias.siau_red.Downloader.once') as network:
            omitted = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(omitted.estado, 'omitida')
        network.assert_not_called()
        source, changed = set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        self.assertTrue(changed)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(run.publicaciones_observadas, 1)
        publication = Publicacion.objects.get(fuente=source)
        self.assertEqual(publication.versiones.count(), 1)
        self.assertEqual(BorradorRastreo.objects.filter(publicacion=publication).count(), 1)
        self.assertEqual(publication.convocatoria.estado, 'borrador')
        # El llenado asigna la entidad cuando la ficha nombra a una existente (el oferente ya no queda siempre vacío).
        self.assertEqual(publication.convocatoria.institucion.nombre, 'Universidad ecuatoriana sintetica')
        self.assertFalse(publicas().filter(pk=publication.convocatoria_id).exists())
        self.assertEqual(Revision.objects.filter(fuente=source, dimension='configuracion').count(), 2)
        self.assertEqual(Incidencia.objects.filter(fuente=source, gravedad='error').count(), 0)
        self.assertEqual(run.accesos.filter(documento__isnull=False).count(), 4)
        self.assertIn(self.client.get('/api/gestion/rastreo/fuentes/').status_code, (401, 403))
        self.client.force_login(self.actor)
        response = self.client.get('/api/gestion/rastreo/fuentes/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['borradores'], 1)
        self.assertEqual(response.json()['results'][0]['ultima_ejecucion']['estado'], 'finalizada')
        # La frecuencia de una fuente no obliga a recapturarla.
        with patch('convocatorias.siau_red.Downloader.once') as network:
            same = run_scheduled(source.pk)
        self.assertEqual(same.pk, run.pk)
        network.assert_not_called()

    def test_one_fiche_error_does_not_erase_other_source(self):
        source = self.source()
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        def denied(url):
            if url == UTPL.robots:
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /tipos-de-becas/\n'
            return self.network(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=denied):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(run.estado, 'parcial')
        self.assertEqual(Publicacion.objects.filter(fuente=source).count(), 0)
        self.assertTrue(run.incidencias.filter(codigo='ROBOTS').exists())

    def test_ups_general_index_does_not_become_a_scholarship(self):
        source, _ = register_portal(self.actor.pk, 'ups', 'Alta sintética')
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        page = b'<html><h1>Becas UPS</h1><p>Estudiantes de la universidad.</p></html>'
        def network(url):
            return (200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /private/\n') if url == PORTALES['ups'].robots else (200, {'content-type': 'text/html'}, page)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(run.estado, 'parcial')
        self.assertEqual(Publicacion.objects.filter(fuente=source).count(), 0)
        self.assertTrue(run.incidencias.filter(codigo='INDICE_ESTRUCTURA').exists())
        self.assertEqual(BorradorRastreo.objects.count(), 0)
        self.assertEqual(Convocatoria.objects.count(), 0)

    def test_ups_detail_link_is_discovered_with_mocked_html(self):
        source, _ = register_portal(self.actor.pk, 'ups', 'Alta sintética')
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        portal = PORTALES['ups']
        detail = portal.indice + '/convocatoria-prueba'
        index = f'<html><a href="{detail}">Beca concreta</a></html>'.encode()
        page = (b'<html><h1>Beca para ciudadanos ecuatorianos</h1>'
                b'<p>Universidad ecuatoriana sintetica ofrece esta beca a ciudadanos ecuatorianos.</p>'
                b'<h2>Requisitos</h2><p>Ser estudiante regular y ciudadano ecuatoriano.</p>'
                b'<p>Cierre: 12 de noviembre de 2026</p></html>')
        def network(url):
            if url == portal.robots:
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /private/\n'
            return 200, {'content-type': 'text/html'}, index if url == portal.indice else page
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(run.estado, 'finalizada')
        publication = Publicacion.objects.get(fuente=source, url_normalizada=detail)
        self.assertEqual(publication.versiones.count(), 1)
        self.assertEqual(BorradorRastreo.objects.filter(publicacion=publication).count(), 1)
        self.assertFalse(publicas().filter(pk=publication.convocatoria_id).exists())

    def test_ups_three_sections_share_original_evidence_but_not_identity(self):
        source, _ = register_portal(self.actor.pk, 'ups', 'Alta sintética')
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        portal = PORTALES['ups']
        pdf = 'https://www.ups.edu.ec/documents/20121/beca.pdf/abc123?t=1656539176842'
        page = (f'<html><h4>Conoce las becas de grado</h4>'
                f'<h4><a href="{pdf}">Beca Equidad Social</a></h4>'
                '<p>La cobertura depende del quintil socioeconómico.</p>'
                '<h4>Beca Permanente</h4><p>Programa permanente. Requisitos por revisar.</p>'
                '<h4>Beca Mérito</h4><p>Universidad ecuatoriana sintetica ofrece esta beca a ciudadanos ecuatorianos.</p>'
                '<p>Requisitos: ser estudiante regular y ciudadano ecuatoriano.</p>'
                '<p>Beneficio: cobertura parcial.</p><p>Cierre: 12 de noviembre de 2026</p></html>').encode()
        def network(url):
            if url == portal.robots:
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow:\n'
            self.assertEqual(url, portal.indice)
            return 200, {'content-type': 'text/html'}, page
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as requested:
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(run.publicaciones_observadas, 3)
        self.assertEqual(Publicacion.objects.filter(fuente=source).count(), 3)
        self.assertEqual(Version.objects.filter(publicacion__fuente=source).count(), 3)
        # Cada una de las tres secciones conserva su propio borrador privado (creación parcial permitida).
        self.assertEqual(BorradorRastreo.objects.filter(publicacion__fuente=source).count(), 3)
        self.assertTrue(Incidencia.objects.filter(fuente=source, codigo='BASE_NO_PERMITIDA').exists())
        self.assertEqual([call.args[0] for call in requested.call_args_list], [portal.robots, portal.indice])
        for publication in Publicacion.objects.filter(fuente=source):
            self.assertEqual(publication.url_original, portal.indice)
            self.assertTrue(publication.url_normalizada.startswith(portal.indice + '#becanexo-'))
            relation = publication.versiones.get().documentos.get(rol='ficha_html')
            self.assertEqual(relation.url_normalizada, portal.indice)
            self.assertTrue(relation.localizador.startswith('becanexo-'))
        with patch('rastreo.services.next_due', return_value=None), patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            second = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        second.refresh_from_db()
        self.assertEqual(second.observaciones_sin_cambios, 3)
        self.assertEqual(Publicacion.objects.filter(fuente=source).count(), 3)
        self.assertEqual(Version.objects.filter(publicacion__fuente=source).count(), 3)

    def test_backoff_stops_only_portal_and_keeps_retry_evidence(self):
        source = self.source()
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        def network(url):
            if url == UTPL.indice:
                return 429, {'content-type': 'text/html', 'retry-after': '120'}, b''
            return self.network(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as requested:
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(run.estado, 'fallida')
        self.assertEqual([call.args[0] for call in requested.call_args_list], [UTPL.robots, UTPL.indice])
        self.assertTrue(run.incidencias.filter(codigo='REINTENTO_FUENTE').exists())
        self.assertEqual(Publicacion.objects.filter(fuente=source).count(), 0)

    def test_same_title_and_closure_from_another_portal_requires_review(self):
        first = self.source()
        set_portal_active(first.pk, self.actor.pk, 'Activación sintética', True)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.network):
            run_manual(first.pk, self.actor.pk, uuid.uuid4())
        second, _ = register_portal(self.actor.pk, 'ups', 'Alta sintética')
        set_portal_active(second.pk, self.actor.pk, 'Activación sintética', True)
        portal = PORTALES['ups']
        detail = portal.indice + '/beca-sintetica'
        def network(url):
            if url == portal.robots:
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /private/\n'
            if url == portal.indice:
                return 200, {'content-type': 'text/html'}, f'<html><a href="{detail}">Beca</a></html>'.encode()
            return 200, {'content-type': 'text/html'}, FICHA_HTML
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run_manual(second.pk, self.actor.pk, uuid.uuid4())
        # Desde que se relajó la creación de borradores, el duplicado de otro portal también conserva su borrador privado
        # (con la incidencia de revisión), en lugar de quedar sin borrador.
        self.assertEqual(Publicacion.objects.count(), 2)
        self.assertEqual(BorradorRastreo.objects.count(), 2)
        self.assertTrue(Incidencia.objects.filter(fuente=second, codigo='BORRADOR_REVISION_PENDIENTE').exists())
