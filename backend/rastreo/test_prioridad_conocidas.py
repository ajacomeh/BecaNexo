"""Reparto del cupo de fichas por corrida entre publicaciones conocidas y candidatos nuevos (siau-nacionales/4).

HTTP simulado; escribe solo en la base de pruebas aislada.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TransactionTestCase
from django.utils import timezone

from convocatorias.siau_red import NATIONAL_INDEX
from . import tests as base
from .descubrimiento import MAX_FICHAS
from .models import Observacion, Publicacion
from .services import MAX_FICHAS_CONOCIDAS, run_manual, seleccionar_fichas, set_paginated_discovery
from . import test_ajax_pagination as ajax
from .test_ajax_pagination import PAGE, card, index
from .test_periodico import national_ficha

SIAU = 'https://siau.senescyt.gob.ec'
CONOCIDAS = [SIAU + f'/oferta-de-becas-nacionales-conocida-{n}/' for n in range(8)]
NUEVAS = [SIAU + f'/oferta-de-becas-nacionales-nueva-{n}/' for n in range(20)]


class PrioridadConocidasTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    configured = ajax.AjaxPaginationTests.configured
    network = ajax.AjaxPaginationTests.network

    def conocidas(self, source, cantidad):
        ahora = timezone.now()
        for n, url in enumerate(CONOCIDAS[:cantidad]):
            # Última detección escalonada: la 0 es la más antigua.
            Publicacion.objects.create(fuente=source, url_original=url, url_normalizada=url, normalizacion_version='urls-cerradas/1',
                                       primera_deteccion=ahora - timedelta(days=20 - n), ultima_deteccion=ahora - timedelta(days=20 - n))

    def test_reparto_del_cupo(self):
        self.assertEqual((MAX_FICHAS, MAX_FICHAS_CONOCIDAS), (12, 6))
        source = self.source()
        self.conocidas(source, 6)
        fichas, mas = seleccionar_fichas(source, NUEVAS)
        self.assertEqual(fichas, [*CONOCIDAS[:6], *NUEVAS[:6]])  # 6 + 6, conocidas por última detección más antigua
        self.assertTrue(mas)

    def test_pocas_conocidas_ceden_el_cupo_a_las_nuevas(self):
        source = self.source()
        self.conocidas(source, 2)
        fichas, _ = seleccionar_fichas(source, NUEVAS)
        self.assertEqual(fichas, [*CONOCIDAS[:2], *NUEVAS[:10]])  # 2 + 10: el cupo sobrante pasa a las nuevas
        fichas, mas = seleccionar_fichas(source, NUEVAS[:3])
        self.assertEqual(fichas, [*CONOCIDAS[:2], *NUEVAS[:3]])
        self.assertFalse(mas)

    def test_pocas_nuevas_dejan_el_cupo_a_las_conocidas_sin_pasar_de_12(self):
        source = self.source()
        ahora = timezone.now()
        urls = [SIAU + f'/oferta-de-becas-nacionales-vista-{n}/' for n in range(15)]
        for n, url in enumerate(urls):
            Publicacion.objects.create(fuente=source, url_original=url, url_normalizada=url, normalizacion_version='urls-cerradas/1',
                                       primera_deteccion=ahora - timedelta(hours=15 - n), ultima_deteccion=ahora - timedelta(hours=15 - n))
        fichas, mas = seleccionar_fichas(source, NUEVAS[:2])
        self.assertEqual(len(fichas), MAX_FICHAS)
        self.assertEqual(fichas, [*urls[:10], *NUEVAS[:2]])
        self.assertTrue(mas)

    @base.ventana_cumplida()
    def test_corrida_v4_visita_conocidas_fuera_del_indice_y_cuenta_sin_cambios(self):
        source = self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)
        self.conocidas(source, 6)
        # El índice de esta corrida solo trae candidatos nuevos (su primera tarjeta es PAGE): las conocidas se piden por su URL guardada.
        indice = index(max_pages=1) + b''.join(card(url) for url in NUEVAS)
        nuevas = [PAGE, *NUEVAS[:5]]

        def red(url):
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, indice
            if url in CONOCIDAS or url in NUEVAS or url == PAGE:
                return 200, {'content-type': 'text/html'}, national_ficha()
            return self.network(url)

        with patch('convocatorias.siau_red.Downloader.once', side_effect=red), patch('convocatorias.siau_red.Downloader.post_once'):
            primera = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        visitadas = set(primera.accesos.filter(rol='ficha').values_list('url_normalizada', flat=True))
        self.assertEqual(visitadas, {*CONOCIDAS[:6], *nuevas})
        self.assertLessEqual(len(visitadas), MAX_FICHAS)
        antes = dict(Publicacion.objects.filter(url_normalizada__in=CONOCIDAS[:6]).values_list('url_normalizada', 'ultima_deteccion'))
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red), patch('convocatorias.siau_red.Downloader.post_once'):
            segunda = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        # Las conocidas observadas la vez anterior y sin cambios de contenido cuentan como «sin cambios».
        sin_cambios = set(Observacion.objects.filter(ejecucion=segunda, resultado='sin_cambios')
                          .values_list('publicacion__url_normalizada', flat=True))
        self.assertTrue(sin_cambios)
        self.assertTrue(sin_cambios <= {*CONOCIDAS[:6], *nuevas})
        segunda.refresh_from_db()
        self.assertEqual(segunda.observaciones_sin_cambios, len(sin_cambios))
        despues = dict(Publicacion.objects.filter(url_normalizada__in=sin_cambios).values_list('url_normalizada', 'ultima_deteccion'))
        self.assertTrue(all(despues[url] > antes.get(url, despues[url] - timedelta(seconds=1)) for url in despues if url in antes))
