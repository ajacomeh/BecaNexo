"""Propuestas editoriales puras: HTML/PDF sintéticos, sin escrituras ni red."""
from django.test import SimpleTestCase

from .evidencia_tabular import extraer_tablas
from .propuestas_documentales import proponer


URL = 'https://institucion.edu.ec/becas/'
ORIGIN = {'version_id': 4, 'documento_id': 7, 'pagina': 2, 'url': URL + 'bases.pdf'}


def fragment(text, kind, *, category=None, condition='inicial_por_revisar', date=None, percentages=()):
    return {'texto_original': text, 'tipo': kind, 'categoria': category, 'seccion': 'Bases',
            'condicion': condition, 'fecha_sugerida': date, 'porcentajes_literales': percentages,
            'enlaces_literales': [], 'procedencia': ORIGIN}


class PropuestasDocumentalesTests(SimpleTestCase):
    def test_istcge_separa_programa_cuotas_y_renovacion(self):
        html = extraer_tablas(b'''<h2>Cronograma general</h2><table>
          <tr><td>Cierre programa general</td><td>22/11/2026</td></tr>
          <tr><td>Politica de Cuotas, proceso separado</td><td>12/12/2026</td></tr></table>
          <h2>Beca socioeconomica</h2><table><tr><td>Renovacion: mantener promedio</td></tr></table>
          <a href="/bases.pdf">Bases oficiales</a>''', URL, version_id=4, documento_id=7)
        result = proponer(html, {'documentos': []})
        self.assertFalse(any(row['campo'] == 'cierre_dia' for row in result))
        self.assertFalse(any(row['destino'] == 'requisitos' for row in result))
        self.assertEqual(next(row for row in result if row['campo'] == 'url_bases')['valor'], 'https://institucion.edu.ec/bases.pdf')

    def test_puce_alternativas_y_cobertura_variable_no_se_validan(self):
        rows = [fragment('Presentar discapacidad', 'requisito', category='Beca Solidaridad',
                         condition='alternativa_por_revisar'),
                fragment('Cobertura del 75% al 100% segun evaluacion', 'beneficio', percentages=['75%', '100%'])]
        result = proponer({}, {'documentos': [{'fragmentos': rows}]})
        self.assertIsNone(result[0]['destino'])
        self.assertEqual(result[1]['destino'], 'beneficios')
        self.assertTrue(any('porcentaje fijo' in note for note in result[1]['advertencias']))
        self.assertEqual(result[1]['valor'], rows[1]['texto_original'])
        self.assertEqual(result[1]['procedencia']['pagina'], 2)

    def test_occitec_requisito_general_y_cierre_explicito(self):
        rows = [fragment('Ser ciudadano ecuatoriano', 'requisito'),
                fragment('Cierre de postulaciones 12/11/2026', 'cronograma', date='2026-11-12'),
                fragment('Inicio del curso 20/11/2026', 'cronograma', date='2026-11-20'),
                fragment('Programa de innovacion educativa', 'programa_o_nivel'),
                fragment('Modalidad en linea', 'modalidad'),
                fragment('Otorgada por OCCITEC', 'oferente_mencionado')]
        result = proponer({}, {'documentos': [{'fragmentos': rows}]})
        self.assertEqual([row['destino'] for row in result],
                         ['requisitos', 'general', None, None, None, None])
        self.assertEqual(result[1]['campo'], 'cierre_dia')
        self.assertEqual(result[1]['valor'], '2026-11-12')
        self.assertTrue(all(row['estado'] == 'pendiente_revision' for row in result))

    def test_idempotencia_y_categoria_no_se_propaga_a_otra_pagina(self):
        row = fragment('Presentar cedula', 'documento_exigido')
        result = proponer({}, {'documentos': [{'fragmentos': [row, row]}]})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['procedencia'], ORIGIN)

    def test_requisito_especifico_sin_categoria_expresa_no_se_prepara_como_general(self):
        row = {**fragment('Presentar acreditacion deportiva', 'requisito'),
               'seccion': 'Requisitos especificos'}
        result = proponer({}, {'documentos': [{'fragmentos': [row]}]})
        self.assertIsNone(result[0]['destino'])
        self.assertTrue(result[0]['advertencias'])

    def test_alternativas_en_filas_separadas_no_se_vuelven_acumulativas(self):
        html = extraer_tablas(b'''<h2>Requisitos</h2><table>
          <tr><td>Una de las siguientes alternativas</td></tr>
          <tr><td>Acreditar discapacidad</td></tr>
          <tr><td>Presentar certificado de vulnerabilidad</td></tr></table>''',
          URL, version_id=4, documento_id=7)
        result = proponer(html, {'documentos': []})
        self.assertTrue(result)
        self.assertTrue(all(row['destino'] is None for row in result))
