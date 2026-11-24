"""Detalle de ejecución: resumen agrupado de incidencias, filtros y tamaño de página de 25.

Escribe solo en la base de pruebas aislada.
"""
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from . import tests as base
from .services import incident

ROOT = '/api/gestion/rastreo/'


class ResumenIncidenciasTests(TransactionTestCase):
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    run_fake = base.RastreoTests.run_fake

    def setUp(self):
        base.RastreoTests.setUp(self)
        self.run = self.run_fake(self.source())
        for _ in range(12):
            incident(self.run, 'BASE_NO_PERMITIDA', 'Enlace de bases fuera de lista cerrada.', severity='aviso')
        for _ in range(3):
            incident(self.run, 'RED', 'ConnectionError')
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.actor)

    def get(self, query=''):
        return self.client.get(f'{ROOT}ejecuciones/{self.run.pk}/incidencias/{query}')

    def test_resumen_agrupado_por_tipo_y_gravedad_con_contador(self):
        data = self.get().data
        resumen = {(g['codigo'], g['gravedad']): g['total'] for g in data['resumen']}
        self.assertEqual(resumen[('BASE_NO_PERMITIDA', 'aviso')], 12)
        self.assertGreaterEqual(resumen[('RED', 'error')], 3)
        self.assertEqual(sum(resumen.values()), data['count'])
        # Los errores aparecen antes que los avisos.
        gravedades = [g['gravedad'] for g in data['resumen']]
        self.assertEqual(gravedades, sorted(gravedades, key=lambda g: g != 'error'))
        self.assertEqual(data['page_size'], 25)
        self.assertLessEqual(len(data['results']), 25)
        for private in ('detalle', 'Enlace de bases', 'ConnectionError'):
            self.assertNotIn(private, str(data))

    def test_filtros_por_gravedad_y_codigo_no_cambian_el_resumen(self):
        completo = self.get().data['resumen']
        avisos = self.get('?gravedad=aviso').data
        self.assertTrue(all(i['gravedad'] == 'aviso' for i in avisos['results']))
        self.assertEqual(avisos['resumen'], completo)
        bases = self.get('?codigo=BASE_NO_PERMITIDA&page_size=5').data
        self.assertEqual((bases['count'], len(bases['results'])), (12, 5))
        self.assertEqual(self.get('?codigo=BASE_NO_PERMITIDA&gravedad=error').data['count'], 0)
        for query in ('?gravedad=grave', '?codigo=' + 'X' * 61, '?page_size=51', '?gravedad=aviso&gravedad=error', '?orden=id'):
            self.assertEqual(self.get(query).status_code, 400, query)

    def test_accesos_paginan_de_25_por_defecto_y_los_contadores_por_gravedad(self):
        accesos = self.client.get(f'{ROOT}ejecuciones/{self.run.pk}/accesos/').data
        self.assertEqual(accesos['page_size'], 25)
        detalle = self.client.get(f'{ROOT}ejecuciones/{self.run.pk}/').data
        self.assertGreaterEqual(detalle['incidencias_error'], 3)
        self.assertGreaterEqual(detalle['incidencias_aviso'], 12)
        self.assertEqual(detalle['incidencias_error'] + detalle['incidencias_aviso'], self.get().data['count'])

    def test_solo_las_incidencias_editoriales_traen_su_detalle(self):
        from .api import CODIGOS_EDITORIALES
        resumen_antes = self.get().data['resumen']
        motivos = {'BORRADOR_REVISION_PENDIENTE': 'Participación de ciudadanos ecuatorianos por confirmar en las bases.',
                   'CANDIDATO_PENDIENTE': 'Revisión editorial pendiente: oferente por confirmar.',
                   'CANDIDATO_FUERA_ALCANCE': 'Descartada: la ficha excluye expresamente a ciudadanos ecuatorianos.'}
        self.assertEqual(set(motivos), set(CODIGOS_EDITORIALES))
        for codigo, motivo in motivos.items():
            incident(self.run, codigo, motivo, severity='aviso')
        incident(self.run, 'ALMACENAMIENTO', 'C:\ruta\privada\archivo.bin: permiso denegado')
        incident(self.run, 'HTTP', 'HTTP 503; detalle interno del servidor')
        for codigo, motivo in motivos.items():
            filas = self.get(f'?codigo={codigo}').data['results']
            self.assertEqual([fila['detalle'] for fila in filas], [motivo])
        for codigo in ('ALMACENAMIENTO', 'HTTP', 'RED', 'BASE_NO_PERMITIDA'):
            for fila in self.get(f'?codigo={codigo}&page_size=50').data['results']:
                self.assertNotIn('detalle', fila, codigo)
        texto = str(self.get('?page_size=50').data) + str(self.get('?page=2&page_size=50').data)
        for interno in ('ruta', 'privada', 'detalle interno', 'ConnectionError', 'Enlace de bases'):
            self.assertNotIn(interno, texto)
        # El resumen agrupado por tipo y gravedad mantiene su forma y solo suma los nuevos grupos.
        resumen = self.get().data['resumen']
        self.assertTrue(all(set(g) == {'codigo', 'gravedad', 'total'} for g in resumen))
        anteriores = {(g['codigo'], g['gravedad']): g['total'] for g in resumen_antes}
        actuales = {(g['codigo'], g['gravedad']): g['total'] for g in resumen}
        self.assertTrue(all(actuales.get(clave, 0) >= total for clave, total in anteriores.items()))
        self.assertEqual(actuales[('BORRADOR_REVISION_PENDIENTE', 'aviso')], 1)
        self.assertEqual(actuales[('ALMACENAMIENTO', 'error')], 1)
