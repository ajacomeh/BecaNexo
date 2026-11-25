"""Variante de ficha SIAU con «Requisitos para aplicar» y sin «REQUISITOS GENERALES» (sintética, sin HTML real)."""
from pathlib import Path

from django.test import SimpleTestCase

from .siau_extraccion import extract_html

FIXTURE = Path(__file__).parent / 'fixtures/siau/ficha_sintetica.html'
URL = 'https://siau.senescyt.gob.ec/ficha-sintetica/'


def extraer(html):
    return extract_html({'contenido': html.encode(), 'url': URL, 'consulta_utc': '2026-11-25T12:00:00+00:00'})


def variante():
    """La ficha sintética sin marcas principales: el bloque de requisitos se titula «Requisitos para aplicar»."""
    html = FIXTURE.read_text(encoding='utf8').replace('<p>Requisitos generales para aplicar</p><p>CONDICIONES OBLIGATORIAS</p>',
                                                      '<p>Requisitos para aplicar</p><p>Todos los requisitos y formularios los podrás descargar dando clic en BASES.</p>')
    assert 'REQUISITOS GENERALES' not in html and 'Requisitos generales para aplicar' not in html
    return html


class RequisitosParaAplicarTests(SimpleTestCase):
    def test_la_variante_queda_completa_con_requisitos_literales(self):
        item = extraer(variante())
        self.assertTrue(item['seccion_completa'])
        self.assertEqual(item['requisitos']['texto_original'],
                         'Todos los requisitos y formularios los podrás descargar dando clic en BASES.\n'
                         'No haber sido sancionado por desistimiento.\nCondición académica ficticia.\n'
                         'Nota adicional no estructurable: comprobación exclusiva por la entidad.')
        # Literal: el pie de página no entra ni se infiere nada; el resto de campos se leen igual.
        self.assertNotIn('Contenido ajeno', item['requisitos']['texto_original'])
        self.assertNotIn('Requisitos para aplicar', item['postulacion_y_documentos']['texto_original'])
        anterior = extraer(FIXTURE.read_text(encoding='utf8'))
        for campo in ('titulo', 'descripcion', 'cierre', 'beneficio', 'enlaces_bases'):
            self.assertEqual(item[campo], anterior[campo], campo)

    def test_con_requisitos_generales_se_lee_igual_que_antes(self):
        # Aunque también diga «Requisitos para aplicar», mandan las marcas principales.
        html = FIXTURE.read_text(encoding='utf8').replace('<p>¿Cómo postular?</p>', '<p>Requisitos para aplicar</p><p>¿Cómo postular?</p>')
        item = extraer(html)
        self.assertTrue(item['seccion_completa'])
        self.assertTrue(item['requisitos']['texto_original'].startswith('CONDICIONES OBLIGATORIAS'))
        original = extraer(FIXTURE.read_text(encoding='utf8'))
        self.assertEqual(original['requisitos'], extraer(FIXTURE.read_text(encoding='utf8'))['requisitos'])
        self.assertTrue(original['requisitos']['texto_original'].startswith('CONDICIONES OBLIGATORIAS'))

    def test_sin_ninguna_marca_sigue_incompleta(self):
        html = FIXTURE.read_text(encoding='utf8').replace('<p>Requisitos generales para aplicar</p>', '<p>Documentos</p>')
        item = extraer(html)
        self.assertFalse(item['seccion_completa'])
        self.assertEqual(item['requisitos']['texto_original'], '')
