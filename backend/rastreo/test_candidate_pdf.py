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
                    pdf_url=PDF_URL, robots=transition.ROBOTS_TEXT, links=1, html=None, key=None):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        html = (html or transition.fiche()).replace(
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
            execution = run_candidate(self.candidate.pk, self.actor.pk, key or uuid.uuid4(),
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

    @override_settings(AVISOS_CORREO_HABILITADOS=True,
                       EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                       BECANEXO_PUBLIC_BASE_URL='http://127.0.0.1:5173')
    def test_flujo_integral_sintetico_hasta_aviso_y_smtp_simulado(self):
        from datetime import date
        from django.contrib.auth import get_user_model
        from django.core import mail
        from django.core.management import call_command
        from rest_framework.test import APIClient
        from convocatorias.models import Evento, Institucion, OpcionEstudio, Requisito, TipoRequisito
        from convocatorias.comparacion import evaluar_convocatoria
        from convocatorias.reglas import CONTRATOS
        from perfiles.models import Pais, Perfil, Preferencia
        from notificaciones.models import EntregaCorreo, Notificacion, PreferenciaCorreo
        from notificaciones.correo import procesar_pendientes
        from .auto_borradores import editable_candidates

        call_command('cargar_catalogos_convocatorias', verbosity=0)
        html = transition.fiche(deadline_text='20 de noviembre de 2030').replace(
            b'</ol>', b'<li>Edad maxima de 25 anos al 1 de enero de 2026.</li></ol>')
        pdf = pdf_pages(['Programa sintetico de becas nacionales', 'Requisitos generales',
                         'Edad maxima de 25 anos al 1 de enero de 2026',
                         'Cierre 20 de noviembre de 2030'])
        key = uuid.uuid4()
        run, calls = self.execute_pdf(html=html, pdf_bytes=pdf, key=key)
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(calls, [ROBOTS, transition.URL, PDF_URL])
        publication = Publicacion.objects.get(fuente=self.source, url_normalizada=self.candidate.url_normalizada)
        origin = BorradorRastreo.objects.get(publicacion=publication)
        offer = origin.convocatoria
        # El llenado asigna la entidad cuando la ficha nombra a una existente (el oferente ya no queda siempre vacío).
        self.assertEqual((offer.revision, offer.institucion.nombre), ('pendiente', 'Universidad Ecuatoriana Demo'))
        self.assertEqual(origin.version.documentos.filter(rol='ficha_html').count(), 1)
        self.assertEqual(origin.version.documentos.filter(rol='bases_pdf').count(), 1)
        self.assertTrue(editable_candidates(origin.version)['otros_campos']['propuestas_documentales'])
        self.assertEqual(APIClient().get(f'/api/becas/{offer.pk}/').status_code, 404)

        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        token = admin.get('/api/auth/csrf/').data['csrfToken']
        evidence = admin.get(f'/api/gestion/rastreo/convocatorias/{offer.pk}/origen/')
        self.assertEqual(evidence.status_code, 200)
        # El origen ya no devuelve los candidatos editables (el llenado escribe los campos); entrega la evidencia visible.
        # Las propuestas documentales se siguen comprobando arriba con editable_candidates.
        self.assertTrue(evidence.data['automatico'])
        self.assertEqual(set(evidence.data['evidencia']), {'campos', 'registros'})
        self.assertEqual(admin.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {},
                                    format='json', HTTP_X_CSRFTOKEN=token).status_code, 400)

        institution = Institucion.objects.get(nombre='Universidad Ecuatoriana Demo')
        edited = admin.patch(f'/api/gestion/convocatorias/{offer.pk}/',
                             {'institucion': institution.pk, 'url_oficial': transition.URL},
                             format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(edited.status_code, 200, edited.data)
        ec = Pais.objects.get(codigo='EC')
        option = OpcionEstudio.objects.create(convocatoria=offer, nivel='grado', modalidad='virtual')
        option.paises.add(ec)
        Requisito.objects.create(convocatoria=offer, tipo_requisito=TipoRequisito.objects.get(codigo='EDAD'),
            texto_original='Edad maxima de 25 anos al 1 de enero de 2026',
            valor_estructurado={'maximo': 25}, operador=CONTRATOS['EDAD'][1],
            fecha_referencia=date(2026, 1, 1), modo_comprobacion='dato_declarado',
            obligatorio=True, validado=True)

        users = get_user_model().objects
        eligible = users.create_user(email='elegible-demo@example.test', nombre='Perfil elegible', password=None)
        ineligible = users.create_user(email='no-elegible-demo@example.test', nombre='Perfil no elegible', password=None)
        for user, birth in ((eligible, date(2005, 1, 1)), (ineligible, date(1980, 1, 1))):
            profile = Perfil.objects.create(usuario=user, nacionalidad=ec, fecha_nacimiento=birth,
                                            descripcion='Interes en estudios de grado y apoyo academico')
            Preferencia.objects.create(perfil=profile, nivel='grado', modalidad='virtual')
            PreferenciaCorreo.objects.create(usuario=user, habilitada=True)

        # El llenado deja sus requisitos sin validar y la comparación solo cuenta los validados; la revisión del
        # administrador (o «Validar y publicar») los valida antes de comparar.
        offer.requisitos.filter(activo=True).update(validado=True)
        eligible_result = evaluar_convocatoria(eligible, offer)['opciones'][0]['resultado']
        ineligible_result = evaluar_convocatoria(ineligible, offer)['opciones'][0]['resultado']
        self.assertEqual((eligible_result, ineligible_result), ('cumple', 'no_cumple'))
        published = admin.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {},
                               format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(published.status_code, 200, published.data)
        offer.refresh_from_db()
        self.assertEqual(offer.revision, 'validada')
        self.assertEqual(APIClient().get(f'/api/becas/{offer.pk}/').status_code, 200)
        recommendation_states = []
        for user, expected in ((eligible, 'cumple'), (ineligible, 'no_cumple')):
            client = APIClient()
            client.force_login(user)
            response = client.get('/api/becas/recomendaciones/')
            self.assertEqual(response.status_code, 200)
            recommended = next(row for row in response.data['results'] if row['convocatoria']['id'] == offer.pk)
            self.assertEqual(recommended['elegibilidad'], expected)
            recommendation_states.append(recommended['afinidad']['estado'])
        self.assertTrue(Evento.objects.filter(convocatoria=offer, actor=self.actor, accion='publicar').exists())
        self.assertEqual(list(Notificacion.objects.values_list('usuario_id', flat=True)), [eligible.pk])
        self.assertEqual(EntregaCorreo.objects.count(), 1)
        self.assertEqual(EntregaCorreo.objects.get().notificacion.usuario_id, eligible.pk)
        self.assertEqual(procesar_pendientes(limite=1)['enviados'], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [eligible.email])
        self.assertIn(f'/becas/{offer.pk}', mail.outbox[0].body)
        self.assertEqual(procesar_pendientes(limite=1)['enviados'], 0)

        repeated = run_candidate(self.candidate.pk, self.actor.pk, key, 'Ensayo de PDF individual sintético')
        self.assertEqual(repeated.pk, run.pk)
        self.assertEqual(Publicacion.objects.count(), 1)
        self.assertEqual(BorradorRastreo.objects.count(), 1)
        self.assertEqual((Notificacion.objects.count(), EntregaCorreo.objects.count()), (1, 1))
        print({'ejecucion': run.pk, 'publicacion': publication.pk, 'version': origin.version_id,
               'borrador': offer.pk, 'publicado': offer.revision, 'compatibilidad': [eligible_result, ineligible_result],
               'afinidad': recommendation_states, 'avisos': Notificacion.objects.count(),
               'correos_simulados': len(mail.outbox)})

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
