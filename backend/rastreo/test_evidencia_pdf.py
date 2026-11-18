"""PDF sintéticos, sin acceso a becanexo_db ni consultas a portales."""
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from .evidencia_pdf import leer_evidencia_pdf
from .auto_borradores import editable_candidates
from .storage import key_for


def pdf_pages(*pages):
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    font_ref = writer._add_object(font)
    for lines in pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font_ref})})
        if lines:
            content = '\n'.join(f'BT /F1 12 Tf 50 {700 - index * 20} Td ({line}) Tj ET'
                                for index, line in enumerate(lines))
            stream = DecodedStreamObject()
            stream.set_data(content.encode('ascii'))
            page[NameObject('/Contents')] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class EvidenciaPDFTests(SimpleTestCase):
    def read(self, content):
        digest = hashlib.sha256(content).hexdigest()
        key = key_for(digest)
        with TemporaryDirectory() as folder:
            path = Path(folder) / key
            path.parent.mkdir(parents=True)
            path.write_bytes(content)
            document = SimpleNamespace(pk=19, mime='application/pdf', sha256=digest,
                                       tamano_bytes=len(content), clave_almacenamiento=key)
            relation = SimpleNamespace(documento=document, documento_id=19,
                                       url_normalizada='https://institucion.edu.ec/bases.pdf')
            return leer_evidencia_pdf(relation, 7, root=folder)

    def test_programa_requisitos_fechas_y_procedencia_por_pagina(self):
        result = self.read(pdf_pages([
            'Programa de becas 2026', 'Requisitos generales', 'Presentar solicitud y cedula',
            'Cronograma', 'Cierre 22/11/2026', 'Postulacion en https://institucion.edu.ec/formulario',
        ], ['Beca deportiva', 'Requisitos especificos', 'Acreditar actividad deportiva']))
        self.assertEqual(result['estado'], 'extraido')
        self.assertEqual(result['total_paginas'], 2)
        rows = result['fragmentos']
        self.assertTrue(any(row['tipo'] == 'requisito' and row['procedencia']['pagina'] == 1 for row in rows))
        self.assertTrue(any(row['categoria'] == 'Beca deportiva' and row['procedencia']['pagina'] == 2 for row in rows))
        self.assertTrue(any(row['fecha_sugerida'] == '2026-11-22' for row in rows))
        self.assertTrue(all(row['procedencia']['documento_id'] == 19 and row['procedencia']['version_id'] == 7 for row in rows))
        self.assertTrue(all(row['estado'] == 'pendiente_revision' for row in rows))

    def test_categorias_alternativas_renovacion_y_cobertura_variable(self):
        result = self.read(pdf_pages([
            'Beca socioeconomica', 'Requisitos especificos', 'Una de las siguientes alternativas',
            'Acreditar discapacidad', 'Presentar certificado de vulnerabilidad economica', 'Renovacion',
            'Mantener promedio exigido', 'Beneficios', 'Cobertura del 75% al 100% segun evaluacion',
        ]))
        rows = result['fragmentos']
        self.assertEqual(sum(row['condicion'] == 'alternativa_por_revisar' for row in rows), 2)
        self.assertTrue(any(row['condicion'] == 'renovacion' for row in rows))
        coverage = next(row for row in rows if '75%' in row['texto_original'])
        self.assertEqual(coverage['porcentajes_literales'], ['75%', '100%'])
        self.assertIsNone(coverage['porcentaje_fijo'])

    def test_pdf_sin_texto_e_invalido_quedan_pendientes(self):
        self.assertEqual(self.read(pdf_pages([]))['estado'], 'sin_texto')
        self.assertEqual(self.read(b'%PDF-documento invalido')['estado'], 'invalido')

    def test_texto_con_acentos_no_depende_de_codificacion_de_consola(self):
        result = self.read(pdf_pages([r'Programa de investigaci\351n']))
        self.assertEqual(result['estado'], 'extraido')
        self.assertTrue(result['fragmentos'])

    def test_limite_de_paginas_no_extrae_mas_de_doce(self):
        result = self.read(pdf_pages(*([['Programa de becas']] * 13)))
        self.assertEqual(result['estado'], 'limite_paginas')
        self.assertEqual(result['total_paginas'], 13)
        self.assertEqual(len(result['paginas']), 12)

    def test_limite_de_fragmentos_se_informa(self):
        lines = [f'Presentar documento {index}' for index in range(75)]
        result = self.read(pdf_pages(lines, lines))
        self.assertEqual(len(result['fragmentos']), 120)
        self.assertTrue(result['fragmentos_truncados'])

    def test_editor_no_duplica_pdf_y_conserva_otro_si_uno_falla(self):
        good = pdf_pages(['Requisitos generales', 'Presentar solicitud'])
        bad = b'%PDF-documento invalido'
        with TemporaryDirectory() as folder:
            relations = []
            for index, content in enumerate((bad, good, good), start=1):
                digest = hashlib.sha256(content).hexdigest()
                key = key_for(digest)
                path = Path(folder) / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                document = SimpleNamespace(pk=index, mime='application/pdf', sha256=digest,
                                           tamano_bytes=len(content), clave_almacenamiento=key)
                relations.append(SimpleNamespace(documento=document, documento_id=index,
                    url_normalizada=f'https://institucion.edu.ec/bases-{index}.pdf'))
            documents = MagicMock()
            documents.filter.return_value.select_related.return_value.order_by.return_value.__getitem__.return_value = relations
            documents.filter.return_value.select_related.return_value.first.return_value = None
            version = SimpleNamespace(pk=7, documentos=documents,
                                      datos_extraidos={'requisitos': {'texto_original': ''}, 'estudios': {}})
            with patch('rastreo.evidencia_pdf.root_path', return_value=Path(folder)):
                result = editable_candidates(version)['otros_campos']['evidencia_pdf']['documentos']
        self.assertEqual(len(result), 2)
        self.assertEqual([row['estado'] for row in result], ['invalido', 'extraido'])
        self.assertEqual(len(result[1]['urls']), 2)
