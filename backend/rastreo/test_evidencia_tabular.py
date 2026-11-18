"""Muestras HTML sintéticas: ninguna consulta externa ni escritura en becanexo_db."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from .auto_borradores import editable_candidates
from .evidencia_tabular import extraer_tablas


URL = 'https://institucion.edu.ec/becas/2026/'


class EvidenciaTabularTests(SimpleTestCase):
    def parse(self, html):
        return extraer_tablas(html.encode(), URL, version_id=12, documento_id=8)

    def test_istcge_separa_cronograma_categorias_y_renovacion(self):
        result = self.parse('''<h2>Cronograma de becas 2026</h2><table>
          <tr><th>Proceso</th><th>Fecha</th></tr>
          <tr><td>Cierre programa general</td><td>22/11/2026</td></tr>
          <tr><td>Política de Cuotas, proceso separado</td><td>12/12/2026</td></tr></table>
          <h2>Beca socioeconómica</h2><table><caption>Requisitos específicos</caption>
          <tr><td>Presentar ficha socioeconómica</td></tr>
          <tr><td>Renovación: mantener promedio exigido</td></tr></table>
          <a href="/anexos/solicitud.pdf">Anexo de solicitud</a>''')
        timeline, category = result['tablas']
        self.assertEqual([row['fecha_sugerida'] for row in timeline['filas'][1:]], ['2026-11-22', '2026-12-12'])
        self.assertEqual(category['encabezado'], 'Beca socioeconómica')
        self.assertEqual(category['filas'][1]['condicion'], 'renovacion')
        self.assertTrue(all(row['estado'] == 'pendiente_revision' for row in category['filas']))
        self.assertEqual(result['enlaces_documentales'][0]['url'], 'https://institucion.edu.ec/anexos/solicitud.pdf')

    def test_puce_alternativas_y_cobertura_variable_no_son_reglas_validadas(self):
        result = self.parse('''<h2>Requisitos de Solidaridad</h2><table><tr><td>Una de las siguientes alternativas:</td>
          <td>Discapacidad o vulnerabilidad socioeconómica</td></tr></table>
          <h2>Cobertura</h2><table><tr><td>Del 75% al 100% según evaluación</td></tr></table>''')
        self.assertEqual(result['tablas'][0]['filas'][0]['condicion'], 'alternativa_por_revisar')
        benefit = result['tablas'][1]['filas'][0]
        self.assertEqual(benefit['porcentajes_literales'], ['75%', '100%'])
        self.assertIsNone(benefit['porcentaje_fijo'])

    def test_occitec_archivo_html_precarga_evidencia_sin_publicar(self):
        raw = b'''<h2>Requisitos generales</h2><table><tr><td>Ciudadanos ecuatorianos</td></tr></table>
          <a href="https://institucion.edu.ec/bases.pdf">Bases oficiales</a>
          <a href="javascript:alert(1)">Formulario</a>
          <a href="https://[invalido">Anexo roto</a>'''
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'ficha.html'
            path.write_bytes(raw)
            document = SimpleNamespace(clave_almacenamiento='ficha.html', sha256=hashlib.sha256(raw).hexdigest(),
                                       tamano_bytes=len(raw))
            relation = SimpleNamespace(documento_id=8, documento=document, url_normalizada=URL)
            documents = MagicMock()
            documents.filter.return_value.select_related.return_value.first.return_value = relation
            version = SimpleNamespace(pk=12, documentos=documents, datos_extraidos={
                'url': URL, 'requisitos': {'texto_original': ''}, 'estudios': {}})
            with patch('rastreo.storage.root_path', return_value=Path(folder)):
                suggestions = editable_candidates(version)
        evidence = suggestions['otros_campos']['evidencia_tabular']
        self.assertEqual(evidence['estado'], 'extraida')
        self.assertEqual(evidence['tablas'][0]['procedencia']['documento_id'], 8)
        self.assertEqual(evidence['tablas'][0]['filas'][0]['estado'], 'pendiente_revision')
        self.assertEqual(len(evidence['enlaces_documentales']), 1)
        self.assertEqual(suggestions['requisitos'], [])
