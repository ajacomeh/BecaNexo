"""Política siau-nacionales/4: índice ampliado, límite de fichas, bases admitidas y robots.txt.

HTTP siempre simulado; escribe solo en la base de pruebas aislada.
"""
import uuid
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase

from convocatorias.siau_red import INDEX, NATIONAL_INDEX, ROBOTS
from . import tests as base
from .descubrimiento import MAX_FICHAS
from .models import Publicacion
from .services import enable_discovery, enable_national_discovery, run_manual, set_paginated_discovery
from .test_ajax_pagination import ROBOTS_ALLOW, index
from .test_periodico import national_ficha

SIAU = 'https://siau.senescyt.gob.ec'
MUJERES = SIAU + '/programa-de-becas-para-mujeres-ecuatorianas-universidad-europea-ministerio-de-gobierno-del-ecuador/'
NACIONALES = [SIAU + f'/oferta-de-becas-nacionales-sintetica-{n}/' for n in range(MAX_FICHAS + 1)]
PDF_SIAU = SIAU + '/wp-content/uploads/2026/11/bases-sinteticas.pdf'
ZIP_SIAU = SIAU + '/wp-content/uploads/2026/10/2026-0494.zip'
PDF_EXTERNO = 'https://bases.example.org/wp-content/uploads/2026/11/bases.pdf'
ENLACE_FIXTURE = b'/wp-content/uploads/2026/10/bn_4to_nivel_2026_13102026_vf-1.pdf'


def tarjeta(url, titulo):
    return (f'<article class="category-convocatorias"><h2 class="entry-title"><a href="{url}">{titulo}</a></h2></article>').encode()


class IndiceYBasesV4Tests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake

    def configurada_v4(self):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        self.source()
        enable_discovery(self.actor.pk, 'Prueba índice')
        enable_national_discovery(self.actor.pk, 'Prueba nacionales')
        source, cambio = set_paginated_discovery(self.actor.pk, 'Ampliar el índice en pruebas', True)
        self.assertTrue(cambio)
        self.assertEqual(source.politica_version, 'siau-nacionales/4')
        return source

    def red(self, indice, fichas, robots=ROBOTS_ALLOW, pedidas=None):
        def responder(url):
            if pedidas is not None:
                pedidas.append(url)
            if url == ROBOTS:
                return 200, {'content-type': 'text/plain'}, robots
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, indice
            if url in fichas:
                return 200, {'content-type': 'text/html'}, fichas[url]
            if url == PDF_SIAU:
                return 200, {'content-type': 'application/pdf'}, b'%PDF-1.4\nBases sinteticas'
            return self.fake(url)
        return responder

    @base.ventana_cumplida()
    def test_indice_con_mas_candidatas_que_el_limite_incluye_becas_sin_rotulo_nacional(self):
        """/3 solo admitía «becas nacionales»; /4 admite cualquier beca, procesa 12 por corrida y rota el resto."""
        source = self.configurada_v4()
        indice = index(max_pages=1) + b''.join(tarjeta(u, f'Oferta de Becas Nacionales sintética {n}') for n, u in enumerate(NACIONALES)) \
            + tarjeta(MUJERES, 'Programa de Becas para Mujeres Ecuatorianas Universidad Europea – Ministerio de Gobierno del Ecuador')
        fichas = {u: national_ficha() for u in [*NACIONALES, MUJERES]}
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.red(indice, fichas)), \
                patch('convocatorias.siau_red.Downloader.post_once') as post:
            primera = run_manual(source.pk, self.actor.pk, uuid.uuid4())
            post.assert_not_called()  # max_num_pages=1: no hay paginación AJAX que seguir
        self.assertLessEqual(primera.accesos.filter(rol='ficha').count(), MAX_FICHAS)
        self.assertTrue(primera.incidencias.filter(codigo='INDICE_LIMITE').exists())
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.red(indice, fichas)), \
                patch('convocatorias.siau_red.Downloader.post_once'):
            run_manual(source.pk, self.actor.pk, uuid.uuid4())
        # Las no vistas tienen prioridad: en dos corridas se observan todas, incluida la beca sin «nacionales».
        observadas = set(Publicacion.objects.filter(fuente=source).values_list('url_normalizada', flat=True))
        self.assertIn(MUJERES, observadas)
        self.assertTrue(set(NACIONALES) <= observadas)
        self.assertFalse(Publicacion.objects.exclude(convocatoria=None).filter(fuente=source, convocatoria__revision='validada').exists())

    @base.ventana_cumplida()
    def test_bases_pdf_del_host_admitido_y_rechazo_de_zip_y_de_otro_host(self):
        source = self.configurada_v4()
        ficha = NACIONALES[0]
        html = national_ficha().replace(ENLACE_FIXTURE, PDF_SIAU.encode())
        extra = (f'<a href="{ZIP_SIAU}"><span>BASES</span></a> <a href="{PDF_EXTERNO}"><span>BASES</span></a>').encode()
        html = html.replace(b'<span>BASES</span></a>', b'<span>BASES</span></a> ' + extra, 1)
        pedidas = []
        indice = index(max_pages=1) + tarjeta(ficha, 'Oferta de Becas Nacionales sintética')
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.red(indice, {ficha: html}, pedidas=pedidas)), \
                patch('convocatorias.siau_red.Downloader.post_once'):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        publicacion = Publicacion.objects.get(url_normalizada=ficha)
        version = publicacion.versiones.get()
        self.assertEqual(version.documentos.filter(rol='bases_pdf').count(), 1)  # el PDF del propio SIAU
        self.assertIn(PDF_SIAU, pedidas)
        self.assertNotIn(ZIP_SIAU, pedidas)      # un ZIP no es una base PDF admitida
        self.assertNotIn(PDF_EXTERNO, pedidas)   # otro host nunca se solicita
        pendientes = {p['url']: p['estado'] for p in version.manifiesto.get('pendientes') or []}
        self.assertEqual(pendientes.get(ZIP_SIAU), 'fuera_de_lista')
        self.assertEqual(pendientes.get(PDF_EXTERNO), 'fuera_de_lista')
        self.assertTrue(run.incidencias.filter(codigo='BASE_NO_PERMITIDA', publicacion=publicacion).exists())
        # Omitir enlaces fuera de la lista cerrada es una decisión por diseño: aviso, sin degradar a «parcial»
        self.assertEqual(set(run.incidencias.filter(codigo='BASE_NO_PERMITIDA').values_list('gravedad', flat=True)), {'aviso'})
        # (El estado «finalizada» con solo este aviso se comprueba en test_periodico.)

    @base.ventana_cumplida()
    def test_robots_sigue_mandando_sobre_las_fichas(self):
        source = self.configurada_v4()
        bloqueada, permitida = NACIONALES[0], NACIONALES[1]
        robots = ROBOTS_ALLOW + b'Disallow: /oferta-de-becas-nacionales-sintetica-0/\n'
        indice = index(max_pages=1) + tarjeta(bloqueada, 'Oferta de Becas Nacionales 0') + tarjeta(permitida, 'Oferta de Becas Nacionales 1')
        pedidas = []
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.red(
                indice, {bloqueada: national_ficha(), permitida: national_ficha()}, robots=robots, pedidas=pedidas)), \
                patch('convocatorias.siau_red.Downloader.post_once'):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertNotIn(bloqueada, pedidas)
        self.assertIn(permitida, pedidas)
        self.assertTrue(run.incidencias.filter(codigo='ROBOTS').exists())
        self.assertTrue(run.accesos.filter(url_normalizada=bloqueada, resultado='bloqueado').exists())
