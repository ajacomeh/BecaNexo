"""Incidencias: aviso documental una vez por documento e INDICE_LIMITE como aviso solo por rotación con /4.

HTTP simulado; escribe solo en la base de pruebas aislada.
"""
import uuid
from unittest.mock import patch

from django.test import TransactionTestCase

from convocatorias.siau_red import NATIONAL_INDEX, PDFS, ROBOTS
from . import tests as base
from .services import run_manual, set_paginated_discovery, summary
from .test_ajax_pagination import AjaxPaginationTests, ROBOTS_ALLOW, card, index

SIAU = 'https://siau.senescyt.gob.ec'
MUCHAS = [SIAU + f'/oferta-de-becas-nacionales-rotacion-{n}/' for n in range(14)]


class IncidenciasRotacionTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    configured = AjaxPaginationTests.configured
    network = AjaxPaginationTests.network

    def correr(self, source, red, ajax=(200, {'content-type': 'text/html'}, None)):
        respuesta = ajax if ajax[2] is not None else (ajax[0], ajax[1], card())
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red), \
                patch('convocatorias.siau_red.Downloader.post_once', return_value=respuesta):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        return run, summary(run)['estado']

    def indice_limite(self, run):
        return list(run.incidencias.filter(codigo='INDICE_LIMITE').values_list('gravedad', flat=True))

    @base.ventana_cumplida()
    def test_revision_documental_una_vez_por_documento_y_de_nuevo_si_cambia(self):
        source = self.source()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake):
            primera = run_manual(source.pk, self.actor.pk, uuid.uuid4())
            segunda = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        bases = primera.accesos.filter(rol='bases', documento__isnull=False).values('url_normalizada').distinct().count()
        self.assertGreaterEqual(bases, 1)
        self.assertEqual(primera.incidencias.filter(codigo='REVISION_DOCUMENTAL_PENDIENTE').count(), bases)  # una por documento
        self.assertFalse(segunda.incidencias.filter(codigo='REVISION_DOCUMENTAL_PENDIENTE').exists())
        self.assertTrue(segunda.accesos.filter(rol='bases', resultado='reutilizado').exists())

        url_bases = primera.accesos.filter(rol='bases', documento__isnull=False).first().url_normalizada
        self.assertIn(url_bases, PDFS)

        def nuevo_pdf(url):
            return (200, {'content-type': 'application/pdf'}, b'%PDF-1.4\nBases cambiadas') if url == url_bases else self.fake(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=nuevo_pdf):
            tercera = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(tercera.incidencias.filter(codigo='REVISION_DOCUMENTAL_PENDIENTE').count(), 1)
        self.assertTrue(tercera.incidencias.filter(codigo='PDF_CAMBIADO').exists())
        for run in (primera, segunda, tercera):
            self.assertEqual(summary(run)['estado'], 'finalizada')  # los avisos no degradan el estado

    @base.ventana_cumplida()
    def test_v4_rotacion_por_diseno_es_aviso_y_la_corrida_queda_finalizada(self):
        source = self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)

        def red(url):
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, index(max_pages=3) + b''.join(card(u) for u in MUCHAS)
            if url in MUCHAS:
                from .test_periodico import national_ficha
                return 200, {'content-type': 'text/html'}, national_ficha()
            return self.network(url)
        run, estado = self.correr(source, red)
        self.assertEqual(self.indice_limite(run), ['aviso'])
        self.assertFalse(run.incidencias.filter(gravedad='error').exists())
        self.assertEqual(estado, 'finalizada')

    @base.ventana_cumplida()
    def test_v3_el_limite_del_indice_sigue_siendo_error(self):
        source = self.configured()  # política /3
        run, estado = self.correr(source, self.network)
        self.assertEqual(self.indice_limite(run), ['error'])
        self.assertEqual(estado, 'parcial')

    @base.ventana_cumplida()
    def test_v4_fallos_reales_del_indice_y_del_ajax_siguen_degradando(self):
        source = self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)
        casos = {
            'página AJAX con HTTP 500': (self.network, (500, {'content-type': 'text/html'}, b''), 'HTTP'),
            'respuesta AJAX inválida': (self.network, (200, {'content-type': 'text/html'}, b'<html>sin tarjetas</html>'), 'INDICE_ESTRUCTURA'),
            'robots.txt no autoriza el AJAX': (
                lambda url: (200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /wp-admin/\n') if url == ROBOTS else self.network(url),
                (200, {'content-type': 'text/html'}, None), 'ROBOTS'),
            'índice nacional con HTTP 500': (
                lambda url: (500, {'content-type': 'text/html'}, b'') if url == NATIONAL_INDEX else self.network(url),
                (200, {'content-type': 'text/html'}, None), 'HTTP'),
        }
        for nombre, (red, ajax, codigo) in casos.items():
            with self.subTest(nombre):
                run, estado = self.correr(source, red, ajax)
                self.assertTrue(run.incidencias.filter(codigo=codigo, gravedad='error').exists())
                self.assertEqual(estado, 'parcial')
                self.assertNotIn('error', self.indice_limite(run))  # la rotación nunca es el error

    @base.ventana_cumplida()
    def test_v4_http_429_en_el_ajax_detiene_la_corrida(self):
        source = self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)
        run, estado = self.correr(source, self.network, (429, {'content-type': 'text/html', 'retry-after': '120'}, b''))
        self.assertEqual(estado, 'fallida')
        self.assertTrue(run.incidencias.filter(codigo='HTTP', gravedad='error').exists())
