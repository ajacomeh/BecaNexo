"""Lectura de las bases en PDF y su uso en el llenado automático. Sin red; base aislada.

Los PDF reales se leen (solo lectura) desde la copia del respaldo indicada en BECANEXO_RESPALDO_DOCUMENTOS
o, por defecto, desde D:\\Respaldos_BecaNexo\\becanexo_pre_captura_16_20261120T143538Z_b5240bcd\\documentos.
Si no está disponible, esas pruebas se omiten.
"""
import hashlib
import os
import shutil
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import skipUnless

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from convocatorias.models import Convocatoria, Institucion
from perfiles.models import Pais
from .bases_pdf import clave, obligaciones_de_bases, requisitos_de_bases
from .evidencia_pdf import _parrafos, leer_evidencia_pdf
from .llenado import completar_borrador, entidad_oferente
from .storage import key_for
from .test_evidencia_pdf import pdf_pages

RESPALDO = Path(os.environ.get('BECANEXO_RESPALDO_DOCUMENTOS',
                               r'D:\Respaldos_BecaNexo\becanexo_pre_captura_16_20261120T143538Z_b5240bcd\documentos'))
# Bases conservadas de las fichas reales (documento → SHA-256).
HIDROCARBUROS = (16, '78e686b3fe65afc326f41cb2da14b26943debc3775f173c4606eca8f43664de8')
JOVENES = (4, 'f1f52296aa6a5896d02aba2dd731ce49ec04415efe011578af68daea775ec2c3')
TALENTO_JOVEN = (14, '0aa17fa9013edce78371abaeb0e5a51156a1eaa0ff89ddd36d635566242d8172')
DISPONIBLE = all((RESPALDO / sha[:2] / f'{sha}.bin').exists() for _id, sha in (HIDROCARBUROS, JOVENES, TALENTO_JOVEN))


def leer_real(documento_id, sha):
    """Copia el PDF del respaldo a un almacén temporal y lo lee con los límites de evidencia_pdf."""
    with TemporaryDirectory() as folder:
        key = key_for(sha)
        destino = Path(folder) / key
        destino.parent.mkdir(parents=True)
        shutil.copyfile(RESPALDO / sha[:2] / f'{sha}.bin', destino)
        document = SimpleNamespace(pk=documento_id, mime='application/pdf', sha256=sha,
                                   tamano_bytes=destino.stat().st_size, clave_almacenamiento=key)
        relation = SimpleNamespace(documento=document, documento_id=documento_id, url_normalizada=f'https://siau.example/{documento_id}.pdf')
        return leer_evidencia_pdf(relation, 900, root=folder)


def pagina(texto, numero=1):
    return {'pagina': numero, 'estado': 'texto', 'texto': texto}


class ParrafosTests(SimpleTestCase):
    def test_une_lineas_cortadas_y_palabras_partidas_por_guion(self):
        parrafos = _parrafos([pagina('A. OBJETIVO\nEl programa, impulsado por el\nMinisterio de Educación, Deporte y Cultura, concede\n'
                                     'becas para la postu-\nlación de jóvenes.\n\nOtra frase distinta.')])
        textos = [p['texto'] for p in parrafos if not p['encabezado']]
        self.assertEqual(textos[0], 'El programa, impulsado por el Ministerio de Educación, Deporte y Cultura, concede becas '
                                    'para la postulación de jóvenes.')
        self.assertEqual(textos[1], 'Otra frase distinta.')
        self.assertTrue(all(p['seccion_bases'] == 'objeto' for p in parrafos))

    def test_reconoce_secciones_por_encabezado_y_elementos_numerados(self):
        parrafos = _parrafos([pagina('D. FINANCIAMIENTO Y RUBRO DE COBERTURA:\nSe cubre USD 500.\n'
                                     'E. REQUISITOS PARA LA POSTULACIÓN\n1. Ser persona natural en goce de\nderechos.\n2. No tener deudas.\n'
                                     'J. OBLIGACIONES DE LA PERSONA BENEFICIARIA:\na) Durante los estudios deberá:\n1. Destinar los recursos.'),
                               pagina('2. Aprobar el programa.\nK. CRONOGRAMA\nCierre el 30 de junio.', 2)])
        secciones = [(p['seccion_bases'], p['texto']) for p in parrafos if not p['encabezado']]
        self.assertEqual(secciones, [
            ('financiamiento', 'Se cubre USD 500.'), ('requisitos', '1. Ser persona natural en goce de derechos.'),
            ('requisitos', '2. No tener deudas.'), ('obligaciones', 'a) Durante los estudios deberá:'),
            ('obligaciones', '1. Destinar los recursos.'), ('obligaciones', '2. Aprobar el programa.'),
            ('cronograma', 'Cierre el 30 de junio.')])
        self.assertTrue(all(p['elemento'] for p in parrafos if p['texto'][:2] in ('1.', '2.', 'a)')))

    def test_el_limite_de_fragmentos_cuenta_parrafos_y_no_lineas(self):
        # Doscientas líneas de una misma frase forman un solo párrafo y un solo fragmento.
        lineas = ['Presentar la solicitud firmada'] + ['y la copia del documento de identidad'] * 199 + ['en la oficina.']
        with TemporaryDirectory() as folder:
            content = pdf_pages(lineas[:30])
            digest = hashlib.sha256(content).hexdigest()
            key = key_for(digest)
            path = Path(folder) / key
            path.parent.mkdir(parents=True)
            path.write_bytes(content)
            document = SimpleNamespace(pk=3, mime='application/pdf', sha256=digest, tamano_bytes=len(content), clave_almacenamiento=key)
            result = leer_evidencia_pdf(SimpleNamespace(documento=document, documento_id=3, url_normalizada='https://x.ec/b.pdf'), 1, root=folder)
        self.assertEqual(len(result['fragmentos']), 1)
        self.assertFalse(result['fragmentos_truncados'])
        self.assertTrue(result['fragmentos'][0]['texto_original'].startswith('Presentar la solicitud firmada y la copia'))


@skipUnless(DISPONIBLE, 'Copia del respaldo con los PDF reales no disponible.')
class BasesRealesTests(SimpleTestCase):
    def test_hidrocarburos_reconstruye_el_impulsor_requisitos_y_obligaciones_con_pagina(self):
        resultado = leer_real(*HIDROCARBUROS)
        self.assertEqual(resultado['estado'], 'extraido')
        self.assertFalse(any(p.get('texto_recortado') for p in resultado['paginas']), 'las páginas ya no se recortan')
        impulsor = next(p for p in resultado['parrafos'] if 'impulsado por el Ministerio de Educación, Deporte y Cultura' in p['texto'])
        self.assertEqual(impulsor['pagina'], 1)
        requisitos = requisitos_de_bases([resultado], 900)
        textos = [r['texto_original'] for r in requisitos]
        self.assertIn('Persona natural en goce de derechos de participación ciudadana en el Ecuador.', textos)
        self.assertTrue(all(r['procedencia']['documento_id'] == 16 and r['procedencia']['pagina'] for r in requisitos))
        # La documentación opcional del baremo no se toma como requisito.
        self.assertFalse(any('Récord académico' in t for t in textos))
        obligaciones = obligaciones_de_bases([resultado])
        self.assertEqual((obligaciones['documento_id'], obligaciones['pagina']), (16, 10))
        self.assertIn('1. Destinar los recursos al objeto de la beca recibida.', obligaciones['texto'])


@skipUnless(DISPONIBLE, 'Copia del respaldo con los PDF reales no disponible.')
class EntidadEnBasesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        cls.minedec = Institucion.objects.create(nombre='Ministerio de Educación, Deporte y Cultura del Ecuador (MINEDEC)',
                                                 sector='publico', pais=cls.ec)
        call_command('cargar_catalogos_convocatorias', verbosity=0)

    def datos(self, resultado):
        from .bases_pdf import fragmentos_para_entidad
        return {'titulo': {'texto_original': 'PROGRAMA DE BECAS NACIONALES'}, 'evidencia_pdf': fragmentos_para_entidad([resultado])}

    def test_asigna_la_entidad_que_las_bases_nombran_como_impulsora_con_fragmento_y_pagina(self):
        entidad = entidad_oferente(self.datos(leer_real(*HIDROCARBUROS)), '', 50)
        self.assertEqual(entidad['accion'], 'asignar')
        self.assertEqual(entidad['institucion'].pk, self.minedec.pk)
        self.assertEqual((entidad['documento_id'], entidad['pagina'], entidad['seccion']), (16, 1, 'Bases en PDF'))
        self.assertIn('impulsado por el Ministerio de Educación, Deporte y Cultura', entidad['literal'])

    def test_las_bases_que_nombran_al_ministerio_como_quien_firma_el_contrato_y_emite_la_beca_asignan_con_fragmento_y_pagina(self):
        for real, documento in ((JOVENES, 4), (TALENTO_JOVEN, 14)):
            with self.subTest(documento=documento):
                entidad = entidad_oferente(self.datos(leer_real(*real)), '', 50)
                self.assertEqual(entidad['accion'], 'asignar')
                self.assertEqual(entidad['institucion'].pk, self.minedec.pk)
                self.assertEqual(entidad['documento_id'], documento)
                self.assertIsInstance(entidad['pagina'], int)
                self.assertEqual(entidad['seccion'], 'Bases en PDF · Suscripción del contrato y su procedimiento')
                self.assertIn('suscribir con', entidad['literal'])
                self.assertIn('Minedec', entidad['literal'])
                self.assertIn('el contrato de financiamiento', entidad['literal'])

    def test_las_menciones_en_verificaciones_requisitos_o_seguimiento_de_las_bases_reales_no_asignan(self):
        # Solo quedan los párrafos de esas secciones: el Minedec aparece, pero ninguno acredita su papel de oferente.
        resultado = leer_real(*JOVENES)
        resultado['parrafos'] = [p for p in resultado['parrafos'] if p['seccion_bases'] in
                                 ('requisitos', 'obligaciones', 'seguimiento', 'sanciones', 'informacion', 'documentos')]
        self.assertTrue(any('Minedec' in p['texto'] or 'MINEDEC' in p['texto'] for p in resultado['parrafos']))
        entidad = entidad_oferente(self.datos(resultado), '', 50)
        self.assertIsNone(entidad['accion'])
        self.assertIsNone(entidad.get('institucion'))

    def test_el_llenado_completa_obligaciones_y_requisitos_de_las_bases_sin_duplicar_los_de_la_ficha(self):
        bases = [leer_real(*HIDROCARBUROS)]
        offer = Convocatoria.objects.create(titulo='Simulación', institucion=self.minedec, clave_deduplicacion=uuid.uuid4().hex * 2)
        ficha = 'Ser persona natural en ejercicio de sus derechos de participación en el Ecuador.\nNo constar como persona beneficiaria incumplida de crédito educativo.'
        evidencia = {'version_id': 900, 'datos': {'requisitos': {'texto_original': ficha}}, 'texto': '', 'documento_id': 50,
                     'url_ficha': 'https://siau.senescyt.gob.ec/hidrocarburos/', 'bases': bases}
        registro = {}
        completar_borrador(offer, evidencia, registro)
        offer.refresh_from_db()
        self.assertIn('1. Destinar los recursos al objeto de la beca recibida.', offer.obligaciones_beneficiario)
        campo = next(c for c in registro['campos'] if c['campo'] == 'obligaciones_beneficiario')
        self.assertEqual((campo['documento_id'], campo['pagina'], campo['seccion']), (16, 10, 'Bases en PDF · Obligaciones'))
        textos = list(offer.requisitos.values_list('texto_original', flat=True))
        # El requisito de crédito educativo está en la ficha y en las bases: una sola vez.
        self.assertEqual(sum(clave(t) == clave('No constar como persona beneficiaria incumplida de crédito educativo.') for t in textos), 1)
        # La misma condición redactada distinto en las bases («en goce de derechos…») tampoco se duplica.
        self.assertNotIn('Persona natural en goce de derechos de participación ciudadana en el Ecuador.', textos)
        de_bases = [r for r in registro['registros'] if r['modelo'] == 'requisitos' and r.get('pagina')]
        self.assertTrue(de_bases)
        self.assertTrue(all(r['documento_id'] == 16 and r['seccion'] == 'Bases en PDF · Requisitos' for r in de_bases))
        self.assertFalse(offer.requisitos.filter(validado=True).exists())

    def test_sin_bases_el_llenado_es_el_de_siempre(self):
        offer = Convocatoria.objects.create(titulo='Simulación', institucion=self.minedec, clave_deduplicacion=uuid.uuid4().hex * 2)
        evidencia = {'version_id': 901, 'datos': {'requisitos': {'texto_original': 'No constar como persona beneficiaria incumplida de crédito educativo.'}},
                     'texto': '', 'documento_id': 50, 'url_ficha': 'https://siau.senescyt.gob.ec/x/', 'bases': []}
        registro = {}
        completar_borrador(offer, evidencia, registro)
        self.assertFalse(any(r.get('pagina') for r in registro['registros']))
        self.assertFalse(any(c['campo'] == 'obligaciones_beneficiario' for c in registro['campos']))


class ReglaDeAdjudicacionTests(TestCase):
    """Textos sintéticos: la regla de adjudicación acepta secciones concretas y rechaza lo demás."""

    @classmethod
    def setUpTestData(cls):
        cls.ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        cls.minedec = Institucion.objects.create(nombre='Ministerio de Educación, Deporte y Cultura del Ecuador (MINEDEC)', sector='publico', pais=cls.ec)
        cls.otra = Institucion.objects.create(nombre='Secretaría Nacional de Becas', sector='publico', pais=cls.ec)

    def pdf(self, *fragmentos):
        return {'titulo': {'texto_original': 'PROGRAMA DE BECAS NACIONALES'}, 'evidencia_pdf': {'documentos': [{'documento_id': 9, 'fragmentos': [
            {'texto_original': texto, 'seccion_bases': seccion, 'titulo_seccion': titulo, 'procedencia': {'documento_id': 9, 'pagina': pagina}}
            for texto, seccion, titulo, pagina in fragmentos]}]}}

    FIRMA = ('Deberán suscribir con la Subsecretaría de Educación del Distrito Metropolitano de Quito y las coordinaciones zonales del '
             'Minedec, que corresponda, el contrato de financiamiento.')

    def test_la_entidad_que_firma_el_contrato_adjudica_o_emite_la_beca_se_asigna_con_procedencia(self):
        casos = {
            'firma': (self.FIRMA, 'contrato', 'SUSCRIPCIÓN DEL CONTRATO Y SU PROCEDIMIENTO'),
            'emite': ('A partir de dicha suscripción, la persona adjudicataria se convierte en persona becaria de la beca del Minedec.',
                      'contrato', 'SUSCRIPCIÓN DEL CONTRATO Y SU PROCEDIMIENTO'),
            'adjudica': ('El Ministerio de Educación, Deporte y Cultura adjudicará las becas a las personas seleccionadas.',
                         'adjudicacion', 'PROCESO DE OTORGAMIENTO DE LA BECA'),
        }
        for nombre, (texto, seccion, titulo) in casos.items():
            with self.subTest(nombre):
                entidad = entidad_oferente(self.pdf((texto, seccion, titulo, 4)), '', 50)
                self.assertEqual((entidad['accion'], entidad['institucion'].pk), ('asignar', self.minedec.pk))
                self.assertEqual((entidad['documento_id'], entidad['pagina']), (9, 4))
                self.assertEqual(entidad['seccion'], f'Bases en PDF · {titulo.capitalize()}')
                self.assertEqual(entidad['literal'], texto)

    def test_una_mencion_en_requisitos_prohibiciones_verificaciones_o_seguimiento_no_asigna(self):
        sin_papel = [
            ('No mantener la calidad vigente de persona becaria de la beca del Minedec.', 'requisitos', 'REQUISITOS PARA LA POSTULACIÓN'),
            ('Se verificará en la página de servicios del Minedec que la persona no tenga una beca vigente.', 'requisitos', 'REQUISITOS PARA LA POSTULACIÓN'),
            ('Remitir al Minedec el certificado de notas, a través del sistema, en un plazo de tres meses.', 'obligaciones', 'OBLIGACIONES DE LA PERSONA BENEFICIARIA'),
            ('El seguimiento estará a cargo del Minedec, según corresponda.', 'seguimiento', 'SEGUIMIENTO Y CONTROL'),
            ('Las bases estarán a disposición en la página web del Minedec.', 'informacion', 'INFORMACIÓN ADICIONAL'),
            # En la sección correcta, pero sin el papel: solo verifica o recibe documentos.
            ('El Minedec se reserva el derecho de verificar la autenticidad de los datos proporcionados.', 'adjudicacion', 'PROCESO DE OTORGAMIENTO DE LA BECA'),
            ('La Dirección del Minedec revisará las postulaciones para verificar que cumplan con los requisitos.', 'adjudicacion', 'PROCESO DE OTORGAMIENTO DE LA BECA'),
            ('Las coordinaciones zonales del Minedec solicitarán a las personas adjudicatarias los documentos.', 'contrato', 'ELABORACIÓN DEL CONTRATO DE FINANCIAMIENTO'),
            # Un papel explícito escrito dentro de una sección sin valor de oferente tampoco cuenta.
            ('No haber desistido de una beca otorgada por el Ministerio de Educación, Deporte y Cultura.', 'requisitos', 'REQUISITOS PARA LA POSTULACIÓN'),
        ]
        for texto, seccion, titulo in sin_papel:
            with self.subTest(texto=texto[:60]):
                entidad = entidad_oferente(self.pdf((texto, seccion, titulo, 3)), '', 50)
                self.assertIsNone(entidad['accion'])

    def test_con_una_entidad_extranjera_como_oferente_no_se_asigna_por_adjudicar(self):
        extranjera = ('Las becas son otorgadas por la Universidad de Zaragoza para estudios en España.', 'objeto', 'OBJETIVO', 1)
        entidad = entidad_oferente(self.pdf(extranjera, (self.FIRMA, 'contrato', 'SUSCRIPCIÓN DEL CONTRATO', 5)), '', 50)
        self.assertIsNone(entidad['accion'])
        # También si la ficha es quien nombra a la extranjera.
        datos = self.pdf((self.FIRMA, 'contrato', 'SUSCRIPCIÓN DEL CONTRATO', 5))
        datos['descripcion'] = {'texto_original': 'Becas otorgadas por Universidad Nebrija para estudios de posgrado.'}
        self.assertIsNone(entidad_oferente(datos, '', 50)['accion'])
        # Sin ninguna extranjera, la misma frase sí asigna.
        self.assertEqual(entidad_oferente(self.pdf((self.FIRMA, 'contrato', 'SUSCRIPCIÓN DEL CONTRATO', 5)), '', 50)['accion'], 'asignar')

    def test_el_papel_explicito_se_mantiene_aunque_haya_una_extranjera(self):
        impulsa = ('El programa, impulsado por el Ministerio de Educación, Deporte y Cultura, concede becas.', 'objeto', 'OBJETIVO', 1)
        extranjera = ('Algunas plazas son otorgadas por la Universidad de Zaragoza.', 'objeto', 'OBJETIVO', 1)
        entidad = entidad_oferente(self.pdf(extranjera, impulsa), '', 50)
        self.assertEqual((entidad['accion'], entidad['institucion'].pk), ('asignar', self.minedec.pk))

    def test_con_dos_entidades_registradas_candidatas_no_se_asigna_ninguna(self):
        dos = ('Deberán suscribir con el Minedec y con la Secretaría Nacional de Becas el contrato de financiamiento.', 'contrato', 'SUSCRIPCIÓN DEL CONTRATO', 5)
        self.assertIsNone(entidad_oferente(self.pdf(dos), '', 50)['accion'])

    def test_no_crea_entidades_por_esta_via_y_respeta_lo_que_el_administrador_eligio_o_vacio(self):
        antes = Institucion.objects.count()
        sin_registrar = ('Deberán suscribir con la Universidad Tecnológica del Ecuador el contrato de financiamiento.', 'contrato', 'SUSCRIPCIÓN DEL CONTRATO', 5)
        self.assertIsNone(entidad_oferente(self.pdf(sin_registrar), '', 50)['accion'])
        self.assertEqual(Institucion.objects.count(), antes)
        # En el llenado: lo elegido no se pisa y lo vaciado no se reasigna (idempotente).
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        offer = Convocatoria.objects.create(titulo='Prueba', institucion=self.otra, clave_deduplicacion=uuid.uuid4().hex * 2)
        evidencia = {'version_id': 1, 'datos': self.pdf((self.FIRMA, 'contrato', 'SUSCRIPCIÓN DEL CONTRATO', 5)), 'texto': '',
                     'documento_id': 50, 'url_ficha': 'https://siau.senescyt.gob.ec/x/', 'bases': []}
        registro = {}
        completar_borrador(offer, evidencia, registro)
        offer.refresh_from_db()
        self.assertEqual(offer.institucion_id, self.otra.pk)
        offer.institucion = None
        offer.save(update_fields=['institucion'])
        completar_borrador(offer, evidencia, registro)
        offer.refresh_from_db()
        self.assertEqual(offer.institucion_id, self.minedec.pk)
        campo = next(c for c in registro['campos'] if c['campo'] == 'institucion')
        self.assertEqual((campo['documento_id'], campo['pagina'], campo['seccion']), (9, 5, 'Bases en PDF · Suscripción del contrato'))
        offer.institucion = None
        offer.save(update_fields=['institucion'])
        completar_borrador(offer, evidencia, registro)
        offer.refresh_from_db()
        self.assertIsNone(offer.institucion_id, 'lo que el administrador vació no se reasigna')
