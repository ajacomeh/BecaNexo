"""Una corrida siau-nacionales/4 con la variante «Requisitos para aplicar» no registra error de ESTRUCTURA.

HTTP simulado; escribe solo en la base de pruebas aislada.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TransactionTestCase
from django.utils import timezone

from convocatorias.siau_red import NATIONAL_INDEX
from convocatorias.test_siau_requisitos_variante import FIXTURE, variante
from . import tests as base
from . import test_ajax_pagination as ajax
from .models import Publicacion
from .services import run_manual, set_paginated_discovery
from .test_ajax_pagination import PAGE, index

FICHA = 'https://siau.senescyt.gob.ec/oferta-de-becas-nacionales-variante/'
TITULO = 'Oferta de Becas Nacionales para Educación Continua'


class VarianteRequisitosTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    configured = ajax.AjaxPaginationTests.configured
    network = ajax.AjaxPaginationTests.network

    def correr(self, html):
        self.configured()
        source, _ = set_paginated_discovery(self.actor.pk, 'Ampliar en pruebas', True)
        ahora = timezone.now() - timedelta(days=5)
        Publicacion.objects.create(fuente=source, url_original=FICHA, url_normalizada=FICHA, normalizacion_version='urls-cerradas/1',
                                   primera_deteccion=ahora, ultima_deteccion=ahora)
        contenido = html.replace('PROGRAMA FICTICIO PARA PRUEBAS', TITULO).encode()

        def red(url):
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, index(max_pages=1)
            if url in (FICHA, PAGE):
                return 200, {'content-type': 'text/html'}, contenido
            return self.network(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red), patch('convocatorias.siau_red.Downloader.post_once'):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        return run, Publicacion.objects.get(url_normalizada=FICHA).versiones.order_by('-id').first()

    @base.ventana_cumplida()
    def test_la_variante_no_registra_error_de_estructura(self):
        run, version = self.correr(variante())
        self.assertFalse(run.incidencias.filter(codigo='ESTRUCTURA').exists())
        self.assertTrue(version.datos_extraidos['seccion_completa'])
        self.assertIn('No haber sido sancionado por desistimiento.', version.datos_extraidos['requisitos']['texto_original'])

    @base.ventana_cumplida()
    def test_sin_marcas_sigue_registrando_estructura(self):
        sin_marcas = FIXTURE.read_text(encoding='utf8').replace('<p>Requisitos generales para aplicar</p>', '<p>Documentos</p>')
        run, version = self.correr(sin_marcas)
        self.assertTrue(run.incidencias.filter(codigo='ESTRUCTURA', gravedad='error').exists())
        self.assertFalse(version.datos_extraidos['seccion_completa'])
