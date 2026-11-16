from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from perfiles.models import Area, Pais, Perfil, PerfilArea, Preferencia, PerfilPais
from favoritos.models import Favorito
from .models import Convocatoria, Institucion, OpcionEstudio, Requisito, TipoRequisito
from .reglas import CONTRATOS
from .semantica import _modelo, similitud, vector


class InferenciaRealTests(SimpleTestCase):
    def test_modelo_local_en_cpu_y_textos_en_espanol(self):
        if not (Path(settings.SEMANTIC_MODEL_DIR) / "onnx" / "model_quint8_avx2.onnx").is_file():
            self.skipTest("Modelo local opcional no instalado")
        self.assertEqual(_modelo()[0].get_providers(), ["CPUExecutionProvider"])
        origen = vector("Ingeniería de petróleo y producción de hidrocarburos")
        self.assertEqual(len(origen), 384)
        self.assertGreater(similitud(origen, vector("Beca para estudiar ingeniería de energía y petróleo")),
                           similitud(origen, vector("Historia del arte y música clásica")))
        self.assertEqual(origen, vector("Ingeniería de petróleo y producción de hidrocarburos"))


class RecomendacionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ec = Pais.objects.create(codigo="EC", nombre="Ecuador")
        cls.user = get_user_model().objects.create_user(email="recomendacion@example.com", nombre="Prueba", password=None)
        cls.admin = get_user_model().objects.create_user(email="admin-recomendacion@example.com", nombre="Prueba", password=None, rol="administrador")
        cls.perfil = Perfil.objects.create(usuario=cls.user, nacionalidad=ec, fecha_nacimiento=date(2000, 1, 1), dedicacion_disponible="parcial")
        area = Area.objects.create(nombre="Ingeniería petrolera")
        PerfilArea.objects.create(perfil=cls.perfil, area=area)
        Preferencia.objects.create(perfil=cls.perfil, nivel="maestria", modalidad="virtual")
        PerfilPais.objects.create(perfil=cls.perfil, pais=ec)
        institucion = Institucion.objects.create(nombre="Institución ecuatoriana", sector="publico", pais=ec)
        call_command("cargar_catalogos_convocatorias", verbosity=0)
        for pk, dedicacion in ((1, "parcial"), (2, "completa")):
            offer = Convocatoria.objects.create(institucion=institucion, titulo=f"Programa {pk}",
                descripcion="Estudios de ingeniería", cierre=timezone.now() + timedelta(days=30),
                revision="validada", clave_deduplicacion=f"recomendar-{pk}")
            opcion = OpcionEstudio.objects.create(convocatoria=offer, nivel="maestria", modalidad="virtual")
            opcion.paises.add(ec)
            Requisito.objects.create(convocatoria=offer, tipo_requisito=TipoRequisito.objects.get(codigo="DEDICACION"),
                texto_original="Dedicación exigida", valor_estructurado={"valores_admitidos": [dedicacion]},
                operador=CONTRATOS["DEDICACION"][1], modo_comprobacion="dato_declarado", validado=True)

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.path = "/api/becas/recomendaciones/"

    @patch("convocatorias.recomendaciones.vector_convocatoria", side_effect=lambda texto: (1.0, 0.0) if "Programa 2" in texto else (0.0, 1.0))
    @patch("convocatorias.recomendaciones.vector", return_value=(1.0, 0.0))
    def test_elegibilidad_precede_afinidad_y_no_expone_perfil(self, *_):
        favorito = Favorito.objects.create(usuario=self.user, convocatoria=Convocatoria.objects.get(clave_deduplicacion="recomendar-1"))
        self.client.force_login(self.user)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        rows = response.data["results"]
        self.assertEqual([x["elegibilidad"] for x in rows], ["cumple", "no_cumple"])
        self.assertTrue(all(x["afinidad"]["estado"] == "calculada" for x in rows))
        self.assertEqual(rows[0]["convocatoria"]["favorito_id"], favorito.pk)
        self.assertEqual(rows[0]["preferencias"]["coincidencias"], ["nivel de estudio", "modalidad", "destino"])
        self.assertNotIn("email", str(rows))
        self.assertNotIn("_puntuacion", str(rows))
        self.assertNotIn("porcentaje", str(rows))

    def test_modelo_ausente_mantiene_reglas(self):
        self.client.force_login(self.user)
        with override_settings(SEMANTIC_MODEL_DIR="Z:/ruta-inexistente-modelo-becanexo"):
            _modelo.cache_clear()
            rows = self.client.get(self.path).data["results"]
        _modelo.cache_clear()
        self.assertEqual([x["elegibilidad"] for x in rows], ["cumple", "no_cumple"])
        self.assertTrue(all(x["afinidad"]["estado"] == "modelo_no_disponible" for x in rows))

    def test_perfil_incompleto_y_permisos(self):
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.path + "?usuario=2").status_code, 400)
        self.perfil.areas.all().delete()
        rows = self.client.get(self.path).data["results"]
        self.assertTrue(all(x["afinidad"]["estado"] == "sin_datos_perfil" for x in rows))

    @patch("convocatorias.recomendaciones.vector_convocatoria", return_value=(1.0, 0.0))
    @patch("convocatorias.recomendaciones.vector", return_value=(1.0, 0.0))
    def test_cambios_de_perfil_requisito_y_texto_se_reflejan_en_nueva_consulta(self, profile_vector, offer_vector):
        self.client.force_login(self.user)
        first = self.client.get(self.path).data["results"]
        self.assertEqual([row["elegibilidad"] for row in first], ["cumple", "no_cumple"])

        self.perfil.dedicacion_disponible = None
        self.perfil.descripcion = "Intereses académicos actualizados"
        self.perfil.save(update_fields=["dedicacion_disponible", "descripcion"])
        second = self.client.get(self.path).data["results"]
        self.assertEqual([row["elegibilidad"] for row in second], ["desconocido", "desconocido"])
        self.assertIn("Intereses académicos actualizados", profile_vector.call_args.args[0])

        self.perfil.dedicacion_disponible = "parcial"
        self.perfil.save(update_fields=["dedicacion_disponible"])
        offer = Convocatoria.objects.get(clave_deduplicacion="recomendar-2")
        offer.titulo = "Programa 2 actualizado"
        offer.save(update_fields=["titulo"])
        requirement = offer.requisitos.get(tipo_requisito__codigo="DEDICACION")
        requirement.valor_estructurado = {"valores_admitidos": ["parcial"]}
        requirement.save(update_fields=["valor_estructurado"])
        third = self.client.get(self.path).data["results"]
        self.assertEqual([row["elegibilidad"] for row in third], ["cumple", "cumple"])
        self.assertTrue(any("Programa 2 actualizado" in call.args[0] for call in offer_vector.call_args_list))

    def test_afinidad_real_ordena_solo_dentro_de_elegibilidad(self):
        if not (Path(settings.SEMANTIC_MODEL_DIR) / "onnx" / "model_quint8_avx2.onnx").is_file():
            self.skipTest("Modelo local opcional no instalado")
        arte = Convocatoria.objects.get(clave_deduplicacion="recomendar-1")
        arte.titulo = "Historia del arte y música clásica"
        arte.descripcion = "Estudios de arte, música e historia"
        arte.save(update_fields=["titulo", "descripcion"])
        petroleo = Convocatoria.objects.create(institucion=arte.institucion,
            titulo="Ingeniería petrolera e hidrocarburos", descripcion="Producción de energía y petróleo",
            cierre=timezone.now() + timedelta(days=30), revision="validada", clave_deduplicacion="recomendar-3")
        opcion = OpcionEstudio.objects.create(convocatoria=petroleo, nivel="maestria", modalidad="virtual")
        opcion.paises.add(self.perfil.nacionalidad)
        Requisito.objects.create(convocatoria=petroleo, tipo_requisito=TipoRequisito.objects.get(codigo="DEDICACION"),
            texto_original="Dedicación parcial", valor_estructurado={"valores_admitidos": ["parcial"]},
            operador=CONTRATOS["DEDICACION"][1], modo_comprobacion="dato_declarado", validado=True)
        self.client.force_login(self.user)
        rows = self.client.get(self.path).data["results"]
        self.assertEqual([x["convocatoria"]["id"] for x in rows], [petroleo.pk, arte.pk,
            Convocatoria.objects.get(clave_deduplicacion="recomendar-2").pk])
        self.assertTrue(all(x["afinidad"]["estado"] == "calculada" for x in rows))
