from datetime import date
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
from perfiles.models import Pais, Idioma, Area, Perfil, PerfilIdioma, Formacion, Preferencia, PerfilPais
from .models import Institucion, Convocatoria, OpcionEstudio, TipoRequisito, Requisito
from .reglas import CONTRATOS


class ComparacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ec = Pais.objects.create(codigo="EC", nombre="Ecuador")
        cls.es = Pais.objects.create(codigo="ES", nombre="España")
        cls.en = Idioma.objects.create(codigo="en", nombre="Inglés")
        cls.area = Area.objects.create(nombre="Ingeniería de prueba")
        cls.otra_area = Area.objects.create(nombre="Arte de prueba")
        call_command("cargar_catalogos_convocatorias", verbosity=0)
        cls.user = get_user_model().objects.create_user(email="comparacion@example.com", nombre="DEMO comparación", password=None)
        cls.other = get_user_model().objects.create_user(email="otro-comparacion@example.com", nombre="DEMO otro", password=None)
        cls.admin = get_user_model().objects.create_user(email="admin-comparacion@example.com", nombre="DEMO admin", password=None, rol="administrador")
        cls.perfil = Perfil.objects.create(usuario=cls.user, nacionalidad=cls.ec, fecha_nacimiento=date(2000, 6, 15))
        institucion = Institucion.objects.create(nombre="DEMO entidad", sector="publico", pais=cls.ec)
        cls.conv = Convocatoria.objects.create(institucion=institucion, titulo="DEMO comparación", revision="validada", clave_deduplicacion="comparacion")
        cls.op = OpcionEstudio.objects.create(convocatoria=cls.conv, nivel="maestria", modalidad="virtual")
        cls.op.paises.add(cls.es)
        cls.path = f"/api/becas/{cls.conv.pk}/comparacion/"

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def regla(self, codigo, valor, **kwargs):
        return Requisito.objects.create(convocatoria=self.conv, tipo_requisito=TipoRequisito.objects.get(codigo=codigo),
            texto_original=f"DEMO condición {codigo}", valor_estructurado=valor, operador=CONTRATOS[codigo][1],
            modo_comprobacion="entidad_oferente" if codigo in ("DOCUMENTO", "ACREDITACION", "OTRO") else "dato_declarado", validado=True, **kwargs)

    def resultado(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("no-store", response["Cache-Control"])
        return response.data["opciones"][0]

    def formacion(self, **kwargs):
        return Formacion.objects.create(perfil=self.perfil, nivel="grado", carrera="DEMO", titulo_obtenido=True,
            estado_estudios="concluidos", **kwargs)

    def test_coincidencia_nacionalidad_sin_porcentaje_ni_datos_personales_innecesarios(self):
        self.regla("NACIONALIDAD", {"codigos_pais": ["EC"]})
        result = self.resultado()
        self.assertEqual(result["resultado"], "cumple")
        self.assertEqual(result["requisitos"][0]["dato_declarado"], {"nacionalidad": "EC"})
        self.assertNotIn("email", str(result))
        self.assertNotIn("similitud", str(result))
        self.assertNotIn("afinidad", str(result))

    def test_edad_limites_inclusivos_y_fecha_publicada(self):
        r = self.regla("EDAD", {"minimo": 26, "maximo": 26}, fecha_referencia=date(2026, 6, 15))
        self.assertEqual(self.resultado()["resultado"], "cumple")
        r.fecha_referencia = date(2026, 6, 14); r.save()
        result = self.resultado()
        self.assertEqual(result["resultado"], "no_cumple")
        self.assertEqual(result["requisitos"][0]["dato_declarado"], {"edad_a_fecha_referencia": 25})
        r.fecha_referencia = date(2027, 6, 15); r.save()
        self.assertEqual(self.resultado()["resultado"], "no_cumple")

    def test_edad_sin_fecha_referencia_desconocida(self):
        self.regla("EDAD", {"maximo": 30})
        self.assertEqual(self.resultado()["resultado"], "desconocido")

    def test_dato_ausente_y_perfil_ausente_no_son_incumplimiento(self):
        self.regla("IDIOMA", {"codigo_idioma": "en", "nivel_minimo": "B2"})
        result = self.resultado()
        self.assertEqual(result["resultado"], "desconocido")
        self.assertEqual(result["requisitos"][0]["seccion_perfil"], "idiomas")
        self.client.force_login(self.other)
        result = self.resultado()
        self.assertEqual(result["resultado"], "desconocido")
        self.assertEqual(result["requisitos"][0]["seccion_perfil"], "idiomas")

    def test_dedicacion_disponible_cubre_tiempo_parcial_sin_confundir_traslado(self):
        # Sin requisito de dedicación no se crea un incumplimiento artificial.
        self.perfil.dedicacion_disponible = "parcial"
        self.perfil.disponible_traslado = False
        self.perfil.save()
        self.assertEqual(self.resultado()["requisitos"], [])
        rule = self.regla("DEDICACION", {"valores_admitidos": ["completa"]})
        expected = {
            "completa": {"completa": "cumple", "parcial": "cumple", "ambas": "no_cumple"},
            "parcial": {"completa": "no_cumple", "parcial": "cumple", "ambas": "no_cumple"},
            "ambas": {"completa": "cumple", "parcial": "cumple", "ambas": "cumple"},
        }
        for available, requirements in expected.items():
            self.perfil.dedicacion_disponible = available
            self.perfil.save(update_fields=["dedicacion_disponible"])
            for required, state in requirements.items():
                with self.subTest(disponible=available, exigido=required):
                    rule.valor_estructurado = {"valores_admitidos": [required]}
                    rule.save(update_fields=["valor_estructurado"])
                    alternative = self.resultado()
                    result = alternative["requisitos"][0]
                    self.assertEqual(result["resultado"], state)
                    self.assertEqual(alternative["resultado"], state)
                    self.assertEqual(result["seccion_perfil"], "disponibilidad" if state == "no_cumple" else None)
        self.perfil.dedicacion_disponible = None
        self.perfil.save(update_fields=["dedicacion_disponible"])
        alternative = self.resultado()
        self.assertEqual(alternative["resultado"], "desconocido")
        self.assertEqual(alternative["requisitos"][0]["resultado"], "desconocido")
        self.assertEqual(alternative["requisitos"][0]["seccion_perfil"], "disponibilidad")

    def test_enlaces_solo_para_datos_del_perfil_y_perfil_sin_declarar(self):
        nationality = self.regla("NACIONALIDAD", {"codigos_pais": ["EC"]})
        self.client.force_login(self.other)
        first = self.resultado()["requisitos"][0]
        self.assertEqual(first["resultado"], "desconocido")
        self.assertEqual(first["seccion_perfil"], "datos-personales")
        self.client.force_login(self.user)
        nationality.activo = False
        nationality.save(update_fields=["activo"])
        self.regla("EDAD", {"maximo": 30})  # Falta fecha publicada: no se resuelve desde el perfil.
        self.regla("ACREDITACION", {"certificados_admitidos": "Documento oficial"})
        for item in self.resultado()["requisitos"]:
            self.assertEqual(item["resultado"], "desconocido")
            self.assertIsNone(item["seccion_perfil"])

    def test_mcer_nivel_inferior_igual_y_superior(self):
        self.regla("IDIOMA", {"codigo_idioma": "en", "nivel_minimo": "B2"})
        idioma = PerfilIdioma.objects.create(perfil=self.perfil, idioma=self.en, nivel="B1")
        for nivel, expected in [("B1", "no_cumple"), ("B2", "cumple"), ("C1", "cumple"), (None, "desconocido")]:
            with self.subTest(nivel=nivel):
                idioma.nivel = nivel; idioma.save()
                self.assertEqual(self.resultado()["resultado"], expected)

    def test_idioma_y_acreditacion_separados(self):
        self.regla("IDIOMA", {"codigo_idioma": "en", "nivel_minimo": "B2"})
        self.regla("ACREDITACION", {"certificados_admitidos": "Certificado según bases"})
        PerfilIdioma.objects.create(perfil=self.perfil, idioma=self.en, nivel="C1")
        result = self.resultado()
        self.assertEqual([e["resultado"] for e in result["requisitos"]], ["cumple", "desconocido"])
        self.assertEqual(result["resultado"], "cumple")
        self.assertEqual(result["verificaciones_externas_pendientes"], 1)
        self.assertEqual(result["requisitos"][1]["estado_documental"], "pendiente_entidad_oferente")

    def test_documento_anexo_no_se_acredita_por_coincidir(self):
        self.regla("NACIONALIDAD", {"codigos_pais": ["EC"]}, documento_exigido="Documento de identidad")
        result = self.resultado()["requisitos"][0]
        self.assertEqual(result["resultado"], "cumple")
        self.assertTrue(result["comprobacion_externa"])
        self.assertEqual(result["estado_documental"], "pendiente_entidad_oferente")

    def test_comunes_especificos_no_mezclados_y_destacada(self):
        second = OpcionEstudio.objects.create(convocatoria=self.conv, nivel="grado", modalidad="presencial")
        second.paises.add(self.ec)
        self.regla("NACIONALIDAD", {"codigos_pais": ["EC"]})
        self.regla("EDAD", {"maximo": 20}, fecha_referencia=date(2026, 6, 15), opcion_estudio=self.op)
        self.regla("EDAD", {"minimo": 20}, fecha_referencia=date(2026, 6, 15), opcion_estudio=second)
        response = self.client.get(self.path).data
        self.assertEqual([o["resultado"] for o in response["opciones"]], ["no_cumple", "cumple"])
        self.assertEqual([len(o["requisitos"]) for o in response["opciones"]], [2, 2])
        self.assertEqual(response["opcion_destacada_id"], second.pk)
        self.assertEqual(self.client.get(f"/api/becas/{self.conv.pk}/").status_code, 200)

    def test_sin_reglas_no_es_cumplimiento_y_no_exigido_explicito(self):
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        self.assertIn("No hay requisitos", self.resultado()["aviso"])
        self.regla("TRASLADO", {"requerido": False})
        self.client.force_login(self.other)
        self.assertEqual(self.resultado()["resultado"], "cumple")

    def test_opciones_y_reglas_inactivas_no_aparecen(self):
        self.regla("EDAD", {"maximo": 10}, fecha_referencia=date(2026, 6, 15), activo=False)
        OpcionEstudio.objects.create(convocatoria=self.conv, nivel="grado", modalidad="virtual", activa=False)
        self.assertEqual(self.resultado()["requisitos"], [])
        self.assertEqual(len(self.client.get(self.path).data["opciones"]), 1)

    def test_formacion_exacta_sin_inventar_jerarquia(self):
        r = self.regla("FORMACION", {"nivel_minimo": "grado", "estado_exigido": "concluidos", "titulo_obtenido": True})
        self.formacion()
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        r.valor_estructurado["nivel_minimo"] = "bachillerato"; r.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")

    def test_titulo_y_area_no_se_toman_de_formaciones_distintas(self):
        self.regla("TITULO_AREA", {"titulos_admitidos": ["Ingeniería"], "areas_admitidas": [self.area.pk]})
        self.formacion(nombre_titulo="Ingeniería", area=self.otra_area)
        f = self.formacion(nombre_titulo=None, area=self.area)
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        f.nombre_titulo = "  INGENIERÍA  "; f.save()
        self.assertEqual(self.resultado()["resultado"], "cumple")

    def test_varias_reglas_academicas_sin_relacion_explicita_no_mezclan_titulos(self):
        self.regla("TITULO_AREA", {"areas_admitidas": [self.area.pk]})
        self.regla("PROMEDIO", {"minimo": 8, "escala_min": 0, "escala_max": 10})
        self.formacion(area=self.area, promedio=5, escala_min=0, escala_max=10)
        self.formacion(area=self.otra_area, promedio=10, escala_min=0, escala_max=10)
        result = self.resultado()
        self.assertEqual(result["resultado"], "desconocido")
        self.assertTrue(all(e["resultado"] == "desconocido" for e in result["requisitos"]))
        self.assertIn("sin vínculo", result["requisitos"][0]["explicacion"])

    def test_promedio_limite_escala_y_dato_ausente(self):
        self.regla("PROMEDIO", {"minimo": 8, "escala_min": 0, "escala_max": 10})
        f = self.formacion(promedio=8, escala_min=0, escala_max=10)
        self.assertEqual(self.resultado()["resultado"], "cumple")
        f.promedio = 7.999; f.save()
        self.assertEqual(self.resultado()["resultado"], "no_cumple")
        f.promedio = 80; f.escala_max = 100; f.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        f.promedio = f.escala_min = f.escala_max = None; f.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")

    def test_relacion_academica_ambigua_no_oculta_incumplimiento_comprobable(self):
        self.regla("TITULO_AREA", {"areas_admitidas": [self.area.pk]})
        self.regla("PROMEDIO", {"minimo": 8, "escala_min": 0, "escala_max": 10})
        self.formacion(area=self.otra_area, promedio=9, escala_min=0, escala_max=10)
        result = self.resultado()
        self.assertEqual(result["resultado"], "no_cumple")
        self.assertEqual([e["resultado"] for e in result["requisitos"]], ["no_cumple", "desconocido"])

    def test_experiencia_ambigua_desconocida(self):
        self.regla("EXPERIENCIA", {"meses_minimos": 12})
        self.assertEqual(self.resultado()["resultado"], "desconocido")

    def test_regla_no_revisada_o_contrato_invalido_no_se_interpreta(self):
        r = self.regla("EDAD", {"maximo": "treinta"}, fecha_referencia=date(2026, 6, 15))
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        r.valor_estructurado = {"maximo": 35}; r.validado = False; r.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")

    def test_preferencias_no_restringen_y_opcional_no_impide(self):
        Preferencia.objects.create(perfil=self.perfil, nivel="grado", modalidad="presencial")
        PerfilPais.objects.create(perfil=self.perfil, pais=self.ec)
        self.regla("NACIONALIDAD", {"codigos_pais": ["EC"]})
        self.regla("EDAD", {"maximo": 18}, fecha_referencia=date(2026, 6, 15), obligatorio=False)
        self.assertEqual(self.resultado()["resultado"], "cumple")

    def test_edicion_perfil_reflejada_y_csrf_conservado(self):
        self.regla("DEDICACION", {"valores_admitidos": ["completa", "ambas"]})
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        self.assertEqual(self.client.patch("/api/perfil/", {"dedicacion_disponible": "completa"}, format="json").status_code, 403)
        token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        response = self.client.patch("/api/perfil/", {"dedicacion_disponible": "completa"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.resultado()["resultado"], "cumple")

    def test_residencia_pais_y_alias_territorial(self):
        self.regla("RESIDENCIA", {"codigos_pais": ["EC"], "provincias": ["Pichincha"], "ciudades": ["Quito"]})
        self.perfil.residencia = self.ec; self.perfil.provincia_residencia = "Pichincha"; self.perfil.ciudad_residencia = "  QUITO "; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "cumple")
        self.perfil.ciudad_residencia = "Distrito Metropolitano de Quito"; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        self.perfil.residencia = self.es; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "no_cumple")

    def test_traslado_extranjero_no_confunde_destinos_preferidos(self):
        self.regla("TRASLADO", {"requerido": True, "destino": "ES"})
        self.perfil.disponible_traslado = True; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        self.perfil.disponible_extranjero = False; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "no_cumple")
        self.perfil.disponible_extranjero = True; self.perfil.save()
        self.assertEqual(self.resultado()["resultado"], "cumple")

    def test_permisos_usuario_ajeno_y_ocultas(self):
        self.regla("NACIONALIDAD", {"codigos_pais": ["EC"]})
        self.assertEqual(APIClient().get(self.path).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.path, {"usuario": self.user.pk}).status_code, 400)
        self.assertEqual(self.client.get(self.path, {"perfil_id": self.perfil.pk}).status_code, 400)
        self.assertEqual(self.resultado()["resultado"], "desconocido")
        self.conv.revision = "pendiente"; self.conv.save()
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.conv.revision = "validada"; self.conv.activa = False; self.conv.save()
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_solo_lectura_y_rechazo_cuerpo_usuario(self):
        token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        self.assertEqual(self.client.post(self.path, {}, format="json", HTTP_X_CSRFTOKEN=token).status_code, 405)
        self.assertEqual(self.client.generic("GET", self.path, '{"usuario": 999}', content_type="application/json").status_code, 400)
