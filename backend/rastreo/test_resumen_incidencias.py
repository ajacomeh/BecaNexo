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
