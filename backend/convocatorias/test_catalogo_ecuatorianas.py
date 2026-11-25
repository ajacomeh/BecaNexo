"""Catálogo público: por defecto solo convocatorias con entidad oferente ecuatoriana; las demás con un parámetro.

Escribe solo en la base de pruebas aislada.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from . import models as m
from . import tests as base

ROOT = '/api/becas/'


class CatalogoEcuatorianasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        base.ConvocatoriasTests.setUpTestData.__func__(cls)
        ahora = timezone.now()
        cls.ofertas = {}

        def crear(clave, institucion, **fechas):
            cls.ofertas[clave] = m.Convocatoria.objects.create(
                institucion=institucion, titulo=f'Oferta {clave}', descripcion='Datos sintéticos', url_oficial='https://example.org/t',
                clave_deduplicacion=clave.ljust(64, 'x'), revision='validada', activa=True, **fechas)
        for estado, fechas in {'vigente': {'cierre': ahora + timedelta(days=20)},
                               'proxima': {'apertura': ahora + timedelta(days=5), 'cierre': ahora + timedelta(days=40)},
                               'cerrada': {'cierre': ahora - timedelta(days=3)}}.items():
            crear(f'ec-{estado}', cls.institution, **fechas)
            crear(f'otra-{estado}', None, **fechas)  # sin entidad ecuatoriana (oferente no ecuatoriano o por confirmar)

    def setUp(self):
        self.client = APIClient()

    def ids(self, query=''):
        data = self.client.get(ROOT + query).data
        return data['count'], {r['id'] for r in data['results']}

    def esperado(self, *claves):
        return {self.ofertas[c].pk for c in claves}

    def test_por_defecto_excluye_las_que_no_tienen_entidad_ecuatoriana_en_cada_pestana(self):
        casos = {'': ['vigente'], '?estado=proxima': ['proxima'], '?estado=cerrada': ['cerrada'],
                 '?estado=todas': ['vigente', 'proxima', 'cerrada']}
        for query, estados in casos.items():
            with self.subTest(query or 'vigentes'):
                self.assertEqual(self.ids(query), (len(estados), self.esperado(*[f'ec-{e}' for e in estados])))
                self.assertEqual(self.ids(query + ('&' if query else '?') + 'incluir_no_ecuatorianas=false')[1],
                                 self.esperado(*[f'ec-{e}' for e in estados]))

    def test_con_el_parametro_incluye_todas(self):
        for valor in ('true', '1', 'TRUE'):
            count, ids = self.ids(f'?estado=todas&incluir_no_ecuatorianas={valor}')
            self.assertEqual(count, 6)
            self.assertEqual(ids, set(o.pk for o in self.ofertas.values()))
        self.assertEqual(self.ids('?incluir_no_ecuatorianas=1')[1], self.esperado('ec-vigente', 'otra-vigente'))
        for invalido in ('si', '2', ''):
            self.assertEqual(self.client.get(ROOT + f'?incluir_no_ecuatorianas={invalido}').status_code, 400)

    def test_contador_y_paginacion_siguen_al_filtro(self):
        por_defecto = self.client.get(ROOT + '?estado=todas&page_size=2').data
        self.assertEqual((por_defecto['count'], len(por_defecto['results'])), (3, 2))
        segunda = self.client.get(ROOT + '?estado=todas&page_size=2&page=2').data
        self.assertEqual(len(segunda['results']), 1)
        self.assertTrue(all(r['institucion'] for r in por_defecto['results'] + segunda['results']))
        todas = self.client.get(ROOT + '?estado=todas&page_size=2&page=3&incluir_no_ecuatorianas=true').data
        self.assertEqual((todas['count'], len(todas['results'])), (6, 2))

    def test_el_detalle_por_enlace_directo_sigue_accesible(self):
        otra = self.ofertas['otra-vigente']
        respuesta = self.client.get(f'{ROOT}{otra.pk}/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(respuesta.data['institucion'])

    def test_administracion_ve_todas(self):
        self.client.force_login(self.admin)
        data = self.client.get('/api/gestion/convocatorias/?estado=todas').data
        self.assertEqual(data['count'], 6)
        self.assertEqual(self.client.get('/api/gestion/convocatorias/?incluir_no_ecuatorianas=true').status_code, 400)

    def test_recomendaciones_aplican_el_mismo_criterio(self):
        self.student.rol = 'postulante'
        self.student.save(update_fields=['rol'])
        self.client.force_login(self.student)
        with patch('convocatorias.recomendaciones.evaluar_convocatoria', side_effect=lambda usuario, conv: {'opciones': []}) as evaluadas:
            self.client.get('/api/becas/recomendaciones/')
        self.assertEqual({c.args[1].pk for c in evaluadas.call_args_list}, self.esperado('ec-vigente'))
