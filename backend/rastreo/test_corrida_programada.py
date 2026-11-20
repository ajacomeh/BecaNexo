"""Corrida programada de SIAU con una fuente simulada, en la base aislada: ciclo completo y garantías de seguridad.

Todo el HTTP es simulado (no hay red). La tarea de Windows ejecuta `rastreo estado-programacion` y `rastreo programado`
sobre la fuente 1; estas pruebas ejercitan ese mismo comando.
"""
import io
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from convocatorias.models import BorradorRastreo, Convocatoria, Evento, Institucion
from convocatorias.services import publicas
from convocatorias.siau_red import INDEX, NATIONAL_INDEX, PDFS, ROBOTS
from notificaciones.models import EntregaCorreo, Notificacion
from perfiles.models import Pais
from . import tests as base
from .descubrimiento import MAX_FICHAS
from .models import Ejecucion, Publicacion
from .services import (enable_discovery, enable_national_discovery, exclusion, resumen_corrida, run_scheduled, set_frequency, snapshot)
from .test_evidencia_pdf import pdf_pages
from .test_periodico import NATIONAL_PAGE, national_ficha
from .web_frequency import source_blocked

BASES_PDF = pdf_pages([
    'A. OBJETIVO',
    'El programa, impulsado por el Ministerio de Educacion, Deporte y Cultura, concede becas a personas naturales.',
    'D. REQUISITOS PARA LA POSTULACION',
    '1. Persona natural en goce de derechos de participacion ciudadana en el Ecuador.',
    'I. OBLIGACIONES DE LA PERSONA BECARIA:',
    '1. Destinar los recursos al objeto de la beca recibida.',
    '2. Aprobar el programa de estudios en los plazos del contrato.',
])


def tarjetas(*paginas):
    cuerpo = ''.join(f'<article class="category-convocatorias pais-ecuador"><h2 class="entry-title"><a href="{url}">Oferta de Becas Nacionales {n}</a></h2></article>'
                     for n, url in enumerate(paginas, start=1))
    return (cuerpo + '<div onclick="{&quot;max_num_pages&quot;:1}"></div>').encode()


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class CorridaProgramadaTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake

    def preparar(self, frecuencia=1440):
        self.ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        self.minedec = Institucion.objects.create(nombre='Ministerio de Educación, Deporte y Cultura del Ecuador (MINEDEC)', sector='publico', pais=self.ec)
        fuente = self.source()
        enable_discovery(self.actor.pk, 'Índice de prueba')
        enable_national_discovery(self.actor.pk, 'Índice nacional de prueba')
        self.fuente, _ = set_frequency(fuente.pk, self.actor.pk, 'Ventana de 24 horas de la corrida programada', frecuencia)
        return self.fuente

    def red(self, paginas=(NATIONAL_PAGE,), robots=None, fallar=None, estado_indice=None):
        """Servidor simulado: devuelve (función de red, lista de URL pedidas)."""
        pedidas = []

        def red(url):
            pedidas.append(url)
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, (robots or 'User-agent: *\nDisallow: /wp-admin/\n').encode()
            if estado_indice and url == INDEX:
                return estado_indice
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, tarjetas(*paginas)
            if url in paginas:
                if fallar and url == fallar:
                    raise RuntimeError('fallo simulado a mitad de la corrida')
                return 200, {'content-type': 'text/html'}, national_ficha()
            if url in PDFS:
                return 200, {'content-type': 'application/pdf'}, BASES_PDF
            return self.fake(url)
        return red, pedidas

    def programado(self):
        salida = io.StringIO()
        call_command('rastreo', 'programado', fuente_id=self.fuente.pk, stdout=salida)
        return json.loads(salida.getvalue())[0]

    def anterior(self, minutos, estado='finalizada', origen='programada', **extra):
        """Ejecución previa creada con su edad desde el inicio (las finalizadas son inmutables en la base)."""
        inicio = timezone.now() - timedelta(minutes=minutos)
        return Ejecucion.objects.create(
            fuente=self.fuente, origen=origen, clave_idempotencia=uuid.uuid4(), inicio=inicio,
            fin=None if estado == 'en_curso' else inicio, estado=estado, configuracion_snapshot=snapshot(self.fuente.pk),
            version_extractor='siau-html/2', solicitado_por=self.actor if origen == 'manual' else None, **extra)

    def correr(self):
        corrida = run_scheduled(self.fuente.pk)
        corrida.refresh_from_db()
        return corrida

    # 2. Ciclo completo de una corrida programada.
    def test_corrida_programada_completa_crea_borrador_con_bases_y_no_publica_ni_notifica(self):
        self.preparar()
        red, pedidas = self.red()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
            resultado = self.programado()
            segunda = self.programado()
        # Resultado legible: fecha, peticiones, candidatos nuevos y borradores creados.
        self.assertEqual(resultado['estado'], 'finalizada')
        resumen = resultado['resumen']
        nuevas = Publicacion.objects.count()   # en la fuente simulada también son nuevas las fichas conocidas
        self.assertEqual((resumen['peticiones'], resumen['candidatos_nuevos'], resumen['borradores_creados']), (len(pedidas), nuevas, 1))
        self.assertIn(f'{nuevas} candidatos nuevos', resumen['texto'])
        self.assertIn('1 borrador creado', resumen['texto'])
        self.assertIn('(Ecuador)', resumen['texto'])
        # Captura y detección: la ficha nacional quedó como publicación con su versión y su PDF de bases.
        publicacion = Publicacion.objects.get(url_normalizada=NATIONAL_PAGE)
        version = publicacion.versiones.get()
        self.assertTrue(version.documentos.filter(rol='ficha_html').exists())
        self.assertTrue(version.documentos.filter(rol='bases_pdf').exists())
        ejecucion = Ejecucion.objects.get(pk=resultado['id'])
        self.assertEqual((ejecucion.origen, ejecucion.solicitado_por_id), ('programada', None))
        # Borrador privado con su llenado, que ya lee las bases en PDF: entidad y obligaciones con su procedencia.
        origen = BorradorRastreo.objects.get(publicacion=publicacion)
        oferta = origen.convocatoria
        libro = origen.datos_iniciales['llenado_automatico']
        self.assertIsNone(libro.get('error'))
        self.assertEqual(oferta.institucion_id, self.minedec.pk)
        entidad = next(c for c in libro['campos'] if c['campo'] == 'institucion')
        self.assertTrue(entidad['seccion'].startswith('Bases en PDF'))
        self.assertIn('Destinar los recursos', oferta.obligaciones_beneficiario)
        self.assertTrue(oferta.requisitos.exists())
        self.assertFalse(oferta.requisitos.filter(validado=True).exists())
        # No publica, no crea notificaciones ni envía correos.
        self.assertEqual((oferta.revision, publicas().filter(pk=oferta.pk).exists()), ('pendiente', False))
        self.assertEqual((Notificacion.objects.count(), EntregaCorreo.objects.count(), len(mail.outbox)), (0, 0, 0))
        self.assertEqual(Evento.objects.filter(accion__in=('publicar', 'confirmar_publicacion')).count(), 0)
        # La segunda invocación, en la misma ventana, no hace peticiones.
        self.assertEqual(segunda['estado'], 'no_corresponde_aun')
        self.assertEqual(len(pedidas), resumen['peticiones'])

    # 3a. Ventana de 24 horas.
    def test_una_corrida_anticipada_a_las_24_horas_no_hace_peticiones(self):
        self.preparar()
        red, pedidas = self.red()
        self.anterior(24 * 60 - 1)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
            self.assertEqual(self.programado()['estado'], 'no_corresponde_aun')
            self.assertEqual(self.correr().origen, 'programada')
        self.assertEqual(pedidas, [])
        self.assertEqual(Ejecucion.objects.count(), 1, 'ni siquiera crea una ejecución nueva')

    def test_cumplidas_las_24_horas_la_corrida_si_se_ejecuta(self):
        self.preparar()
        red, pedidas = self.red()
        self.anterior(24 * 60 + 1)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
            self.assertEqual(self.programado()['estado'], 'finalizada')
        self.assertGreater(len(pedidas), 0)

    def test_una_captura_manual_de_un_candidato_consume_la_misma_ventana(self):
        self.preparar()
        self.anterior(60, origen='manual')
        red, pedidas = self.red()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
            self.assertEqual(self.programado()['estado'], 'no_corresponde_aun')
        self.assertEqual(pedidas, [])

    # 3b. Candado: dos corridas simultáneas.
    def test_con_otra_corrida_en_curso_la_programada_se_omite_sin_red(self):
        self.preparar()
        red, pedidas = self.red()
        self.anterior(25 * 60, estado='en_curso', latido_en=timezone.now())
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
            omitida = self.correr()
        self.assertEqual((omitida.estado, pedidas), ('omitida', []))
        self.assertIn('pendiente de recuperación', omitida.error_resumen)

    def test_con_el_candado_de_la_fuente_tomado_otra_conexion_se_omite_sin_red(self):
        from concurrent.futures import ThreadPoolExecutor
        from django.db import connection, connections
        self.preparar()
        red, pedidas = self.red()

        def competidora():
            connections.close_all()
            try:
                with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
                    return run_scheduled(self.fuente.pk).pk
            finally:
                connections.close_all()
        with exclusion(self.fuente.pk) as propio:
            self.assertTrue(propio)
            with ThreadPoolExecutor(max_workers=1) as pool:
                identificador = pool.submit(competidora).result(timeout=20)
        omitida = Ejecucion.objects.get(pk=identificador)
        self.assertEqual((omitida.estado, omitida.origen, pedidas), ('omitida', 'programada', []))
        self.assertFalse(omitida.accesos.exists())

    # 3c. 429 / 503: bloqueo sin reintentos en bucle.
    def test_ante_429_la_fuente_queda_bloqueada_la_corrida_termina_sin_reintentar_y_la_siguiente_se_omite(self):
        self.preparar()
        red, pedidas = self.red(estado_indice=(429, {'retry-after': '172800', 'content-type': 'text/plain'}, b''))
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
            primera = self.correr()
            self.assertEqual(pedidas, [ROBOTS, INDEX], 'robots.txt y un solo intento al índice; sin reintentos')
            self.assertEqual(primera.accesos.count(), 2)
            self.assertEqual((primera.estado, primera.error_resumen), ('fallida', 'SourceBackoff'))
            self.assertTrue(source_blocked(self.fuente))
            # Pasadas 25 horas (ventana cumplida) y con el bloqueo vigente (48 h), la corrida no pide nada.
            with patch('django.utils.timezone.now', return_value=timezone.now() + timedelta(hours=25)):
                siguiente = self.correr()
        self.assertEqual(len(pedidas), 2, 'ninguna petición adicional')
        self.assertIn(siguiente.estado, ('omitida', 'fallida'))
        self.assertEqual(Publicacion.objects.filter(url_normalizada=NATIONAL_PAGE).count(), 0)

    def test_ante_503_sin_retry_after_la_corrida_se_detiene_en_la_primera_respuesta(self):
        self.preparar()
        red, pedidas = self.red(estado_indice=(503, {'content-type': 'text/plain'}, b''))
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
            corrida = self.correr()
        self.assertEqual((corrida.estado, pedidas), ('fallida', [ROBOTS, INDEX]))
        self.assertTrue(source_blocked(self.fuente))

    # 3d. robots.txt y límites de peticiones.
    def test_robots_bloquea_la_ficha_sin_pedirla_y_los_limites_acotan_las_fichas(self):
        self.preparar()
        robots = 'User-agent: *\nDisallow: /oferta-de-becas-nacionales-educacion-continua-prueba/\n'
        red, pedidas = self.red(robots=robots)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
            corrida = self.correr()
        self.assertNotIn(NATIONAL_PAGE, pedidas, 'una ruta que robots.txt prohíbe no se solicita')
        self.assertTrue(corrida.incidencias.filter(codigo='ROBOTS').exists())
        self.assertFalse(Publicacion.objects.filter(url_normalizada=NATIONAL_PAGE).exists())

    def test_un_indice_con_mas_fichas_que_el_limite_pide_solo_el_maximo(self):
        self.preparar()
        muchas = tuple(f'https://siau.senescyt.gob.ec/oferta-de-becas-nacionales-prueba-{n}/' for n in range(MAX_FICHAS + 6))
        red, pedidas = self.red(paginas=muchas)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
            corrida = self.correr()
        fichas = [url for url in pedidas if url in muchas]
        self.assertLessEqual(len(fichas), MAX_FICHAS)
        self.assertTrue(corrida.incidencias.filter(codigo='INDICE_LIMITE').exists())
        self.assertLess(len(pedidas), 2 + MAX_FICHAS + 30)

    # 3e. Fallo a mitad de la corrida.
    def test_un_fallo_a_mitad_no_deja_datos_a_medias_y_libera_el_candado(self):
        self.preparar()
        segunda = 'https://siau.senescyt.gob.ec/oferta-de-becas-nacionales-prueba-2/'
        red, pedidas = self.red(paginas=(NATIONAL_PAGE, segunda), fallar=segunda)
        from convocatorias.siau_extraccion import extract_html as original

        def extraer(page):
            if page['url'] == segunda:
                raise RuntimeError('fallo simulado a mitad de la corrida')
            return original(page)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red), patch('rastreo.services.extract_html', side_effect=extraer):
            corrida = self.correr()
        self.assertEqual((corrida.estado, corrida.error_resumen), ('fallida', 'RuntimeError'))
        self.assertIsNotNone(corrida.fin)
        # La ficha completa anterior conserva su versión, sus documentos y su borrador; la que falló no deja nada.
        completa = Publicacion.objects.get(url_normalizada=NATIONAL_PAGE)
        self.assertTrue(completa.versiones.get().documentos.filter(rol='ficha_html').exists())
        self.assertTrue(BorradorRastreo.objects.filter(publicacion=completa).exists())
        fallida = Publicacion.objects.filter(url_normalizada=segunda).first()
        self.assertTrue(fallida is None or not fallida.versiones.exists())
        self.assertFalse(fallida is not None and fallida.convocatoria_id)
        self.assertEqual(Convocatoria.objects.filter(origen_automatico__isnull=False).count(), 1)
        self.assertFalse(Ejecucion.objects.filter(estado='en_curso').exists())
        with exclusion(self.fuente.pk) as obtenido:
            self.assertTrue(obtenido, 'el candado queda libre tras el fallo')

    def test_una_corrida_programada_interrumpida_se_cierra_sola_y_libera_la_fuente(self):
        self.preparar()
        muerta = self.anterior(3 * 60, estado='en_curso')
        resultado = self.programado()
        self.assertEqual(resultado['estado'], 'no_corresponde_aun')
        self.assertEqual(resultado['interrumpidas_cerradas'], [muerta.pk])
        muerta.refresh_from_db()
        self.assertEqual((muerta.estado, muerta.error_resumen), ('fallida', 'Interrumpida; exclusión comprobada.'))
        self.assertIsNotNone(muerta.fin)
        self.assertTrue(muerta.incidencias.filter(codigo='INTERRUMPIDA').exists())
        self.assertFalse(Ejecucion.objects.filter(estado='en_curso').exists())
        # La corrida interrumpida sigue consumiendo la ventana de 24 horas.
        self.assertEqual(self.programado()['estado'], 'no_corresponde_aun')

    def test_no_cierra_una_programada_con_latido_reciente_ni_una_manual(self):
        self.preparar()
        reciente = self.anterior(2, estado='en_curso', latido_en=timezone.now())
        self.assertEqual(self.programado()['interrumpidas_cerradas'], [])
        reciente.refresh_from_db()
        self.assertEqual(reciente.estado, 'en_curso')
        Ejecucion.objects.filter(pk=reciente.pk).update(estado='fallida', fin=timezone.now())
        manual = self.anterior(5 * 60, estado='en_curso', origen='manual')
        self.assertEqual(self.programado()['interrumpidas_cerradas'], [])
        manual.refresh_from_db()
        self.assertEqual(manual.estado, 'en_curso')   # las manuales exigen la recuperación explícita y auditada

    # 3f / 3g. Registro legible y pantalla de Rastreo.
    def test_el_resumen_es_legible_tambien_para_las_corridas_omitidas_y_el_panel_muestra_la_ultima_programada(self):
        self.preparar()
        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        self.assertIsNone(admin.get('/api/gestion/rastreo/control/').data['ultima_programada'])
        red, pedidas = self.red()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
            corrida = self.correr()
        panel = admin.get('/api/gestion/rastreo/control/').data['ultima_programada']
        self.assertEqual((panel['ejecucion_id'], panel['estado'], panel['origen']), (corrida.pk, 'finalizada', 'programada'))
        self.assertEqual((panel['peticiones'], panel['candidatos_nuevos'], panel['borradores_creados']), (len(pedidas), Publicacion.objects.count(), 1))
        self.assertIn('finalizada', panel['texto'])
        # Una corrida posterior omitida (hay una manual en curso que exige recuperación explícita) queda a la vista, con su motivo.
        self.anterior(5, estado='en_curso', origen='manual')
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red),                 patch('django.utils.timezone.now', return_value=timezone.now() + timedelta(hours=25)):
            omitida = Ejecucion.objects.get(pk=run_scheduled(self.fuente.pk).pk)
        panel = admin.get('/api/gestion/rastreo/control/').data['ultima_programada']
        self.assertEqual((panel['ejecucion_id'], panel['estado']), (omitida.pk, 'omitida'))
        self.assertIn('motivo:', resumen_corrida(omitida)['texto'])
        self.assertTrue(panel['motivo'])

    # 4. Cómo detectar que se saltó una corrida.
    def revisar(self):
        salida = io.StringIO()
        call_command('rastreo', 'corridas-programadas', fuente_id=self.fuente.pk, stdout=salida)
        return json.loads(salida.getvalue())

    def test_el_comando_de_revision_no_marca_atraso_sin_capturas_ni_dentro_del_margen(self):
        self.preparar()
        vacio = self.revisar()
        self.assertEqual((vacio['atrasada'], vacio['ultima_captura'], vacio['corridas_programadas']), (False, None, []))
        # Última captura hace 25 horas: la ventana se cumplió hace 1 h, todavía dentro del margen de 2 h.
        self.anterior(25 * 60)
        self.assertFalse(self.revisar()['atrasada'])

    def test_el_comando_de_revision_detecta_una_captura_saltada_y_lista_las_ultimas_corridas(self):
        self.preparar()
        self.anterior(27 * 60 + 1)
        informe = self.revisar()
        self.assertTrue(informe['atrasada'])
        self.assertGreaterEqual(informe['horas_de_atraso'], 3)
        self.assertEqual(informe['ultima_captura']['origen'], 'programada')
        self.assertEqual(informe['corridas_programadas'][0]['origen'], 'programada')
        self.assertIn('finalizada', informe['corridas_programadas'][0]['texto'])
