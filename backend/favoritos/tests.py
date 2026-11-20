from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from perfiles.models import Pais
from convocatorias.models import Institucion, Convocatoria
from .models import Favorito


class FavoritosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.one = users.create_user(email="fav-one@example.com", nombre="Uno", password="Testing-Favoritos-75!")
        cls.two = users.create_user(email="fav-two@example.com", nombre="Dos")
        cls.admin = users.create_user(email="fav-admin@example.com", nombre="Admin", rol="administrador")
        country = Pais.objects.create(codigo="EC", nombre="Ecuador")
        institution = Institucion.objects.create(nombre="DEMO pruebas", sector="privado", pais=country)
        cls.offer = Convocatoria.objects.create(institucion=institution, titulo="Oferta sintética", descripcion="Texto sintético",
            url_oficial="https://example.org/test", clave_deduplicacion="a"*64, revision="validada",
            cierre=timezone.now() + timedelta(days=30))  # postulable: el listado de becas la incluye

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.login(self.one)

    def login(self, user):
        self.client.force_login(user)
        self.token = self.client.get("/api/auth/csrf/").data["csrfToken"]

    def save(self, **data):
        return self.client.post("/api/favoritos/", {"convocatoria": self.offer.pk, **data}, format="json", HTTP_X_CSRFTOKEN=self.token)

    def remove(self, pk, data=None):
        return self.client.delete(f"/api/favoritos/{pk}/", data or {}, format="json", HTTP_X_CSRFTOKEN=self.token)

    def test_guardar_listar_quitar(self):
        response = self.save()
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        self.assertEqual(Favorito.objects.get(pk=pk).usuario, self.one)
        listed = self.client.get("/api/favoritos/")
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["results"][0]["convocatoria"]["titulo"], self.offer.titulo)
        self.assertIn("no-store", listed["Cache-Control"])
        self.assertEqual(self.client.get(f"/api/becas/{self.offer.pk}/").data["favorito_id"], pk)
        self.assertEqual(self.remove(pk).status_code, 204)
        self.assertIsNone(self.client.get("/api/becas/").data["results"][0]["favorito_id"])
        self.assertEqual(self.client.get("/api/favoritos/").data["count"], 0)

    def test_idempotencia_y_restriccion_postgresql(self):
        first = self.save()
        second = self.save()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data, second.data)
        self.assertEqual(Favorito.objects.count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Favorito.objects.create(usuario=self.one, convocatoria=self.offer)

    def test_separacion_propietarios(self):
        first = self.save().data["id"]
        self.login(self.two)
        self.assertEqual(self.client.get("/api/favoritos/").data["count"], 0)
        self.assertIsNone(self.client.get(f"/api/becas/{self.offer.pk}/").data["favorito_id"])
        self.assertEqual(self.remove(first).status_code, 404)
        self.assertEqual(self.save(usuario=self.one.pk).status_code, 400)
        second = self.save().data["id"]
        self.assertNotEqual(first, second)
        self.assertEqual(Favorito.objects.count(), 2)

    def test_anonimo_y_administrador_rechazados(self):
        for user in (None, self.admin):
            self.client.logout()
            if user: self.login(user)
            else: self.token = self.client.get("/api/auth/csrf/").data["csrfToken"]
            self.assertEqual(self.client.get("/api/favoritos/").status_code, 403)
            self.assertEqual(self.save().status_code, 403)
            self.assertEqual(self.remove(1).status_code, 403)
            self.assertNotIn("favorito_id", self.client.get(f"/api/becas/{self.offer.pk}/").data)

    def test_csrf_en_guardar_y_quitar(self):
        pk = self.save().data["id"]
        for headers in ({}, {"HTTP_X_CSRFTOKEN": "incorrecto"}):
            self.assertEqual(self.client.post("/api/favoritos/", {"convocatoria": self.offer.pk}, format="json", **headers).status_code, 403)
            self.assertEqual(self.client.delete(f"/api/favoritos/{pk}/", **headers).status_code, 403)
        self.assertTrue(Favorito.objects.filter(pk=pk).exists())

    def test_oculta_no_se_agrega_y_guardada_no_filtra_datos(self):
        pk = self.save().data["id"]
        for changes in ({"activa": False}, {"activa": True, "revision": "pendiente"}):
            Convocatoria.objects.filter(pk=self.offer.pk).update(**changes)
            self.assertEqual(self.save().status_code, 404)
            row = self.client.get("/api/favoritos/").data["results"][0]
            self.assertEqual(row, {"id": pk, "disponible": False, "convocatoria": None, "aviso": "Esta oportunidad ya no está disponible."})
            self.assertNotIn(self.offer.titulo, str(row))
            self.assertNotIn(self.offer.url_oficial, str(row))
        self.assertEqual(self.remove(pk).status_code, 204)

    def test_paginacion_campos_y_metodos(self):
        pk = self.save().data["id"]
        self.assertEqual(self.client.get("/api/favoritos/?page_size=1&page=2").data["results"], [])
        for params in ("page=0", "page_size=51", "usuario=1", "page=1&page=2"):
            self.assertEqual(self.client.get("/api/favoritos/?"+params).status_code, 400)
        for data in ({"id": pk}, {"creado_en": "2020-01-01"}, {"convocatoria": 99999}, {"convocatoria": 0}):
            self.assertIn(self.save(**data).status_code, [400, 404])
        self.assertEqual(self.remove(pk, {"usuario": self.one.pk}).status_code, 400)
        self.assertEqual(self.client.get(f"/api/favoritos/{pk}/").status_code, 405)

    def test_persiste_tras_logout_login_y_permite_cerradas_publicas(self):
        Convocatoria.objects.filter(pk=self.offer.pk).update(cierre=timezone.now()-timedelta(days=1))
        pk = self.save().data["id"]
        self.client.post("/api/auth/logout/", {}, format="json", HTTP_X_CSRFTOKEN=self.token)
        token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        response = self.client.post("/api/auth/login/", {"email": self.one.email, "password": "Testing-Favoritos-75!"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        row = self.client.get("/api/favoritos/").data["results"][0]
        self.assertEqual(row["id"], pk)
        self.assertEqual(row["convocatoria"]["estado"], "cerrada")
