"""Campo de conocimiento derivado (área única de la convocatoria) para las tarjetas de Favoritos y Notificaciones.

Escribe solo en la base de pruebas aislada.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from favoritos.models import Favorito
from notificaciones.models import Notificacion
from perfiles.models import Area, Pais
from . import models as m
from .services import campos_conocimiento


class CampoConocimientoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(email="campo@example.com", nombre="Postulante", password="Testing-Campo-76!")
        ec, _ = Pais.objects.get_or_create(codigo="EC", defaults={"nombre": "Ecuador"})
        cls.institution = m.Institucion.objects.create(nombre="DEMO campo", sector="privado", pais=ec)
        cls.salud = Area.objects.create(nombre="Salud y bienestar")
        cls.tic = Area.objects.create(nombre="Tecnologías de la información y la comunicación")

    def oferta(self, n, *areas):
        offer = m.Convocatoria.objects.create(institucion=self.institution, titulo=f"Oferta {n}", url_oficial="https://example.org/t",
                                              clave_deduplicacion=f"{n:064d}", revision="validada", cierre=timezone.now() + timedelta(days=30))
        for area in areas:
            m.ConvocatoriaArea.objects.create(convocatoria=offer, area=area)
        return offer

    def setUp(self):
        self.client = APIClient()
        self.client.force_login(self.user)

    def test_area_unica_varias_o_ninguna(self):
        unica, varias, ninguna = self.oferta(1, self.salud), self.oferta(2, self.salud, self.tic), self.oferta(3)
        self.assertEqual(campos_conocimiento([unica.pk, varias.pk, ninguna.pk]),
                         {unica.pk: "Salud y bienestar", varias.pk: None, ninguna.pk: None})
        for offer in (unica, varias, ninguna):
            Favorito.objects.create(usuario=self.user, convocatoria=offer)
            Notificacion.objects.create(usuario=self.user, convocatoria=offer)
        esperado = {"Oferta 1": "Salud y bienestar", "Oferta 2": None, "Oferta 3": None}
        favoritos = self.client.get("/api/favoritos/").data["results"]
        self.assertEqual({f["convocatoria"]["titulo"]: f["convocatoria"]["campo_conocimiento"] for f in favoritos}, esperado)
        avisos = self.client.get("/api/notificaciones/").data["results"]
        self.assertEqual({a["titulo"]: a["campo_conocimiento"] for a in avisos}, esperado)

    def test_no_disponible_no_expone_el_campo(self):
        offer = self.oferta(4, self.tic)
        Notificacion.objects.create(usuario=self.user, convocatoria=offer)
        offer.activa = False
        offer.save(update_fields=["activa"])
        aviso = self.client.get("/api/notificaciones/").data["results"][0]
        self.assertFalse(aviso["disponible"])
        self.assertIsNone(aviso["campo_conocimiento"])

    def test_las_consultas_no_crecen_con_el_numero_de_tarjetas(self):
        def consultas(path):
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get(path).status_code, 200)
            return len(ctx)
        offer = self.oferta(10, self.salud)
        Favorito.objects.create(usuario=self.user, convocatoria=offer)
        Notificacion.objects.create(usuario=self.user, convocatoria=offer)
        base = {path: consultas(path) for path in ("/api/favoritos/", "/api/notificaciones/")}
        for n in range(11, 17):
            offer = self.oferta(n, self.tic if n % 2 else self.salud)
            Favorito.objects.create(usuario=self.user, convocatoria=offer)
            Notificacion.objects.create(usuario=self.user, convocatoria=offer)
        for path, antes in base.items():
            self.assertEqual(consultas(path), antes, path)
