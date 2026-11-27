"""Fichas retiradas: revisión semanal, al final de la cola, y la lista fija PAGES no las desmarca en cada corrida.

HTTP simulado; escribe solo en la base de pruebas aislada.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TransactionTestCase
from django.utils import timezone

from convocatorias.siau_red import NATIONAL_INDEX, PAGES
from . import tests as base
from . import test_ajax_pagination as ajax
from .descubrimiento import MAX_FICHAS
from .models import Publicacion
from .services import REVISION_RETIRADAS, run_manual, seleccionar_fichas, set_paginated_discovery
from .test_ajax_pagination import PAGE, card, index
from .test_periodico import national_ficha

SIAU = 'https://siau.senescyt.gob.ec'
VIGENTE = SIAU + '/oferta-de-becas-nacionales-vigente/'
RETIRADA = SIAU + '/oferta-de-becas-nacionales-retirada/'
FIJA = PAGES[0]  # URL de la lista fija PAGES (en la base real, la publicación #1)


class RevisionRetiradasTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    configured = ajax.AjaxPaginationTests.configured
    network = ajax.AjaxPaginationTests.network

    def fuente(self, *urls):
        self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)
        ahora = timezone.now()
        for n, url in enumerate(urls):
            # La primera es la de última detección más antigua.
            Publicacion.objects.create(fuente=source, url_original=url, url_normalizada=url, normalizacion_version='urls-cerradas/1',
                                       primera_deteccion=ahora - timedelta(days=10 - n), ultima_deteccion=ahora - timedelta(days=10 - n))
        return source

    def correr(self, source, muertas, en_indice=()):
        """Una corrida: las URL de `muertas` responden 404; `en_indice` aparecen como tarjetas del índice nacional."""
        indice = index(max_pages=1) + b''.join(card(url) for url in en_indice)

        def red(url):
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, indice
            if url in muertas:
                return 404, {'content-type': 'text/html'}, b''
            if url in (VIGENTE, RETIRADA, PAGE):
                return 200, {'content-type': 'text/html'}, national_ficha()
            return self.network(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red) as llamadas, patch('convocatorias.siau_red.Downloader.post_once'):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        return run, [c.args[0] for c in llamadas.call_args_list]

    def retirar(self, source, url):
        """Dos corridas con 404 confirman la retirada (como en producción)."""
        self.correr(source, {url})
        self.correr(source, {url})
        publicacion = Publicacion.objects.get(url_normalizada=url)
        self.assertIsNotNone(publicacion.retirada_en)
        return publicacion

    def test_constante_de_revision_semanal(self):
        self.assertEqual(REVISION_RETIRADAS, timedelta(days=7))

    @base.ventana_cumplida()
    def test_retirada_no_entra_en_la_reserva_antes_de_7_dias(self):
        source = self.fuente(RETIRADA, VIGENTE)
        self.retirar(source, RETIRADA)
        for dias in (0, 3, 6):
            with self.subTest(dias=dias):
                fichas, _ = seleccionar_fichas(source, [], now=timezone.now() + timedelta(days=dias))
                self.assertNotIn(RETIRADA, fichas)
                self.assertIn(VIGENTE, fichas)
        # Tampoco cuenta como candidato nuevo aunque llegue entre los candidatos (fuera del índice).
        fichas, _ = seleccionar_fichas(source, [RETIRADA], indexed=set())
        self.assertNotIn(RETIRADA, fichas)

    @base.ventana_cumplida()
    def test_retirada_entra_despues_de_7_dias_al_final_de_la_cola(self):
        source = self.fuente(RETIRADA, VIGENTE)
        self.retirar(source, RETIRADA)
        fichas, _ = seleccionar_fichas(source, [], now=timezone.now() + timedelta(days=8))
        self.assertIn(RETIRADA, fichas)
        self.assertEqual(fichas[-1], RETIRADA)  # después de todas las conocidas no retiradas
        self.assertLess(fichas.index(VIGENTE), fichas.index(RETIRADA))
        # Con la cola llena de conocidas no retiradas, la retirada espera (queda fuera del cupo).
        ahora = timezone.now()
        for n in range(MAX_FICHAS):
            url = SIAU + f'/oferta-de-becas-nacionales-relleno-{n}/'
            Publicacion.objects.create(fuente=source, url_original=url, url_normalizada=url, normalizacion_version='urls-cerradas/1',
                                       primera_deteccion=ahora - timedelta(days=30), ultima_deteccion=ahora - timedelta(days=30))
        fichas, mas = seleccionar_fichas(source, [], now=timezone.now() + timedelta(days=8))
        self.assertNotIn(RETIRADA, fichas)
        self.assertTrue(mas)

    @base.ventana_cumplida()
    def test_corrida_revisa_la_retirada_solo_cuando_vence_la_semana(self):
        source = self.fuente(RETIRADA, VIGENTE)
        retirada = self.retirar(source, RETIRADA)
        marca = retirada.retirada_en
        _, pedidas = self.correr(source, {RETIRADA})
        self.assertNotIn(RETIRADA, pedidas)  # dentro de la semana: no se pide
        with patch('rastreo.services.REVISION_RETIRADAS', timedelta(0)):
            run, pedidas = self.correr(source, {RETIRADA})  # semana vencida: se pide una vez
        self.assertIn(RETIRADA, pedidas)
        self.assertIn('retirada confirmada', run.incidencias.get(codigo='FICHA_NO_DISPONIBLE', publicacion=retirada).detalle)
        self.assertEqual(Publicacion.objects.get(pk=retirada.pk).retirada_en, marca)  # sigue retirada, con su fecha original
        _, pedidas = self.correr(source, {RETIRADA})
        self.assertNotIn(RETIRADA, pedidas)  # y vuelve a esperar otra semana
        # Si al revisarla responde 200, deja de estar retirada.
        with patch('rastreo.services.REVISION_RETIRADAS', timedelta(0)):
            _, pedidas = self.correr(source, set())
        self.assertIn(RETIRADA, pedidas)
        self.assertIsNone(Publicacion.objects.get(pk=retirada.pk).retirada_en)

    @base.ventana_cumplida()
    def test_url_de_pages_retirada_no_se_pide_en_cada_corrida(self):
        source = self.fuente(FIJA, VIGENTE)
        fija = self.retirar(source, FIJA)
        marca = fija.retirada_en
        for _ in range(2):
            run, pedidas = self.correr(source, {FIJA})
            self.assertNotIn(FIJA, pedidas)
            self.assertFalse(run.incidencias.filter(publicacion=fija, codigo='FICHA_NO_DISPONIBLE').exists())
        # La marca no se borra ni se renueva: conserva la fecha de la confirmación.
        self.assertEqual(Publicacion.objects.get(pk=fija.pk).retirada_en, marca)

    @base.ventana_cumplida()
    def test_url_que_reaparece_en_el_indice_recupera_su_estado(self):
        source = self.fuente(FIJA, RETIRADA, VIGENTE)
        self.retirar(source, RETIRADA)
        self.retirar(source, FIJA)
        run, pedidas = self.correr(source, set(), en_indice=[RETIRADA, FIJA])
        self.assertIn(RETIRADA, pedidas)
        self.assertIn(FIJA, pedidas)
        self.assertFalse(Publicacion.objects.filter(url_normalizada__in=[RETIRADA, FIJA], retirada_en__isnull=False).exists())
        self.assertEqual(run.estado, 'finalizada')

    @base.ventana_cumplida()
    def test_primer_404_se_confirma_en_la_corrida_siguiente(self):
        source = self.fuente(RETIRADA, VIGENTE)
        primera, _ = self.correr(source, {RETIRADA})
        self.assertIn('se confirmará si se repite', primera.incidencias.get(codigo='FICHA_NO_DISPONIBLE').detalle)
        publicacion = Publicacion.objects.get(url_normalizada=RETIRADA)
        self.assertIsNone(publicacion.retirada_en)
        # Sin marca y con la última detección más antigua, encabeza la reserva de conocidas.
        fichas, _ = seleccionar_fichas(source, [])
        self.assertEqual(fichas[0], RETIRADA)
        segunda, pedidas = self.correr(source, {RETIRADA})
        self.assertIn(RETIRADA, pedidas)
        self.assertIn('retirada confirmada', segunda.incidencias.get(codigo='FICHA_NO_DISPONIBLE').detalle)
        self.assertIsNotNone(Publicacion.objects.get(pk=publicacion.pk).retirada_en)
