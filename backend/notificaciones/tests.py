from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from convocatorias.models import Convocatoria, ConvocatoriaArea, Institucion, OpcionEstudio, OpcionPais, Requisito, TipoRequisito
from convocatorias.reglas import CONTRATOS
from perfiles.models import Area, Pais, Perfil, PerfilArea, Preferencia
from .models import Notificacion


class NotificacionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ec = Pais.objects.create(codigo="EC", nombre="Ecuador")
        cls.area = Area.objects.create(nombre="Ingeniería sintética")
        call_command("cargar_catalogos_convocatorias", verbosity=0)
        users = get_user_model().objects
        cls.admin = users.create_user(email="admin-notif@example.com", nombre="Admin prueba", password=None, rol="administrador")
        cls.area_user = users.create_user(email="area-notif@example.com", nombre="Área prueba", password=None)
        cls.pref_user = users.create_user(email="pref-notif@example.com", nombre="Preferencia prueba", password=None)
        cls.fail_user = users.create_user(email="fail-notif@example.com", nombre="Incumple prueba", password=None)
        cls.other_user = users.create_user(email="other-notif@example.com", nombre="Sin coincidencia", password=None)
        cls.inactive_user = users.create_user(email="inactive-notif@example.com", nombre="Inactivo", password=None, is_active=False)
        for user, birth in ((cls.area_user, date(2005, 1, 1)), (cls.pref_user, None),
                            (cls.fail_user, date(1980, 1, 1)), (cls.other_user, None),
                            (cls.inactive_user, date(2005, 1, 1)), (cls.admin, date(2005, 1, 1))):
            perfil = Perfil.objects.create(usuario=user, nacionalidad=cls.ec, fecha_nacimiento=birth)
            if user in (cls.area_user, cls.fail_user, cls.inactive_user, cls.admin):
                PerfilArea.objects.create(perfil=perfil, area=cls.area)
            if user == cls.pref_user:
                Preferencia.objects.create(perfil=perfil, nivel="maestria", modalidad="virtual")
        cls.institution = Institucion.objects.create(nombre="Entidad ecuatoriana sintética", sector="publico", pais=cls.ec)

    def setUp(self):
        self.assertIn(connection.settings_dict["NAME"], ("test_becanexo_db", "test_becanexo_fusion_db"))
        self.admin_client = APIClient(enforce_csrf_checks=True)
        self.admin_client.force_login(self.admin)
        self.csrf = self.admin_client.get("/api/auth/csrf/").data["csrfToken"]

    def oferta(self, with_option=True, with_rule=True):
        offer = Convocatoria.objects.create(institucion=self.institution, titulo="Beca sintética", descripcion="Solo pruebas",
            url_oficial="https://example.org/beca", cierre=timezone.now() + timedelta(days=30),
            clave_deduplicacion="n" * 64, revision="pendiente")
        ConvocatoriaArea.objects.create(convocatoria=offer, area=self.area)
        if with_option:
            option = OpcionEstudio.objects.create(convocatoria=offer, nivel="maestria", modalidad="virtual")
            OpcionPais.objects.create(opcion_estudio=option, pais=self.ec)
        if with_rule:
            Requisito.objects.create(convocatoria=offer, tipo_requisito=TipoRequisito.objects.get(codigo="EDAD"),
                texto_original="Hasta 25 años", valor_estructurado={"maximo": 25},
                operador=CONTRATOS["EDAD"][1], fecha_referencia=date(2026, 1, 1),
                modo_comprobacion="dato_declarado", obligatorio=True, validado=True)
        return offer

    def publicar(self, offer):
        return self.admin_client.post(f"/api/gestion/convocatorias/{offer.pk}/publicar/", {}, format="json",
                                      HTTP_X_CSRFTOKEN=self.csrf)

    def test_publicacion_autorizada_selecciona_interes_y_preferencia_sin_incumplir(self):
        offer = self.oferta()
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertEqual(self.publicar(offer).status_code, 200)
        self.assertEqual(set(Notificacion.objects.values_list("usuario_id", flat=True)),
                         {self.area_user.pk, self.pref_user.pk})
        self.assertEqual(Notificacion.objects.get(usuario=self.area_user).motivos, ["área de estudio declarada"])
        self.assertEqual(Notificacion.objects.get(usuario=self.pref_user).motivos, ["nivel y modalidad preferidos"])
        self.assertEqual(self.publicar(offer).status_code, 200)
        self.assertEqual(Notificacion.objects.count(), 2)
        offer.revision = "pendiente"
        offer.save(update_fields=["revision"])
        self.assertEqual(self.publicar(offer).status_code, 200)
        self.assertEqual(Notificacion.objects.count(), 2)

    def test_borrador_fallo_de_publicacion_y_rollback_no_crean_avisos(self):
        offer = self.oferta(with_option=False)
        self.assertEqual(self.publicar(offer).status_code, 400)
        self.assertEqual(Notificacion.objects.count(), 0)
        OpcionPais.objects.create(opcion_estudio=OpcionEstudio.objects.create(
            convocatoria=offer, nivel="maestria", modalidad="virtual"), pais=self.ec)
        with patch("notificaciones.services.avisar_publicacion", side_effect=RuntimeError("Fallo sintético")):
            with self.assertRaises(RuntimeError):
                self.publicar(offer)
        offer.refresh_from_db()
        self.assertEqual(offer.revision, "pendiente")
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertEqual(offer.eventos.filter(accion="publicar").count(), 0)

    def test_api_destinatario_lectura_csrf_y_oferta_pausada(self):
        offer = self.oferta()
        self.assertEqual(self.publicar(offer).status_code, 200)
        aviso = Notificacion.objects.get(usuario=self.area_user)
        anon = APIClient(enforce_csrf_checks=True)
        self.assertEqual(anon.get("/api/notificaciones/").status_code, 403)
        self.assertEqual(self.admin_client.get("/api/notificaciones/").status_code, 403)
        self.assertEqual(self.admin_client.post(f"/api/notificaciones/{aviso.pk}/leer/", {}, format="json",
                                                HTTP_X_CSRFTOKEN=self.csrf).status_code, 403)
        own = APIClient(enforce_csrf_checks=True)
        own.force_login(self.area_user)
        path = "/api/notificaciones/"
        data = own.get(path).data
        self.assertEqual((data["count"], data["no_leidas"], len(data["results"])), (1, 1, 1))
        self.assertEqual(data["results"][0]["convocatoria_id"], offer.pk)
        self.assertTrue(data["results"][0]["disponible"])
        self.assertEqual(own.get(f"/api/becas/{offer.pk}/").status_code, 200)
        self.assertEqual(own.get(path + "?page_size=21").status_code, 400)
        self.assertEqual(own.get(path + "?user=2").status_code, 400)
        self.assertEqual(own.get(path + "?page=2").data["results"], [])
        self.assertEqual(own.post(f"/api/notificaciones/{aviso.pk}/leer/", {}, format="json").status_code, 403)
        token = own.get("/api/auth/csrf/").data["csrfToken"]
        other = Notificacion.objects.get(usuario=self.pref_user)
        self.assertEqual(own.post(f"/api/notificaciones/{other.pk}/leer/", {}, format="json",
                                  HTTP_X_CSRFTOKEN=token).status_code, 404)
        self.assertEqual(own.post(f"/api/notificaciones/{aviso.pk}/leer/", {"usuario": self.pref_user.pk},
                                  format="json", HTTP_X_CSRFTOKEN=token).status_code, 400)
        first = own.post(f"/api/notificaciones/{aviso.pk}/leer/", {}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(first.status_code, 200)
        second = own.post(f"/api/notificaciones/{aviso.pk}/leer/", {}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(second.data["leida_en"], first.data["leida_en"])
        self.assertEqual(own.get(path).data["no_leidas"], 0)
        offer.activa = False
        offer.titulo = "Título administrativo no publicado"
        offer.save(update_fields=["activa", "titulo"])
        oculto = own.get(path).data["results"][0]
        self.assertFalse(oculto["disponible"])
        self.assertEqual(oculto["titulo"], "Convocatoria no disponible públicamente")
        self.assertEqual(own.get(f"/api/becas/{offer.pk}/").status_code, 404)
