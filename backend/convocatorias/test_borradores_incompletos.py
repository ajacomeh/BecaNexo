"""Reproducción: borradores con campos de alcance vacíos.

El formulario React envía null para un campo de texto vacío sin `required` ni `blank`
(OfferForm.jsx). Estas pruebas caracterizan cómo responde la API a ese contrato.
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from perfiles.models import Pais
from . import models as m

ALCANCE = ("alcance_detalle", "alcance_exclusiones", "alcance_sede", "alcance_periodo")


class BorradorAlcanceVacioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user(
            email="admin-borrador@example.com", password="Testing-Only-74!",
            nombre="Administrador sintético", rol="administrador")
        cls.ec, _ = Pais.objects.get_or_create(codigo="EC", defaults={"nombre": "Ecuador"})
        call_command("cargar_catalogos_convocatorias", verbosity=0)
        cls.institution = m.Institucion.objects.create(nombre="DEMO sintética", sector="publico", pais=cls.ec)

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.admin)
        self.token = self.client.get("/api/auth/csrf/").data["csrfToken"]

    def post(self, **extra):
        data = {"titulo": "Borrador sintético", "institucion": self.institution.pk,
                "alcance_academico": "pendiente", **extra}
        return self.client.post("/api/gestion/convocatorias/", data, format="json",
                                HTTP_X_CSRFTOKEN=self.token)

    def test_alcance_nulo_como_lo_envia_el_formulario_se_rechaza(self):
        response = self.post(**{field: None for field in ALCANCE})
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(set(response.data), set(ALCANCE))
        self.assertEqual(m.Convocatoria.objects.count(), 0)

    def test_alcance_vacio_como_cadena_se_admite_en_borrador(self):
        response = self.post(**{field: "" for field in ALCANCE})
        self.assertEqual(response.status_code, 201, response.data)
        offer = m.Convocatoria.objects.get(pk=response.data["id"])
        self.assertEqual(offer.revision, "pendiente")
        self.assertTrue(all(getattr(offer, field) == "" for field in ALCANCE))

    def test_alcance_omitido_se_admite_en_borrador(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
