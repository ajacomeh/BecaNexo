from datetime import date
from django.test import TestCase
from rest_framework.test import APIClient
from perfiles.models import Experiencia
from . import test_comparacion as base


class ReglasV2Tests(TestCase):
    setUpTestData = classmethod(base.ComparacionTests.setUpTestData.__func__)
    setUp = base.ComparacionTests.setUp
    regla = base.ComparacionTests.regla
    resultado = base.ComparacionTests.resultado
    formacion = base.ComparacionTests.formacion

    def equivalencia(self, tipo="titulo", origen="Ing. Software", admitido="Ingeniería de Software", **kwargs):
        return {"tipo": tipo, "origen": origen, "admitido": admitido, "referencia": "Bases, apartado 4", "pais": None, "provincia": None, **kwargs}

    def test_niveles_explicitos_no_jerarquia_y_legacy_pendiente(self):
        r = self.regla("FORMACION", {"niveles_admitidos": ["grado"], "estado_exigido": "concluidos", "titulo_obtenido": True}, relacion_formacion="independiente")
        f = self.formacion()
        self.assertEqual(self.resultado()["resultado"], "cumple")
        f.nivel = "maestria"; f.save()
        self.assertEqual(self.resultado()["resultado"], "no_cumple")
        r.valor_estructurado = {"nivel_minimo": "grado", "estado_exigido": "concluidos", "titulo_obtenido": True}; r.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")

    def test_equivalencia_titulo_documentada_y_coincidencia_normalizada(self):
        r = self.regla("TITULO_AREA", {"titulos_admitidos": ["Ingeniería de Software"]}, relacion_formacion="independiente")
        f = self.formacion(nombre_titulo="Ing. Software")
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        r.equivalencias = [self.equivalencia()]; r.save()
        self.assertEqual(self.resultado()["resultado"], "cumple")
        self.assertEqual(self.resultado()["requisitos"][0]["dato_declarado"]["equivalencia_documentada"], "Bases, apartado 4")
        f.nombre_titulo = "  INGENIERÍA DE SOFTWARE "; f.save()
        self.assertEqual(self.resultado()["resultado"], "cumple")

    def grupo(self):
        self.regla("TITULO_AREA", {"areas_admitidas": [self.area.pk]}, relacion_formacion="misma_formacion", grupo_formacion="titulo_promedio")
        self.regla("PROMEDIO", {"minimo": 8, "escala_min": 0, "escala_max": 10}, relacion_formacion="misma_formacion", grupo_formacion="titulo_promedio")

    def test_grupo_satisfecho_por_una_formacion(self):
        self.grupo()
        self.formacion(area=self.otra_area, promedio=3, escala_min=0, escala_max=10)
        self.formacion(area=self.area, promedio=9, escala_min=0, escala_max=10)
        self.assertEqual(self.resultado()["resultado"], "cumple")

    def test_grupo_no_mezcla_area_y_promedio_y_admite_independencia_explicita(self):
        self.grupo()
        self.formacion(area=self.area, promedio=5, escala_min=0, escala_max=10)
        self.formacion(area=self.otra_area, promedio=9, escala_min=0, escala_max=10)
        self.assertEqual(self.resultado()["resultado"], "no_cumple")
        self.conv.requisitos.update(relacion_formacion="independiente", grupo_formacion=None)
        self.assertEqual(self.resultado()["resultado"], "cumple")

    def test_grupo_datos_desconocidos_candidata_viable(self):
        self.grupo()
        self.formacion(area=self.otra_area, promedio=10, escala_min=0, escala_max=10)
        f = self.formacion(area=self.area)
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        f.promedio = 9; f.escala_min = 0; f.escala_max = 10; f.save()
        self.assertEqual(self.resultado()["resultado"], "cumple")

    def test_escalas_distintas_no_ejecutan_texto(self):
        self.regla("PROMEDIO", {"minimo": 8, "escala_min": 0, "escala_max": 10, "equivalencia_documentada": "promedio / 10"})
        self.formacion(promedio=90, escala_min=0, escala_max=100)
        self.assertEqual(self.resultado()["resultado"], "desconocido")

    def test_ambas_perfil_y_requisito_legacy_sin_reinterpretacion(self):
        r = self.regla("DEDICACION", {"valores_admitidos": ["completa"]})
        for disponible, expected in [("ambas", "cumple"), ("parcial", "no_cumple")]:
            self.perfil.dedicacion_disponible = disponible; self.perfil.save()
            self.assertEqual(self.resultado()["resultado"], expected)
        r.valor_estructurado = {"valores_admitidos": ["ambas"]}; r.save()
        self.perfil.dedicacion_disponible = "completa"; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "no_cumple")

    def test_residencia_alias_contextual_y_homonimos(self):
        r = self.regla("RESIDENCIA", {"codigos_pais": ["EC"], "provincias": ["Pichincha"], "ciudades": ["Quito"]}, equivalencias=[self.equivalencia("ciudad", "DMQ", "Quito", pais="EC", provincia="Pichincha")])
        self.perfil.residencia = self.ec; self.perfil.provincia_residencia = "Pichincha"; self.perfil.ciudad_residencia = "DMQ"; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "cumple")
        self.perfil.provincia_residencia = "Otra provincia"; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        self.perfil.provincia_residencia = "Pichincha"; self.perfil.residencia = self.es; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "no_cumple")
        r.valor_estructurado["codigos_pais"] = ["EC", "ES"]; r.save()
        self.perfil.ciudad_residencia = "Quito"; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")

    def test_ciudad_sin_provincia_no_afirma_coincidencia(self):
        self.regla("RESIDENCIA", {"codigos_pais": ["EC"], "ciudades": ["Quito"]})
        self.perfil.residencia = self.ec; self.perfil.ciudad_residencia = "Quito"; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")

    def test_experiencia_union_area_corte_y_convencion_no_ejecutable(self):
        r = self.regla("EXPERIENCIA", {"meses_minimos": 12, "area": self.area.pk}, fecha_referencia=date(2025, 6, 30))
        for inicio, fin, actual, area in [(date(2025, 1, 1), date(2025, 3, 31), False, self.area),
                (date(2025, 3, 1), None, True, self.area), (date(2020, 1, 1), date(2024, 1, 1), False, self.otra_area)]:
            Experiencia.objects.create(perfil=self.perfil, fecha_inicio=inicio, fecha_fin=fin, actual=actual, area=area)
        e = self.resultado()["requisitos"][0]
        self.assertEqual(e["resultado"], "desconocido")
        self.assertEqual(e["dato_declarado"]["periodos_sin_superposicion"], [["2025-01-01", "2025-06-30"]])
        r.valor_estructurado["convencion_documentada"] = "Meses según cláusula pendiente de formalizar"; r.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")

    def test_virtual_extranjera_sin_traslado_exigido(self):
        self.regla("NACIONALIDAD", {"codigos_pais": ["EC"]})
        self.perfil.disponible_traslado = False; self.perfil.disponible_extranjero = False; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "cumple")

    def test_experiencia_actual_no_proyecta_datos_futuros(self):
        self.regla("EXPERIENCIA", {"meses_minimos": 12}, fecha_referencia=date(9999, 1, 1))
        Experiencia.objects.create(perfil=self.perfil, fecha_inicio=date(2025, 1, 1), actual=True)
        result = self.resultado()["requisitos"][0]
        self.assertEqual(result["resultado"], "desconocido")
        self.assertIsNone(result["dato_declarado"])
        self.assertIn("futura", result["explicacion"])

    def test_varios_destinos_y_ambitos_explicitos(self):
        self.op.paises.add(self.ec)
        self.regla("NACIONALIDAD", {"codigos_pais": ["EC"]})
        self.regla("TRASLADO", {"requerido": True}, opcion_estudio=self.op)
        self.regla("EDAD", {"maximo": 10}, fecha_referencia=date(2026, 1, 1), opcion_estudio=self.op, destino=self.es)
        self.perfil.disponible_traslado = True; self.perfil.disponible_extranjero = False; self.perfil.save()
        result = self.resultado()
        self.assertEqual(result["resultado"], "cumple")
        self.assertEqual({a["pais"]: a["resultado"] for a in result["resultados_destino"]}, {"EC": "cumple", "ES": "no_cumple"})
        self.assertEqual([len(a["requisitos"]) for a in result["resultados_destino"]], [2, 3])
        self.perfil.disponible_traslado = None; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        self.perfil.disponible_traslado = False; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "no_cumple")

    def test_admin_valida_grupos_equivalencias_destinos_y_audita(self):
        r = self.regla("TITULO_AREA", {"titulos_admitidos": ["Ingeniería de Software"]})
        url = f"/api/gestion/convocatorias/{self.conv.pk}/requisitos/{r.pk}/"
        self.assertEqual(self.client.patch(url, {"equivalencias": []}, format="json").status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.patch(url, {"equivalencias": []}, format="json").status_code, 403)
        token = self.client.get('/api/auth/csrf/').data['csrfToken']
        def patch(data): return self.client.patch(url, data, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(patch({"grupo_formacion": "", "relacion_formacion": "misma_formacion"}).status_code, 400)
        for bad in ({"relacion_formacion": "misma_formacion"}, {"equivalencias": [self.equivalencia(referencia="")]},
                    {"destino": self.ec.pk}, {"opcion_estudio": self.op.pk, "destino": self.ec.pk}):
            self.assertEqual(patch(bad).status_code, 400)
        self.assertEqual(patch({"equivalencias": [self.equivalencia()], "relacion_formacion": "independiente", "grupo_formacion": "", "opcion_estudio": self.op.pk, "destino": self.es.pk}).status_code, 200)
        self.assertEqual(self.conv.eventos.count(), 1)
        self.assertEqual(self.client.patch(f"/api/gestion/convocatorias/{self.conv.pk}/opciones/{self.op.pk}/", {"paises": []}, format="json", HTTP_X_CSRFTOKEN=token).status_code, 400)
        self.assertEqual(APIClient().get(self.path).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.path, {"usuario": self.user.pk}).status_code, 400)

    def test_equivalencia_sin_procedencia_insertada_fuera_de_api_no_se_ejecuta(self):
        self.regla("TITULO_AREA", {"titulos_admitidos": ["Ingeniería de Software"]}, equivalencias=[self.equivalencia(referencia="")])
        self.formacion(nombre_titulo="Ing. Software")
        self.assertEqual(self.resultado()["resultado"], "desconocido")
