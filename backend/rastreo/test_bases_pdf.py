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
DISPONIBLE = all((RESPALDO / sha[:2] / f'{sha}.bin').exists() for _id, sha in (HIDROCARBUROS, JOVENES))


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

    def test_sin_papel_explicito_en_las_bases_no_se_asigna_nada(self):
        # Las bases de «Jóvenes del Nuevo Ecuador» solo dicen «persona becaria de la beca del Minedec».
        entidad = entidad_oferente(self.datos(leer_real(*JOVENES)), '', 50)
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
