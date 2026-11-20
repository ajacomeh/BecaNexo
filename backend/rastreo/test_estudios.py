"""Opciones de estudio candidatas: solo lo que la ficha enumera, sin deducir niveles ni modalidades."""
from django.test import SimpleTestCase

from .estudios import campo_de_ficha, completar, modalidades_de_texto, nivel_de_expresion, opciones_candidatas

CATALOGO = {'bachillerato', 'grado', 'especializacion', 'maestria', 'doctorado', 'tecnico_superior',
            'tecnologico_superior', 'maestria_tecnologica', 'no_aplica'}
CATALOGO_ANTERIOR = {'bachillerato', 'grado', 'especializacion', 'maestria', 'doctorado', 'no_aplica'}
OBJETIVO = ('Este programa tiene como objetivo conceder becas a personas que hayan iniciado estudios de maestrías y '
            'especializaciones en universidades del país, y maestrías tecnológicas en institutos superiores.')
FICHA_PUB4 = ('Idioma: Español\nModalidad: Presencial, semipresencial, en\nlínea, a distancia, dual e híbrida\n'
              'APLICAR AHORA:\nBASES')


def menciones(enunciado, *expresiones, funcion='oferta_mencionada'):
    return [{'funcion': funcion, 'seccion': 'objetivo', 'contexto_original': enunciado, 'expresion_original': e}
            for e in expresiones]


def datos(modalidad='Presencial', destino='Ecuador', mentions=None, niveles=None):
    return {'estudios': {'niveles_mencionados': niveles or [], 'menciones_academicas': mentions or [],
                         'modalidad': {'texto_original': modalidad}, 'destino': {'texto_original': destino}}}


class EstudiosTests(SimpleTestCase):
    def test_campo_de_ficha_une_la_continuacion_sin_arrastrar_la_etiqueta_siguiente(self):
        self.assertEqual(campo_de_ficha(FICHA_PUB4, 'Modalidad'),
                         'Presencial, semipresencial, en línea, a distancia, dual e híbrida')
        self.assertEqual(campo_de_ficha('Modalidad: Todas las modalidades\nAPLICAR AHORA:', 'Modalidad'), 'Todas las modalidades')
        self.assertEqual(campo_de_ficha('Modalidad: En línea\nsigue otra frase.', 'Modalidad'), 'En línea sigue otra frase.')
        self.assertEqual(campo_de_ficha('Sin campo', 'Modalidad'), '')

    def test_completar_solo_cuando_el_texto_confirma_el_valor_extraido(self):
        self.assertEqual(completar('Presencial, semipresencial, en', FICHA_PUB4, 'Modalidad'),
                         'Presencial, semipresencial, en línea, a distancia, dual e híbrida')
        self.assertEqual(completar('Virtual', FICHA_PUB4, 'Modalidad'), 'Virtual')
        self.assertEqual(completar('', FICHA_PUB4, 'Modalidad'), '')
        self.assertEqual(completar('Ecuador', 'sin texto', r'Pa[ií]s'), 'Ecuador')

    def test_niveles_solo_por_nombre_exacto_y_maestria_tecnologica_no_es_maestria(self):
        cases = {'maestrías': 'maestria', 'Maestría': 'maestria', 'maestrías tecnológicas': 'maestria_tecnologica',
                 'maestría tecnológica': 'maestria_tecnologica', 'especializaciones': 'especializacion',
                 'Especialización': 'especializacion', 'grado': 'grado', 'Grado': 'grado', 'doctorado': 'doctorado',
                 'técnico superior': 'tecnico_superior', 'tecnológico superior': 'tecnologico_superior'}
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(nivel_de_expresion(expression), expected)
        for expression in ('técnico', 'tecnológico', 'tecnológico superior universitario', 'Posgrado', 'tecnológicos', ''):
            with self.subTest(expression=expression):
                self.assertIsNone(nivel_de_expresion(expression))

    def test_modalidades_enumeradas_y_no_enumeradas(self):
        self.assertEqual(modalidades_de_texto('Presencial, semipresencial, en línea, a distancia, dual e híbrida'),
                         (['presencial', 'semipresencial', 'virtual', 'hibrida'], ['a distancia', 'dual'], False))
        self.assertEqual(modalidades_de_texto('Todas las modalidades'), ([], [], True))
        self.assertEqual(modalidades_de_texto('Todas las modalidades (Presencial, semipresencial y en línea)'),
                         (['presencial', 'semipresencial', 'virtual'], [], True))
        self.assertEqual(modalidades_de_texto('Presencial e híbrida')[0], ['presencial', 'hibrida'])
        self.assertEqual(modalidades_de_texto('En linea')[0], ['virtual'])
        self.assertEqual(modalidades_de_texto('')[0], [])

    def test_una_opcion_por_nivel_y_modalidad_enumerados_en_el_mismo_enunciado(self):
        data = datos('Presencial, semipresencial, en', mentions=menciones(OBJETIVO, 'maestrías', 'especializaciones', 'maestrías tecnológicas')
                     + menciones(OBJETIVO, 'tecnológicos', funcion='incidental'))
        options, pending = opciones_candidatas(data, FICHA_PUB4, 91, CATALOGO)
        self.assertEqual([(o['nivel'], o['modalidad']) for o in options], [
            (level, mode) for level in ('maestria', 'especializacion', 'maestria_tecnologica')
            for mode in ('presencial', 'semipresencial', 'virtual', 'hibrida')])
        self.assertTrue(all(o['destino_original'] == 'Ecuador' and not o['validado'] for o in options))
        self.assertEqual(options[0]['procedencia']['enunciado'], OBJETIVO)
        self.assertEqual(options[0]['procedencia']['modalidad_original'],
                         'Presencial, semipresencial, en línea, a distancia, dual e híbrida')
        self.assertEqual([p['texto_original'] for p in pending], ['a distancia', 'dual'])

    def test_sin_equivalente_en_el_catalogo_queda_pendiente_con_motivo_y_sin_deducirlo(self):
        data = datos('En linea', mentions=menciones(OBJETIVO, 'maestrías', 'maestrías tecnológicas'))
        options, pending = opciones_candidatas(data, '', 7, CATALOGO_ANTERIOR)
        self.assertEqual([(o['nivel'], o['modalidad']) for o in options], [('maestria', 'virtual')])
        self.assertEqual(len(pending), 1)
        self.assertEqual((pending[0]['campo'], pending[0]['texto_original']), ('nivel', 'maestrías tecnológicas'))
        self.assertIn('sin equivalente exacto', pending[0]['motivo'])

    def test_todas_las_modalidades_junto_a_niveles_enumerados_se_expande_a_las_del_catalogo(self):
        enunciado = 'becas para estudios de tercer nivel técnico, tecnológico o de grado en instituciones del país'
        data = datos('Todas las modalidades', mentions=menciones(enunciado, 'técnico', 'tecnológico', 'grado'))
        modalidades = ('presencial', 'semipresencial', 'virtual', 'hibrida')
        options, pending = opciones_candidatas(data, 'Modalidad: Todas las modalidades', 5, CATALOGO, modalidades)
        self.assertEqual([(o['nivel'], o['modalidad']) for o in options], [('grado', m) for m in modalidades])
        self.assertTrue(all(o['procedencia']['todas_las_modalidades'] and o['procedencia']['enunciado'] == enunciado for o in options))
        # técnico y tecnológico sueltos no tienen equivalente exacto: quedan pendientes, no se deducen.
        self.assertEqual([(p['campo'], p['texto_original']) for p in pending], [('nivel', 'técnico'), ('nivel', 'tecnológico')])
        # Sin catálogo de modalidades disponible, no se deduce nada.
        options, pending = opciones_candidatas(data, 'Modalidad: Todas las modalidades', 5, CATALOGO)
        self.assertEqual(options, [])
        self.assertIn('sin enumerarlas', pending[-1]['motivo'])
        # Con modalidad enumerada, solo el nivel exacto genera opción.
        data = datos('Presencial', mentions=menciones(enunciado, 'técnico', 'tecnológico', 'grado'))
        options, pending = opciones_candidatas(data, '', 5, CATALOGO, modalidades)
        self.assertEqual([(o['nivel'], o['modalidad']) for o in options], [('grado', 'presencial')])
        self.assertEqual([p['texto_original'] for p in pending], ['técnico', 'tecnológico'])

    def test_enunciados_de_oferta_distintos_no_se_combinan(self):
        data = datos('Virtual', mentions=menciones('Primera frase de oferta de maestrías.', 'maestrías')
                     + menciones('Otra frase distinta sobre doctorado.', 'doctorado'))
        options, pending = opciones_candidatas(data, '', 3, CATALOGO)
        self.assertEqual(options, [])
        self.assertEqual(pending[0]['campo'], 'nivel')
        self.assertIn('no se combinan', pending[0]['motivo'])

    def test_sin_destino_no_se_propone_opcion_y_sin_menciones_se_usa_el_nivel_unico_de_siempre(self):
        data = datos('Virtual', destino='', mentions=menciones(OBJETIVO, 'maestrías'))
        options, pending = opciones_candidatas(data, '', 3, CATALOGO)
        self.assertEqual(options, [])
        self.assertEqual(pending[-1]['campo'], 'destino')
        # Regresión: un único nivel, modalidad y destino generaban una opción antes y siguen generándola.
        legacy = datos('Virtual', niveles=['maestría'])
        options, pending = opciones_candidatas(legacy, '', 3, CATALOGO)
        self.assertEqual([(o['nivel'], o['modalidad'], o['destino_original']) for o in options], [('maestria', 'virtual', 'Ecuador')])
        self.assertEqual(pending, [])
        self.assertEqual(opciones_candidatas(datos('Virtual', niveles=[]), '', 3, CATALOGO), ([], []))
        self.assertEqual(opciones_candidatas({}, '', 3, CATALOGO), ([], []))
