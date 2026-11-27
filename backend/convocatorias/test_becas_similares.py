"""Vectores guardados de convocatorias y «Becas similares». Embedder falso: rápido y sin el modelo real."""
from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

import numpy as np
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from perfiles.models import Pais
from .models import Convocatoria, Institucion, OpcionEstudio, OpcionPais, Requisito, TipoRequisito, VectorConvocatoria
from .recomendaciones import texto_convocatoria
from .reglas import CONTRATOS
from .semantica import ModeloNoDisponible
from .vectores import UMBRAL_SIMILITUD, VERSION_MODELO, a_bytes, guardar_vector, hash_texto

EMBEDDER = "convocatorias.vectores.vector_convocatoria"


def unitario(*valores):
    v = np.asarray(valores, dtype=np.float32)
    return tuple((v / np.linalg.norm(v)).tolist())


def falso(texto):
    """Vector determinista según palabras clave, normalizado como el real."""
    return unitario(1.0 + texto.count("ingeniería"), 1.0 + texto.count("salud"), 0.5)


class BecasSimilaresTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ec = Pais.objects.create(codigo="EC", nombre="Ecuador")
        cls.otro = Pais.objects.create(codigo="PE", nombre="Perú")
        call_command("cargar_catalogos_convocatorias", verbosity=0)
        cls.admin = get_user_model().objects.create_user(email="admin-similares@example.com", nombre="Admin", password=None, rol="administrador")
        cls.postulante = get_user_model().objects.create_user(email="postulante-similares@example.com", nombre="Postulante", password=None)
        cls.entidad = Institucion.objects.create(nombre="Entidad ecuatoriana sintética", sector="publico", pais=cls.ec)
        cls.extranjera = Institucion.objects.create(nombre="Entidad extranjera sintética", sector="privado", pais=cls.otro)

    n = 0

    def beca(self, titulo, cierre_dias=30, revision="validada", activa=True, institucion=None, vector=None):
        BecasSimilaresTests.n += 1
        c = Convocatoria.objects.create(institucion=institucion or self.entidad, titulo=titulo, descripcion="Solo pruebas",
            url_oficial="https://example.org/beca", cierre=timezone.now() + timedelta(days=cierre_dias),
            clave_deduplicacion=f"similar-{self.n}".ljust(64, "x"), revision=revision, activa=activa)
        OpcionPais.objects.create(opcion_estudio=OpcionEstudio.objects.create(convocatoria=c, nivel="maestria", modalidad="virtual"), pais=self.ec)
        if vector is not None:
            VectorConvocatoria.objects.create(convocatoria=c, vector=a_bytes(vector), version_modelo=VERSION_MODELO,
                                              hash_texto=hash_texto(texto_convocatoria(c)))
        return c

    def publicable(self):
        offer = self.beca("Beca de ingeniería sintética", revision="pendiente")
        Requisito.objects.create(convocatoria=offer, tipo_requisito=TipoRequisito.objects.get(codigo="EDAD"),
            texto_original="Hasta 25 años", valor_estructurado={"maximo": 25}, operador=CONTRATOS["EDAD"][1],
            fecha_referencia=date(2026, 1, 1), modo_comprobacion="dato_declarado", obligatorio=True, validado=True)
        return offer

    def publicar(self, offer):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        token = client.get("/api/auth/csrf/").data["csrfToken"]
        with self.captureOnCommitCallbacks(execute=True):
            return client.post(f"/api/gestion/convocatorias/{offer.pk}/publicar/", {}, format="json", HTTP_X_CSRFTOKEN=token)

    def similares(self, offer, client=None, **extra):
        return (client or APIClient()).get(f"/api/becas/{offer.pk}/similares/", extra)

    # --- Guardado de vectores ---------------------------------------------------------------------------------

    @patch(EMBEDDER, side_effect=falso)
    def test_publicar_guarda_el_vector(self, embedder):
        offer = self.publicable()
        self.assertEqual(self.publicar(offer).status_code, 200)
        guardado = VectorConvocatoria.objects.get(convocatoria=offer)
        self.assertEqual((guardado.version_modelo, guardado.hash_texto), (VERSION_MODELO, hash_texto(texto_convocatoria(offer))))
        np.testing.assert_allclose(np.frombuffer(bytes(guardado.vector), dtype=np.float32), falso(texto_convocatoria(offer)), rtol=1e-6)
        embedder.assert_called_once_with(texto_convocatoria(offer))  # mismo texto que «Para ti · IA»

    @patch(EMBEDDER, side_effect=falso)
    def test_no_recalcula_si_el_texto_no_cambia(self, embedder):
        offer = self.publicable()
        self.publicar(offer)
        self.assertEqual(guardar_vector(offer), "al_dia")
        # Editar una opción de una convocatoria ya pública la vuelve a publicar: con el mismo texto, no recalcula.
        option = offer.opciones.get()
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        token = client.get("/api/auth/csrf/").data["csrfToken"]
        with self.captureOnCommitCallbacks(execute=True):
            response = client.patch(f"/api/gestion/convocatorias/{offer.pk}/opciones/{option.pk}/", {"duracion_meses": 24},
                                    format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(embedder.call_count, 1)

    @patch(EMBEDDER, side_effect=falso)
    def test_recalcula_si_el_texto_cambia(self, embedder):
        offer = self.publicable()
        self.publicar(offer)
        antes = VectorConvocatoria.objects.get(convocatoria=offer).hash_texto
        offer.descripcion = "Ahora también salud pública"
        offer.revision = "pendiente"
        offer.save(update_fields=["descripcion", "revision"])
        self.assertEqual(self.publicar(offer).status_code, 200)
        despues = VectorConvocatoria.objects.get(convocatoria=offer)
        self.assertNotEqual(despues.hash_texto, antes)
        self.assertEqual(despues.hash_texto, hash_texto(texto_convocatoria(offer)))
        self.assertEqual(embedder.call_count, 2)
        # Cambio de versión del modelo: también recalcula.
        VectorConvocatoria.objects.filter(convocatoria=offer).update(version_modelo="otro-modelo")
        self.assertEqual(guardar_vector(offer), "calculado")

    def test_fallo_del_modelo_no_bloquea_la_publicacion(self):
        for error in (ModeloNoDisponible("sin modelo"), RuntimeError("fallo inesperado")):
            with self.subTest(error=type(error).__name__), patch(EMBEDDER, side_effect=error):
                offer = self.publicable()
                with self.assertLogs("convocatorias.vectores", level="WARNING"):
                    self.assertEqual(self.publicar(offer).status_code, 200)
                offer.refresh_from_db()
                self.assertEqual((offer.revision, offer.activa), ("validada", True))
                self.assertFalse(VectorConvocatoria.objects.filter(convocatoria=offer).exists())

    # --- Comando ---------------------------------------------------------------------------------------------

    def comando(self, *args):
        out, err = StringIO(), StringIO()
        call_command("calcular_vectores_convocatorias", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    @patch(EMBEDDER, side_effect=falso)
    def test_comando_idempotente_y_dry_run_sin_escritura(self, embedder):
        publicas = [self.beca(f"Pública {i}") for i in range(3)]
        self.beca("Borrador", revision="pendiente")
        out, _ = self.comando("--dry-run")
        self.assertIn("'calculadas': 3, 'al_dia': 0, 'fallidas': 0", out)
        self.assertIn("simulación (sin escribir)", out)
        self.assertEqual((VectorConvocatoria.objects.count(), embedder.call_count), (0, 0))
        out, _ = self.comando()
        self.assertIn("'calculadas': 3, 'al_dia': 0, 'fallidas': 0", out)
        self.assertEqual(set(VectorConvocatoria.objects.values_list("convocatoria_id", flat=True)), {c.pk for c in publicas})
        out, _ = self.comando()
        self.assertIn("'calculadas': 0, 'al_dia': 3, 'fallidas': 0", out)
        self.assertEqual(embedder.call_count, 3)
        out, _ = self.comando("--dry-run", "--forzar")
        self.assertIn("'calculadas': 3", out)
        self.assertEqual(embedder.call_count, 3)
        out, _ = self.comando("--forzar")
        self.assertIn("'calculadas': 3, 'al_dia': 0, 'fallidas': 0", out)
        self.assertIn("'segundos':", out)

    def test_comando_cuenta_fallos_sin_detenerse(self):
        self.beca("Pública")
        with patch(EMBEDDER, side_effect=ModeloNoDisponible("sin modelo")):
            out, err = self.comando()
        self.assertIn("'calculadas': 0, 'al_dia': 0, 'fallidas': 1", out)
        self.assertIn("sin modelo", err)

    # --- Endpoint --------------------------------------------------------------------------------------------

    def test_orden_umbral_y_exclusiones(self):
        base = self.beca("Base", vector=unitario(1, 0, 0))
        abierta_alta = self.beca("Abierta 0,90", vector=unitario(0.9, 0.436, 0))
        abierta_media = self.beca("Abierta 0,70", vector=unitario(0.7, 0.714, 0))
        abierta_justa = self.beca("Abierta 0,66", vector=unitario(0.66, 0.751, 0))
        cerrada_maxima = self.beca("Cerrada 0,99", cierre_dias=-5, vector=unitario(0.99, 0.141, 0))
        self.beca("Cerrada 0,80", cierre_dias=-5, vector=unitario(0.8, 0.6, 0))  # queda fuera por el límite de 4
        self.beca("Bajo el umbral", vector=unitario(0.5, 0.866, 0))
        self.beca("Borrador idéntico", revision="pendiente", vector=unitario(1, 0, 0))
        self.beca("Pausada idéntica", activa=False, vector=unitario(1, 0, 0))
        self.beca("Extranjera idéntica", institucion=self.extranjera, vector=unitario(1, 0, 0))
        with patch(EMBEDDER, side_effect=AssertionError("no debe cargar el modelo")):
            response = self.similares(base)
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.data["results"]]
        # Vigentes primero, por similitud; luego las cerradas relevantes (con su estado).
        self.assertEqual(ids, [abierta_alta.pk, abierta_media.pk, abierta_justa.pk, cerrada_maxima.pk])
        self.assertEqual(response.data["results"][-1]["estado"], "cerrada")
        self.assertNotIn(base.pk, ids)
        self.assertEqual(set(response.data["results"][0]), {"id", "titulo", "estado", "institucion", "oferente_externo", "niveles", "campo_conocimiento"})
        self.assertEqual(response.data["results"][0]["niveles"], ["maestria"])
        self.assertEqual(response.data["results"][0]["institucion"]["nombre"], self.entidad.nombre)

    def test_sin_similares_sobre_el_umbral_devuelve_vacio(self):
        base = self.beca("Base", vector=unitario(1, 0, 0))
        self.beca("Lejana", vector=unitario(UMBRAL_SIMILITUD - 0.2, 0.9, 0))
        self.assertEqual(self.similares(base).data, {"results": []})
        sola = self.beca("Sola en el catálogo", vector=unitario(0, 0, 1))
        VectorConvocatoria.objects.exclude(convocatoria=sola).delete()
        self.assertEqual(self.similares(sola).data, {"results": []})

    def test_permisos_iguales_al_detalle_publico(self):
        base = self.beca("Base", vector=unitario(1, 0, 0))
        self.beca("Parecida", vector=unitario(0.9, 0.436, 0))
        borrador = self.beca("Borrador", revision="pendiente", vector=unitario(1, 0, 0))
        extranjera = self.beca("Extranjera", institucion=self.extranjera, vector=unitario(1, 0, 0))
        postulante = APIClient()
        postulante.force_login(self.postulante)
        for client in (APIClient(), postulante):
            self.assertEqual(self.similares(base, client).status_code, 200)
            self.assertEqual(len(self.similares(base, client).data["results"]), 1)
            for oculta in (borrador, extranjera):
                self.assertEqual(client.get(f"/api/becas/{oculta.pk}/").status_code, 404)
                self.assertEqual(self.similares(oculta, client).status_code, 404)
        self.assertEqual(APIClient().get("/api/becas/999999/similares/").status_code, 404)
        self.assertEqual(self.similares(base, usuario=self.postulante.pk).status_code, 400)  # sin parámetros
        self.assertEqual(APIClient().post(f"/api/becas/{base.pk}/similares/", {}).status_code, 405)

    def test_vector_faltante_se_calcula_una_sola_vez(self):
        base = self.beca("Beca de ingeniería")
        parecida = self.beca("Otra de ingeniería")
        with patch(EMBEDDER, side_effect=falso) as embedder:
            guardar_vector(parecida)
            embedder.reset_mock()
            first = self.similares(base)
            second = self.similares(base)
        self.assertEqual([item["id"] for item in first.data["results"]], [parecida.pk])
        self.assertEqual(second.data, first.data)
        self.assertEqual(embedder.call_count, 1)
        self.assertTrue(VectorConvocatoria.objects.filter(convocatoria=base).exists())

    def test_modelo_no_disponible_devuelve_vacio_sin_error(self):
        base = self.beca("Sin vector")
        self.beca("Con vector", vector=unitario(1, 0, 0))
        with patch(EMBEDDER, side_effect=ModeloNoDisponible("sin modelo")), self.assertLogs("convocatorias.vectores", level="WARNING"):
            response = self.similares(base)
        self.assertEqual((response.status_code, response.data), (200, {"results": []}))
