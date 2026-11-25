"""Catálogo público: destino rápido (destino_ambito) y facetas del listado.

Escribe solo en la base de pruebas aislada.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from perfiles.models import Pais
from . import models as m
from . import tests as base

ROOT = '/api/becas/'


class CatalogoFacetasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        base.ConvocatoriasTests.setUpTestData.__func__(cls)
        cls.co, _ = Pais.objects.get_or_create(codigo='CO', defaults={'nombre': 'Colombia'})
        cierre = timezone.now() + timedelta(days=20)
        cls.ofertas = {}

        def crear(clave, opciones, institucion=cls.institution, **extra):
            c = m.Convocatoria.objects.create(
                institucion=institucion, titulo=f'Oferta {clave}', descripcion='Datos sintéticos', url_oficial='https://example.org/t',
                clave_deduplicacion=clave.ljust(64, 'x'), revision='validada', activa=True, cierre=extra.pop('cierre', cierre), **extra)
            for nivel, modalidad, paises, *programa in opciones:
                o = m.OpcionEstudio.objects.create(convocatoria=c, nivel=nivel, modalidad=modalidad, programa=(programa or [None])[0])
                for pais in paises: m.OpcionPais.objects.create(opcion_estudio=o, pais=pais)
            cls.ofertas[clave] = c
        # Nacional: grado presencial en Ecuador.
        crear('nacional', [('grado', 'presencial', [cls.ec])])
        # Exterior: maestría virtual en España.
        crear('exterior', [('maestria', 'virtual', [cls.es])])
        # Mixta: maestría presencial en Ecuador y grado virtual en España (atributos en opciones distintas).
        crear('mixta', [('maestria', 'presencial', [cls.ec]), ('grado', 'virtual', [cls.es], 'Ingeniería de software')])
        # Una opción con dos destinos, Ecuador y Colombia: cuenta para ambos ámbitos.
        crear('doble', [('doctorado', 'hibrida', [cls.ec, cls.co])])
        # Sin entidad ecuatoriana (solo con la casilla) y una cerrada (solo en Cerradas o Todas).
        crear('externa', [('grado', 'presencial', [cls.co])], institucion=None)
        crear('cerrada', [('grado', 'presencial', [cls.ec])], cierre=timezone.now() - timedelta(days=2))

    def setUp(self):
        self.client = APIClient()

    def get(self, query=''):
        return self.client.get(ROOT + query)

    def ids(self, query=''):
        response = self.get(query)
        self.assertEqual(response.status_code, 200, response.data)
        return {r['id'] for r in response.data['results']}

    def esperado(self, *claves):
        return {self.ofertas[c].pk for c in claves}

    def test_destino_ambito_ecuador_y_exterior(self):
        self.assertEqual(self.ids('?destino_ambito=ecuador'), self.esperado('nacional', 'mixta', 'doble'))
        self.assertEqual(self.ids('?destino_ambito=exterior'), self.esperado('exterior', 'mixta', 'doble'))
        # Respeta la casilla de entidades y la pestaña.
        self.assertEqual(self.ids('?destino_ambito=exterior&incluir_no_ecuatorianas=1'), self.esperado('exterior', 'mixta', 'doble', 'externa'))
        self.assertEqual(self.ids('?destino_ambito=ecuador&estado=cerrada'), self.esperado('cerrada'))

    def test_destino_ambito_en_la_misma_opcion_que_nivel_y_modalidad(self):
        # La mixta tiene una maestría (en Ecuador) y una opción en España (de grado): no cumple maestría + exterior.
        self.assertEqual(self.ids('?destino_ambito=exterior&nivel=maestria'), self.esperado('exterior'))
        self.assertEqual(self.ids('?destino_ambito=ecuador&nivel=maestria'), self.esperado('mixta'))
        self.assertEqual(self.ids('?destino_ambito=exterior&modalidad=presencial'), set())
        self.assertEqual(self.ids('?destino_ambito=exterior&nivel=grado&modalidad=virtual'), self.esperado('mixta'))

    def test_destino_ambito_invalido_o_combinado_con_destino(self):
        for query in ('?destino_ambito=extranjero', '?destino_ambito=', '?destino_ambito=EC',
                      '?destino_ambito=ecuador&destino=EC', '?destino_ambito=exterior&destino=ES',
                      '?destino_ambito=ecuador&destino_ambito=exterior'):
            with self.subTest(query):
                self.assertEqual(self.get(query).status_code, 400)

    def test_gestion_no_admite_destino_ambito(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/gestion/convocatorias/?destino_ambito=ecuador').status_code, 400)
        self.assertNotIn('facetas', self.client.get('/api/gestion/convocatorias/').data)

    def test_facetas_sin_filtros(self):
        f = self.get().data['facetas']
        self.assertEqual(f['nivel'], [{'valor': 'doctorado', 'total': 1}, {'valor': 'grado', 'total': 2}, {'valor': 'maestria', 'total': 2}])
        self.assertEqual(f['modalidad'], [{'valor': 'hibrida', 'total': 1}, {'valor': 'presencial', 'total': 2}, {'valor': 'virtual', 'total': 2}])
        self.assertEqual(f['destino'], [{'valor': 'CO', 'total': 1}, {'valor': 'EC', 'total': 3}, {'valor': 'ES', 'total': 2}])
        self.assertEqual(f['destino_ambito'], {'ecuador': 3, 'exterior': 3})

    def test_facetas_siguen_la_pestana_y_la_casilla(self):
        cerradas = self.get('?estado=cerrada').data['facetas']
        self.assertEqual((cerradas['nivel'], cerradas['destino']), ([{'valor': 'grado', 'total': 1}], [{'valor': 'EC', 'total': 1}]))
        con_casilla = self.get('?incluir_no_ecuatorianas=1').data['facetas']
        self.assertIn({'valor': 'CO', 'total': 2}, con_casilla['destino'])
        self.assertIn({'valor': 'grado', 'total': 3}, con_casilla['nivel'])

    def test_cada_faceta_no_cuenta_su_propio_filtro_y_coincide_con_aplicarlo(self):
        data = self.get('?nivel=maestria').data
        f = data['facetas']
        # El selector de nivel sigue ofreciendo todos los niveles presentes.
        self.assertEqual([x['valor'] for x in f['nivel']], ['doctorado', 'grado', 'maestria'])
        # Modalidad y destino se calculan con nivel=maestria en la misma opción.
        self.assertEqual(f['modalidad'], [{'valor': 'presencial', 'total': 1}, {'valor': 'virtual', 'total': 1}])
        self.assertEqual(f['destino'], [{'valor': 'EC', 'total': 1}, {'valor': 'ES', 'total': 1}])
        self.assertEqual(f['destino_ambito'], {'ecuador': 1, 'exterior': 1})
        # Cada conteo coincide con el número de resultados al aplicar ese valor junto con los demás filtros.
        for query in ('?q=ingenier', '?modalidad=virtual', '?destino_ambito=exterior', '?nivel=grado&q=software', ''):
            facetas = self.get(query).data['facetas']
            for dimension, param in (('nivel', 'nivel'), ('modalidad', 'modalidad'), ('destino', 'destino')):
                otros = '&'.join(x for x in query.lstrip('?').split('&') if x and not x.startswith(param + '=')
                                 and not (param == 'destino' and x.startswith('destino_ambito=')))
                for fila in facetas[dimension]:
                    with self.subTest(query=query, dimension=dimension, valor=fila['valor']):
                        aplicado = self.get('?' + '&'.join(filter(None, [otros, f"{param}={fila['valor']}"]))).data['count']
                        self.assertEqual(fila['total'], aplicado)

    def test_facetas_con_busqueda_por_programa(self):
        # «software» solo coincide con el programa de la opción de grado virtual en España de la mixta.
        f = self.get('?q=software').data['facetas']
        self.assertEqual(f['nivel'], [{'valor': 'grado', 'total': 1}])
        self.assertEqual(f['destino'], [{'valor': 'ES', 'total': 1}])
        self.assertEqual(f['destino_ambito'], {'ecuador': 0, 'exterior': 1})
