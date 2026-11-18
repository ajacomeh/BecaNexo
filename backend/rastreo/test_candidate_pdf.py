"""PDF individual con HTTP simulado y escrituras exclusivas en base aislada."""
import uuid
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase, override_settings

from convocatorias.models import BorradorRastreo
from convocatorias.siau_red import ROBOTS

from . import test_candidate_transition as transition
from .auto_borradores import editable_candidates
from .models import Ejecucion, Publicacion
from .services import run_candidate
from .test_evidencia_pdf import pdf_pages


PDF_URL = 'https://siau.senescyt.gob.ec/wp-content/uploads/2026/11/bases-demo.pdf'
PDF = pdf_pages(['Programa de becas', 'Requisitos generales', 'Ser ciudadano ecuatoriano',
                 'Cobertura del 75% al 100% segun evaluacion'])


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True,
                   RASTREO_CANDIDATO_PDF_HABILITADO=True)
class CandidatePDFTests(TransactionTestCase):
    setUpBase = transition.CandidateTransitionTests.setUpBase
    source = transition.CandidateTransitionTests.source
    setUp = transition.CandidateTransitionTests.setUp

    def execute_pdf(self, *, pdf_status=200, pdf_type='application/pdf', pdf_bytes=PDF,
                    pdf_url=PDF_URL, robots=transition.ROBOTS_TEXT, links=1):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_fusion_db')
        html = transition.fiche().replace(
            b'</section>', (f'<a href="{pdf_url}">BASES</a>'.encode() * links) + b'</section>')
        calls = []

        def network(url):
            calls.append(url)
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, robots
            if url == transition.URL:
                return 200, {'content-type': 'text/html'}, html
            self.assertEqual(url, pdf_url)
            return pdf_status, {'content-type': pdf_type}, pdf_bytes

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            execution = run_candidate(self.candidate.pk, self.actor.pk, uuid.uuid4(),
                                      'Ensayo de PDF individual sintético')
        execution.refresh_from_db()
        return execution, calls

    def test_un_pdf_admitido_conserva_huella_version_y_propuestas_privadas(self):
        run, calls = self.execute_pdf(links=2)
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(calls, [ROBOTS, transition.URL, PDF_URL])
        publication = Publicacion.objects.get(fuente=self.source)
        origin = BorradorRastreo.objects.get(publicacion=publication)
        self.assertEqual(origin.convocatoria.estado, 'borrador')
        self.assertEqual(origin.version.documentos.filter(rol='bases_pdf').count(), 1)
        pdf = origin.version.documentos.get(rol='bases_pdf')
        self.assertEqual(pdf.url_normalizada, PDF_URL)
        self.assertEqual(pdf.documento.tamano_bytes, len(PDF))
        self.assertEqual(run.accesos.filter(rol='bases', documento=pdf.documento).count(), 1)
        editorial = editable_candidates(origin.version)['otros_campos']
        self.assertEqual(editorial['evidencia_pdf']['documentos'][0]['estado'], 'extraido')
        self.assertTrue(any(row['procedencia'].get('pagina') == 1 for row in editorial['propuestas_documentales']))
        self.assertFalse(origin.convocatoria.requisitos.exists())
        self.assertFalse(origin.convocatoria.beneficios.exists())

    @override_settings(RASTREO_CANDIDATO_PDF_HABILITADO=False)
    def test_configuracion_predeterminada_deja_pdf_pendiente(self):
        run, calls = self.execute_pdf()
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(calls, [ROBOTS, transition.URL])
        version = Publicacion.objects.get(fuente=self.source).versiones.get()
        self.assertEqual(version.documentos.filter(rol='bases_pdf').count(), 0)
        self.assertEqual(version.manifiesto['pendientes'][0]['estado'], 'base_no_descargada')

    def test_destino_privado_no_se_consulta(self):
        run, calls = self.execute_pdf(pdf_url='https://127.0.0.1/bases.pdf')
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(calls, [ROBOTS, transition.URL])
        version = Publicacion.objects.get(fuente=self.source).versiones.get()
        self.assertEqual(version.manifiesto['pendientes'][0]['estado'], 'fuera_de_lista')
        self.assertFalse(version.documentos.filter(rol='bases_pdf').exists())

    def test_dos_bases_validas_quedan_pendientes_sin_elegir_una(self):
        second_url = PDF_URL.replace('bases-demo.pdf', 'anexo-demo.pdf')
        html = transition.fiche().replace(b'</section>',
            f'<a href="{PDF_URL}">BASES</a><a href="{second_url}">BASES</a></section>'.encode())
        calls = []

        def network(url):
            calls.append(url)
            return ((200, {'content-type': 'text/plain'}, transition.ROBOTS_TEXT) if url == ROBOTS
                    else (200, {'content-type': 'text/html'}, html))

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_candidate(self.candidate.pk, self.actor.pk, uuid.uuid4(), 'Dos bases sintéticas')
        run.refresh_from_db()
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(calls, [ROBOTS, transition.URL])
        version = Publicacion.objects.get(fuente=self.source).versiones.get()
        self.assertEqual(len(version.manifiesto['pendientes']), 2)
        self.assertTrue(all(row['estado'] == 'seleccion_pendiente' for row in version.manifiesto['pendientes']))

    def test_exceso_de_enlaces_no_descarga_pdf(self):
        links = ''.join(
            f'<a href="{PDF_URL.replace("bases-demo.pdf", f"bases-{number}.pdf")}">BASES</a>'
            for number in range(9)
        )
        html = transition.fiche().replace(b'</section>', links.encode() + b'</section>')
        calls = []

        def network(url):
            calls.append(url)
            return ((200, {'content-type': 'text/plain'}, transition.ROBOTS_TEXT) if url == ROBOTS
                    else (200, {'content-type': 'text/html'}, html))

        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_candidate(self.candidate.pk, self.actor.pk, uuid.uuid4(), 'Exceso de bases sintéticas')
        run.refresh_from_db()
        self.assertEqual(calls, [ROBOTS, transition.URL])
        self.assertEqual(run.estado, 'finalizada')
        self.assertTrue(run.incidencias.filter(codigo='BASES_LIMITE').exists())
        version = Publicacion.objects.get(fuente=self.source).versiones.get()
        self.assertEqual(len(version.manifiesto['pendientes']), 8)
        self.assertFalse(version.documentos.filter(rol='bases_pdf').exists())

    def test_pdf_invalido_conserva_html_y_revision(self):
        run, calls = self.execute_pdf(pdf_bytes=b'contenido que no es pdf')
        self.assertEqual(run.estado, 'parcial')
        self.assertEqual(calls, [ROBOTS, transition.URL, PDF_URL])
        origin = BorradorRastreo.objects.get()
        self.assertTrue(origin.version.documentos.filter(rol='ficha_html').exists())
        self.assertFalse(origin.version.documentos.filter(rol='bases_pdf').exists())
        self.assertEqual(origin.version.manifiesto['pendientes'][0]['estado'], 'inaccesible')

    def test_robots_impide_pdf_y_conserva_html(self):
        robots = b'User-agent: *\nDisallow: /wp-content/uploads/\nDisallow: /wp-admin/\n'
        run, calls = self.execute_pdf(robots=robots)
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(calls, [ROBOTS, transition.URL])
        origin = BorradorRastreo.objects.get()
        self.assertEqual(origin.version.manifiesto['pendientes'][0]['estado'], 'inaccesible')
        self.assertFalse(origin.version.documentos.filter(rol='bases_pdf').exists())

    def test_http_503_detiene_y_no_fabrica_version(self):
        run, calls = self.execute_pdf(pdf_status=503)
        self.assertEqual(run.estado, 'fallida')
        self.assertEqual(calls, [ROBOTS, transition.URL, PDF_URL])
        self.assertFalse(BorradorRastreo.objects.exists())
        self.assertFalse(Publicacion.objects.get(fuente=self.source).versiones.exists())
        self.assertTrue(run.accesos.filter(http_status=503).exists())
        self.assertFalse(Ejecucion.objects.filter(fuente=self.source, estado='en_curso').exists())
