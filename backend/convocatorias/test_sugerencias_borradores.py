"""Sugerencias de IA local para borradores: solo lectura, solo administradores, sin porcentajes. Embedder falso."""
import json
from datetime import timedelta
from unittest.mock import patch

import numpy as np
from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from perfiles.models import Pais
from .models import Convocatoria, Institucion, OpcionEstudio, TipoBeca, VectorConvocatoria
from .semantica import ModeloNoDisponible
from .vectores import VERSION_MODELO, a_bytes

EMBEDDER = "convocatorias.sugerencias.vector_convocatoria"


def unitario(*v):
    v = np.asarray(v, dtype=np.float32)
    return tuple((v / np.linalg.norm(v)).tolist())


class SugerenciasBorradoresTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ec = Pais.objects.create(codigo="EC", nombre="Ecuador")
        cls.entidad = Institucion.objects.create(nombre="Entidad sintética", sector="publico", pais=cls.ec)
        cls.otra = Institucion.objects.create(nombre="Otra entidad sintética", sector="privado", pais=cls.ec)
        users = get_user_model().objects
        cls.admin = users.create_user(email="admin-sug@example.com", nombre="Admin", password=None, rol="administrador")
        cls.postulante = users.create_user(email="post-sug@example.com", nombre="Postulante", password=None)
        cls.merito = TipoBeca.objects.get_or_create(nombre="Mérito académico")[0]

    n = 0

    def beca(self, titulo, descripcion="Solo pruebas", niveles=(), publicada=False, vector=None, institucion=None, url="", tipo=None):
        SugerenciasBorradoresTests.n += 1
        c = Convocatoria.objects.create(institucion=institucion or self.entidad, titulo=titulo, descripcion=descripcion, url_oficial=url,
                                        cierre=timezone.now() + timedelta(days=30), revision="validada" if publicada else "pendiente",
                                        clave_deduplicacion=f"sug-{self.n}".ljust(64, "x"), tipo_beca=tipo)
        for nivel in niveles:
            OpcionEstudio.objects.create(convocatoria=c, nivel=nivel, modalidad="virtual")
        if vector is not None:
            VectorConvocatoria.objects.create(convocatoria=c, vector=a_bytes(vector), version_modelo=VERSION_MODELO, hash_texto="x" * 64)
        return c

    def pedir(self, c, user=None, embedder=None):
        client = APIClient()
        if user is not None:
            client.force_login(user)
        with patch(EMBEDDER, side_effect=embedder or (lambda texto: unitario(0, 0, 1))):
            return client.get(f"/api/gestion/convocatorias/{c.pk}/sugerencias/")

    def test_solo_administradores(self):
        c = self.beca("Beca de maestría sintética")
        self.assertEqual(self.pedir(c).status_code, 403)
        self.assertEqual(self.pedir(c, self.postulante).status_code, 403)
        self.assertEqual(self.pedir(c, self.admin).status_code, 200)
        self.assertEqual(APIClient().post(f"/api/gestion/convocatorias/{c.pk}/sugerencias/", {}).status_code, 403)

    def test_no_escribe_nada_ni_devuelve_porcentajes(self):
        c = self.beca("Beca de maestría sintética")
        self.beca("Beca de maestría sintética 2027", publicada=True, niveles=["maestria"], vector=unitario(0, 0, 1))
        conteo = lambda: {mo._meta.db_table: mo.objects.count() for mo in apps.get_models()}
        client = APIClient()
        client.force_login(self.admin)  # la sesión del administrador se crea antes de contar
        antes = conteo()
        with patch(EMBEDDER, side_effect=lambda texto: unitario(0, 0, 1)):
            r = client.get(f"/api/gestion/convocatorias/{c.pk}/sugerencias/")
        self.assertEqual(conteo(), antes)
        texto = json.dumps(r.json())
        self.assertFalse(any(isinstance(v, float) for v in json.loads(texto, parse_float=lambda x: float(x)).values() if not isinstance(v, (dict, list))))
        for palabra in ("similitud", "puntaje", "confianza", "%"):
            self.assertNotIn(palabra, texto)

    def test_nivel_por_reglas(self):
        r = self.pedir(self.beca("Becas para programas de doctorado en ciencias"), self.admin).json()
        self.assertEqual(r["nivel"], {"valor": "doctorado", "etiqueta": "Doctorado", "origen": "deducido del texto"})
        # «Bachiller» suele ser requisito, no el nivel financiado: no se sugiere.
        self.assertIsNone(self.pedir(self.beca("Becas para bachilleres de colegios fiscales"), self.admin).json()["nivel"])

    def test_nivel_por_vecinos_coincidentes(self):
        for i in range(3):
            self.beca(f"Programa público {i}", publicada=True, niveles=["grado"], vector=unitario(1, 0.05 * i, 0))
        self.beca("Programa lejano", publicada=True, niveles=["maestria"], vector=unitario(0, 1, 0))
        r = self.pedir(self.beca("Programa sin nivel en el texto"), self.admin, embedder=lambda t: unitario(1, 0, 0)).json()
        self.assertEqual(r["nivel"], {"valor": "grado", "etiqueta": "Tercer nivel / grado", "origen": "según becas publicadas parecidas"})

    def test_sin_sugerencia_si_los_vecinos_discrepan_o_estan_lejos(self):
        for i, nivel in enumerate(("grado", "grado", "maestria")):
            self.beca(f"Programa público {i}", publicada=True, niveles=[nivel], vector=unitario(1, 0.05 * i, 0))
        borrador = self.beca("Programa sin nivel en el texto")
        self.assertIsNone(self.pedir(borrador, self.admin, embedder=lambda t: unitario(1, 0, 0)).json()["nivel"])  # discrepan
        self.assertIsNone(self.pedir(borrador, self.admin, embedder=lambda t: unitario(0.5, 0, 1)).json()["nivel"])  # lejanos

    def test_no_sugiere_si_el_campo_ya_tiene_valor(self):
        r = self.pedir(self.beca("Beca de maestría por excelencia académica", niveles=["grado"], tipo=self.merito), self.admin).json()
        self.assertIsNone(r["nivel"])
        self.assertIsNone(r["tipo_beca"])

    def test_tipo_solo_con_senal_inequivoca_en_el_titulo(self):
        r = self.pedir(self.beca("Beca por excelencia académica 2026"), self.admin).json()
        self.assertEqual(r["tipo_beca"], {"id": self.merito.pk, "nombre": "Mérito académico", "origen": "deducido del título"})
        self.assertIsNone(self.pedir(self.beca("Beca socioeconómica 2026", descripcion="Para estudiantes con excelencia académica"), self.admin).json()["tipo_beca"])

    def test_duplicado_por_titulo_casi_identico(self):
        publicada = self.beca("Becas Internacionales para Programas de Maestría 2026-2027 – Universidad Sintética", publicada=True, niveles=["maestria"], vector=unitario(1, 0, 0))
        borrador = self.beca("Becas Internacionales para Programas de Maestría 2025-2026 – Universidad Sintética")
        r = self.pedir(borrador, self.admin, embedder=lambda t: unitario(0.7, 0.7, 0)).json()
        self.assertEqual(r["duplicados"], [{"id": publicada.pk, "titulo": publicada.titulo, "estado": "publicada", "motivo": "título casi idéntico"}])

    def test_duplicado_misma_entidad_y_texto_muy_parecido(self):
        # Coseno ≈ 0,98: por encima del umbral con la misma entidad (0,97) y por debajo del de texto casi idéntico (0,985).
        otro = self.beca("Ayudas económicas para estudiantes de la entidad", vector=unitario(1, 0.2, 0))
        borrador = self.beca("Programa de apoyo a estudiantes")
        r = self.pedir(borrador, self.admin, embedder=lambda t: unitario(1, 0, 0)).json()
        self.assertEqual([(d["id"], d["estado"], d["motivo"]) for d in r["duplicados"]], [(otro.pk, "borrador", "misma entidad y texto muy parecido")])
        # El mismo texto en otra entidad no basta.
        otro.institucion = self.otra
        otro.save(update_fields=["institucion"])
        self.assertEqual(self.pedir(borrador, self.admin, embedder=lambda t: unitario(1, 0, 0)).json()["duplicados"], [])

    def test_no_marca_becas_distintas(self):
        self.beca("Beca de Medicina para estudiantes de salud", publicada=True, niveles=["grado"], vector=unitario(0, 1, 0))
        self.beca("Becas Internacionales para Programas de Grado – Universidad Sintética", publicada=True, niveles=["grado"], vector=unitario(1, 0, 0))
        borrador = self.beca("Becas Internacionales para Programas de Maestría – Universidad Sintética")  # otro nivel en el título
        r = self.pedir(borrador, self.admin, embedder=lambda t: unitario(1, 0, 0) if "Maestría" in t else unitario(0, 0, 1)).json()
        self.assertEqual(r["duplicados"], [])
        software = self.beca("Beca de Ingeniería de Software")
        self.assertEqual(self.pedir(software, self.admin, embedder=lambda t: unitario(0.2, 0, 1)).json()["duplicados"], [])

    def test_modelo_no_disponible_respuesta_vacia(self):
        def sin_modelo(texto):
            raise ModeloNoDisponible("sin modelo")
        r = self.pedir(self.beca("Beca de maestría sintética"), self.admin, embedder=sin_modelo)
        self.assertEqual((r.status_code, r.json()), (200, {"nivel": None, "tipo_beca": None, "duplicados": []}))
