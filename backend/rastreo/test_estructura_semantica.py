"""Casos sintéticos de interpretación sin escritura en bases de negocio."""
from django.test import SimpleTestCase

from convocatorias.semantica import ModeloNoDisponible, similitud, vector
from .estructura_semantica import PROTOTIPOS, _semantica, candidatos_adicionales, interpretar_requisitos


def candidatos(text):
    return interpretar_requisitos(text, version_id=17, url='https://fuente.edu.ec/ficha', documento_id=8)


class EstructuraSemanticaTests(SimpleTestCase):
    def test_requisitos_explicitos_y_valores_sin_inventar_escala(self):
        cases = [
            ('Ser ciudadano/a ecuatoriano/a', 'NACIONALIDAD', {'codigos_pais': ['EC']}),
            ('Tener entre 18 y 30 años', 'EDAD', {'minimo': 18, 'maximo': 30}),
            ('Promedio mínimo de 8,5', 'PROMEDIO', {'minimo': 8.5}),
            ('Promedio mínimo de 8,5/10', 'PROMEDIO', {'minimo': 8.5, 'escala_min': 0, 'escala_max': 10}),
            ('Dominio del inglés B2', 'IDIOMA', {'codigo_idioma': 'en', 'nivel_minimo': 'B2'}),
            ('Contar con 2 años de experiencia profesional', 'EXPERIENCIA', {'meses_minimos': 24}),
            ('Disponibilidad a tiempo completo', 'DEDICACION', {'valores_admitidos': ['completa']}),
            ('Presentar copia de cédula', 'DOCUMENTO', {'documento': 'Presentar copia de cédula'}),
        ]
        for text, code, values in cases:
            with self.subTest(text=text):
                item = candidatos(text)[0]
                self.assertEqual(item['tipo_sugerido'], code)
                self.assertEqual(item['valor_sugerido'], values)
                self.assertFalse(item['validado'])
                self.assertEqual(item['procedencia']['documento_id'], 8)

    def test_divide_clausulas_con_verbos_y_conserva_ambiguas_o_negadas(self):
        rows = candidatos('Tener entre 18 y 30 años y acreditar dominio del inglés B2')
        self.assertEqual([row['tipo_sugerido'] for row in rows], ['EDAD', 'IDIOMA'])
        negated = candidatos('No tener nacionalidad ecuatoriana')[0]
        self.assertTrue(negated['negacion_literal'])
        self.assertEqual(negated['valor_sugerido'], {})
        self.assertEqual(negated['estado'], 'ambigua')
        unknown = candidatos('Presentar condiciones establecidas en las bases')[0]
        self.assertFalse(unknown['validado'])
        self.assertEqual(unknown['valor_sugerido'], {})

    def test_evidencia_siau_no_inventa_nacionalidad_documento_ni_titulo(self):
        rows = candidatos('CONDICIONES OBLIGATORIAS\nPersona natural en goce de derechos de participación ciudadana en el Ecuador.\n'
                          'Contar con un título académico previo para cursar una maestría; '
                          'cumplir con los requisitos generales establecidos en la convocatoria')
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['tipo_sugerido'], 'OTRO')
        self.assertEqual(rows[0]['metodo'], 'elegibilidad_por_verificar')
        self.assertEqual(rows[1]['valor_sugerido'], {})
        self.assertEqual(rows[2]['metodo'], 'referencia_externa')
        self.assertEqual(candidatos('Ser ciudadano/a ecuatoriano/a')[0]['valor_sugerido'], {'codigos_pais': ['EC']})
        self.assertEqual(candidatos('Ser Bachiller')[0]['valor_sugerido'],
                         {'nivel_minimo': 'bachillerato', 'estado_exigido': 'concluidos', 'titulo_obtenido': True})
        self.assertEqual(candidatos('Estar matriculada en una carrera de tercer nivel de grado.')[0]['valor_sugerido'],
                         {'niveles_admitidos': ['grado'], 'estado_exigido': 'en_curso', 'titulo_obtenido': False})

    def test_beneficio_y_vigencia_literal_sin_suponer_moneda(self):
        data = {'titulo': {'texto_original': 'Beca de excelencia', 'url': 'https://fuente.edu.ec/ficha'},
            'beneficio': {'texto_original': 'Cubre 25% de matrícula y USD 750 de manutención.',
                          'url': 'https://fuente.edu.ec/ficha'},
            'cierre': {'original': '25 de noviembre de 2026', 'fecha': '2026-11-25'},
            'enlaces_postulacion': [{'url': 'https://fuente.edu.ec/postular'}]}
        result = candidatos_adicionales(data, version_id=17, documento_id=8)
        self.assertIsNone(result['beneficios'][0]['porcentaje'])
        self.assertIsNone(result['beneficios'][0]['moneda'])
        self.assertEqual(result['fechas']['cierre']['fecha'], '2026-11-25')
        self.assertEqual(result['enlaces']['postulacion'][0]['url'], 'https://fuente.edu.ec/postular')
        self.assertEqual(candidatos_adicionales({'beneficio': {'texto_original': 'Cubre 25% de matrícula'}}, version_id=17)
                         ['beneficios'][0]['porcentaje'], 25)
        self.assertEqual(candidatos_adicionales({'beneficio': {'texto_original': '$750'}}, version_id=17)
                         ['beneficios'][0]['moneda'], None)
        mixed = candidatos_adicionales({'beneficio': {'texto_original': '100% de matrícula y USD 750 para manutención'}}, version_id=17)
        self.assertIsNone(mixed['beneficios'][0]['porcentaje'])
        once = candidatos_adicionales({'beneficio': {'texto_original': 'Por una sola vez USD 828.97 para manutención',
            'conceptos': ['manutención'], 'cantidades': [{'tipo': 'monto_mencionado', 'moneda': 'USD', 'valor_literal': '828.97'}]}}, version_id=17)
        self.assertEqual(once['beneficios'][0]['monto'], 828.97)
        self.assertEqual(once['beneficios'][0]['concepto_sugerido'], 'manutención')
        cap = candidatos_adicionales({'beneficio': {'texto_original': 'Matrícula y aranceles: 100% hasta USD 10.500,00',
            'conceptos': ['matrícula', 'aranceles'], 'cantidades': [{'tipo': 'tope', 'moneda': 'USD',
                'original': 'USD 10.500,00', 'valor_literal': '10.500,00'}]}}, version_id=17)
        self.assertEqual(cap['beneficios'][0]['porcentaje'], 100)
        self.assertEqual(cap['beneficios'][0]['tope_monto'], 10500)
        self.assertIsNone(cap['beneficios'][0]['monto'])
        thousands = candidatos_adicionales({'beneficio': {'texto_original': 'Hasta USD 10.500',
            'cantidades': [{'tipo': 'tope', 'moneda': 'USD', 'original': 'USD 10.500', 'valor_literal': '10.500'}]}}, version_id=17)
        self.assertEqual(thousands['beneficios'][0]['tope_monto'], 10500)
        partial = candidatos_adicionales({'descripcion': {'texto_original': 'Se otorgan becas parciales para manutención',
            'url': 'https://fuente.edu.ec/ficha'}}, version_id=17, documento_id=8)
        self.assertEqual(partial['cobertura_tipo_sugerida'], 'parcial')
        self.assertEqual(partial['cobertura_procedencia']['campo'], 'descripcion')

    def test_onnx_real_medido_como_clasificador_auxiliar(self):
        cases = [
            ('NACIONALIDAD', 'Ser ciudadano/a ecuatoriano/a'), ('EDAD', 'Tener entre 18 y 30 años'),
            ('PROMEDIO', 'Promedio mínimo de 8,5'), ('IDIOMA', 'Dominio del inglés B2'),
            ('FORMACION', 'Haber concluido estudios de tercer nivel'),
            ('TITULO_AREA', 'Título universitario en ingeniería'),
            ('EXPERIENCIA', 'Contar con dos años de experiencia laboral'),
            ('DEDICACION', 'Disponibilidad a tiempo completo'),
            ('TRASLADO', 'Disponibilidad para trasladarse a España'),
            ('RESIDENCIA', 'Residir en la provincia de Pichincha'),
            ('DOCUMENTO', 'Presentar copia de cédula vigente'),
        ]
        try:
            prototypes = {code: vector(text) for code, text in PROTOTIPOS.items()}
            correct = sum(max(prototypes, key=lambda code: similitud(vector(text), prototypes[code])) == expected
                          for expected, text in cases)
        except ModeloNoDisponible:
            self.fail('El ONNX local no está disponible para medir la clasificación solicitada.')
        print(f'ONNX requisitos: {correct}/{len(cases)} categorías top-1 en frases sintéticas')
        self.assertGreaterEqual(correct, 8)
        variants = [
            ('NACIONALIDAD', 'Pasaporte ecuatoriano vigente'),
            ('EDAD', 'No superar los treinta años al cierre'),
            ('PROMEDIO', 'Calificaciones superiores a nueve sobre diez'),
            ('IDIOMA', 'Capacidad comunicativa B2 en lengua inglesa'),
            ('FORMACION', 'Haber egresado de licenciatura'),
            ('TITULO_AREA', 'Ingeniería o arquitectura como profesión previa'),
            ('EXPERIENCIA', 'Trayectoria de doce meses en investigación'),
            ('DEDICACION', 'Jornada exclusiva durante los estudios'),
            ('TRASLADO', 'Disposición a vivir en otro país'),
            ('RESIDENCIA', 'Domicilio habitual en Quito'),
            ('DOCUMENTO', 'Adjuntar copia de identificación'),
        ]
        varied = sum(max(prototypes, key=lambda code: similitud(vector(text), prototypes[code])) == expected
                     for expected, text in variants)
        print(f'ONNX requisitos: {varied}/{len(variants)} categorías top-1 con redacción variable')
        accepted = [(expected, proposed) for expected, text in variants
                    if (proposed := _semantica(text)[0])]
        print(f'ONNX sugerencias con umbral: {sum(expected == predicted for expected, predicted in accepted)}/{len(accepted)}')
        self.assertTrue(all(expected == predicted for expected, predicted in accepted))
