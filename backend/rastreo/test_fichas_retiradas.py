"""Fichas conocidas que SIAU retira (404/410): aviso FICHA_NO_DISPONIBLE, marca tras dos ejecuciones y selección.

HTTP simulado; escribe solo en la base de pruebas aislada.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from convocatorias.siau_red import NATIONAL_INDEX
from . import tests as base
from . import test_ajax_pagination as ajax
from .models import Publicacion
from .services import run_manual, seleccionar_fichas, set_paginated_discovery
from .test_ajax_pagination import PAGE, card, index
from .test_periodico import national_ficha
from . import test_candidate_transition as transicion
from .test_candidate_transition import URL, fiche

SIAU = 'https://siau.senescyt.gob.ec'
VIGENTE = SIAU + '/oferta-de-becas-nacionales-vigente/'
RETIRADA = SIAU + '/oferta-de-becas-nacionales-retirada/'


class FichasRetiradasTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    configured = ajax.AjaxPaginationTests.configured
    network = ajax.AjaxPaginationTests.network

    def fuente(self):
        self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)
        ahora = timezone.now()
        for n, url in enumerate((RETIRADA, VIGENTE)):
            Publicacion.objects.create(fuente=source, url_original=url, url_normalizada=url, normalizacion_version='urls-cerradas/1',
                                       primera_deteccion=ahora - timedelta(days=10 - n), ultima_deteccion=ahora - timedelta(days=10 - n))
        return source

    def correr(self, source, estado, en_indice=()):
        indice = index(max_pages=1) + b''.join(card(url) for url in en_indice)

        def red(url):
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, indice
            if url == RETIRADA:
                return estado, {'content-type': 'text/html'}, b'' if estado != 200 else national_ficha()
            if url in (VIGENTE, PAGE):
                return 200, {'content-type': 'text/html'}, national_ficha()
            return self.network(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red) as llamadas, patch('convocatorias.siau_red.Downloader.post_once'):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        return run, [c.args[0] for c in llamadas.call_args_list]

    def retirada(self):
        return Publicacion.objects.get(url_normalizada=RETIRADA)

    @base.ventana_cumplida()
    def test_un_404_solo_avisa_sin_marcar_ni_dejar_parcial(self):
        source = self.fuente()
        run, _ = self.correr(source, 404)
        aviso = run.incidencias.get(codigo='FICHA_NO_DISPONIBLE')
        self.assertEqual((aviso.gravedad, aviso.publicacion_id), ('aviso', self.retirada().pk))
        self.assertIn('se confirmará si se repite', aviso.detalle)
        self.assertFalse(run.incidencias.filter(publicacion=self.retirada(), codigo__in=['HTTP', 'FICHA_INCOMPLETA']).exists())
        self.assertFalse(run.incidencias.filter(gravedad='error').exists())
        self.assertEqual(run.estado, 'finalizada')
        self.assertIsNone(self.retirada().retirada_en)
        self.assertEqual(run.observaciones.get(publicacion=self.retirada()).resultado, 'fallo')

    @base.ventana_cumplida()
    def test_dos_404_consecutivos_marcan_y_la_seleccion_la_omite(self):
        source = self.fuente()
        self.correr(source, 404)
        segunda, _ = self.correr(source, 404)
        self.assertIn('retirada confirmada', segunda.incidencias.get(codigo='FICHA_NO_DISPONIBLE').detalle)
        self.assertIsNotNone(self.retirada().retirada_en)
        self.assertEqual(segunda.estado, 'finalizada')
        fichas, _ = seleccionar_fichas(source, [])
        self.assertNotIn(RETIRADA, fichas)
        self.assertIn(VIGENTE, fichas)
        tercera, pedidas = self.correr(source, 404)
        self.assertNotIn(RETIRADA, pedidas)  # ya no ocupa cupo de conocidas
        self.assertFalse(tercera.incidencias.filter(codigo='FICHA_NO_DISPONIBLE').exists())

    @base.ventana_cumplida()
    def test_un_200_entre_dos_404_reinicia_la_confirmacion(self):
        source = self.fuente()
        self.correr(source, 404)
        self.correr(source, 200)
        self.correr(source, 404)
        self.assertIsNone(self.retirada().retirada_en)

    @base.ventana_cumplida()
    def test_410_tambien_es_ficha_retirada(self):
        source = self.fuente()
        run, _ = self.correr(source, 410)
        self.assertEqual(run.incidencias.get(codigo='FICHA_NO_DISPONIBLE').gravedad, 'aviso')
        self.assertEqual(run.estado, 'finalizada')
        self.correr(source, 410)
        self.assertIsNotNone(self.retirada().retirada_en)

    @base.ventana_cumplida()
    def test_500_sigue_siendo_error_y_deja_parcial(self):
        source = self.fuente()
        run, _ = self.correr(source, 500)
        self.assertFalse(run.incidencias.filter(codigo='FICHA_NO_DISPONIBLE').exists())
        self.assertTrue(run.incidencias.filter(codigo='HTTP', gravedad='error', publicacion=self.retirada()).exists())
        self.assertTrue(run.incidencias.filter(codigo='FICHA_INCOMPLETA', gravedad='error').exists())
        self.assertEqual(run.estado, 'parcial')
        self.correr(source, 500)
        self.assertIsNone(self.retirada().retirada_en)

    @base.ventana_cumplida()
    def test_si_reaparece_en_el_indice_se_limpia_la_marca(self):
        source = self.fuente()
        self.correr(source, 404)
        self.correr(source, 404)
        self.assertIsNotNone(self.retirada().retirada_en)
        run, pedidas = self.correr(source, 200, en_indice=[RETIRADA])
        self.assertIn(RETIRADA, pedidas)
        self.assertIsNone(self.retirada().retirada_en)
        self.assertEqual(run.estado, 'finalizada')


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class AvisoFichaRetiradaTests(TransactionTestCase):
    setUpBase = transicion.CandidateTransitionTests.setUpBase
    source = transicion.CandidateTransitionTests.source
    setUp = transicion.CandidateTransitionTests.setUp
    execute = transicion.CandidateTransitionTests.execute

    def test_la_api_expone_la_marca_y_la_convocatoria_su_aviso_sin_cambiarla(self):
        from rest_framework.test import APIClient
        from convocatorias.models import BorradorRastreo
        self.execute(fiche(foreign=True))
        origin = BorradorRastreo.objects.get(publicacion__url_normalizada=URL)
        offer = origin.convocatoria
        client = APIClient()
        client.force_login(self.actor)
        detalle = lambda: client.get(f'/api/gestion/convocatorias/{offer.pk}/').data
        self.assertFalse(detalle()['ficha_retirada'])
        antes = (offer.revision, offer.activa, offer.version)
        Publicacion.objects.filter(pk=origin.publicacion_id).update(retirada_en=timezone.now())
        self.assertTrue(detalle()['ficha_retirada'])
        fila = next(r for r in client.get('/api/gestion/rastreo/publicaciones/').data['results'] if r['id'] == origin.publicacion_id)
        self.assertIsNotNone(fila['retirada_en'])
        offer.refresh_from_db()
        self.assertEqual((offer.revision, offer.activa, offer.version), antes)  # no se despublica ni cambia nada
        public = APIClient().get(f'/api/becas/{offer.pk}/')
        self.assertNotIn('ficha_retirada', public.data if public.status_code == 200 else {})
