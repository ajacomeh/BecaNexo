"""v1.1: el correo refleja cada aviso interno de quien activó el correo, sin reglas de generación propias.

Correo en memoria (locmem); escribe solo en la base de pruebas aislada.
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from convocatorias.models import Convocatoria, ConvocatoriaArea, OpcionEstudio, OpcionPais, Requisito, TipoRequisito
from convocatorias.reglas import CONTRATOS
from . import tests as base
from .correo import MAX_INTENTOS, procesar_pendientes
from .models import EntregaCorreo, Notificacion, PreferenciaCorreo
from .services import avisar_publicacion, encolar_correo

BASE_URL = "http://127.0.0.1:5173"


@override_settings(AVISOS_CORREO_HABILITADOS=True, AVISOS_CORREO_MAX_POR_USUARIO=3,
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", BECANEXO_PUBLIC_BASE_URL=BASE_URL)
class CorreoReflejaAvisosTests(TestCase):
    setUpTestData = base.NotificacionesTests.__dict__["setUpTestData"]
    setUp = base.NotificacionesTests.setUp
    publicar = base.NotificacionesTests.publicar

    def oferta(self, n=0, titulo="Beca sintética"):
        """Como la de tests.py, con clave propia para publicar varias en una prueba."""
        offer = Convocatoria.objects.create(institucion=self.institution, titulo=titulo, descripcion="Solo pruebas",
            url_oficial="https://example.org/beca", cierre=timezone.now() + timedelta(days=30),
            clave_deduplicacion=f"{n:064d}", revision="pendiente")
        ConvocatoriaArea.objects.create(convocatoria=offer, area=self.area)
        option = OpcionEstudio.objects.create(convocatoria=offer, nivel="maestria", modalidad="virtual")
        OpcionPais.objects.create(opcion_estudio=option, pais=self.ec)
        Requisito.objects.create(convocatoria=offer, tipo_requisito=TipoRequisito.objects.get(codigo="EDAD"),
            texto_original="Hasta 25 años", valor_estructurado={"maximo": 25},
            operador=CONTRATOS["EDAD"][1], fecha_referencia=date(2026, 1, 1),
            modo_comprobacion="dato_declarado", obligatorio=True, validado=True)
        return offer

    def activar(self, user, habilitado=True):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        token = client.get("/api/auth/csrf/").data["csrfToken"]
        response = client.patch("/api/notificaciones/correo/", {"habilitado": habilitado}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)

    def test_aviso_interno_con_correo_activado_encola_una_entrega(self):
        # pref_user no tiene fecha de nacimiento: su compatibilidad es «desconocida», como la de los avisos reales.
        self.activar(self.pref_user)
        self.assertEqual(self.publicar(self.oferta()).status_code, 200)
        self.assertEqual(Notificacion.objects.count(), 2)
        entrega = EntregaCorreo.objects.get()
        self.assertEqual((entrega.notificacion.usuario_id, entrega.estado), (self.pref_user.pk, "pendiente"))

    def test_mismo_criterio_que_el_aviso_interno_sin_filtros_propios(self):
        # Antes el correo excluía las «(Ficticia)» y exigía «cumple»; ahora sigue al aviso interno.
        self.activar(self.area_user)
        self.activar(self.pref_user)
        self.assertEqual(self.publicar(self.oferta(titulo="Beca sintética (Ficticia)")).status_code, 200)
        self.assertEqual(set(EntregaCorreo.objects.values_list("notificacion_id", flat=True)),
                         set(Notificacion.objects.values_list("id", flat=True)))
        # Quien no recibe aviso interno (incumple o no coincide) tampoco recibe correo.
        self.activar(self.fail_user)
        self.activar(self.other_user)
        self.assertEqual(self.publicar(self.oferta(1)).status_code, 200)
        self.assertFalse(EntregaCorreo.objects.filter(notificacion__usuario__in=[self.fail_user, self.other_user]).exists())

    def test_sin_preferencia_o_desactivada_no_encola(self):
        PreferenciaCorreo.objects.create(usuario=self.pref_user, habilitada=False)  # area_user ni siquiera tiene fila
        self.assertEqual(self.publicar(self.oferta()).status_code, 200)
        self.assertEqual((Notificacion.objects.count(), EntregaCorreo.objects.count()), (2, 0))
        self.activar(self.area_user)
        self.activar(self.area_user, False)
        self.assertEqual(self.publicar(self.oferta(1)).status_code, 200)
        self.assertEqual((Notificacion.objects.count(), EntregaCorreo.objects.count()), (4, 0))

    def test_avisos_previos_a_la_activacion_no_generan_correo(self):
        self.assertEqual(self.publicar(self.oferta()).status_code, 200)
        antiguo = Notificacion.objects.get(usuario=self.area_user)
        self.activar(self.area_user)
        self.assertEqual(EntregaCorreo.objects.count(), 0)  # sin backfill al activar
        self.assertFalse(encolar_correo(antiguo))
        self.assertEqual(EntregaCorreo.objects.count(), 0)
        activada = PreferenciaCorreo.objects.get(usuario=self.area_user).actualizada_en
        self.activar(self.area_user)  # repetir «activado» no mueve la fecha de activación
        self.assertEqual(PreferenciaCorreo.objects.get(usuario=self.area_user).actualizada_en, activada)
        self.assertEqual(self.publicar(self.oferta(1)).status_code, 200)
        nuevo = EntregaCorreo.objects.get()
        self.assertNotEqual(nuevo.notificacion_id, antiguo.pk)
        # Desactivar y volver a activar deja fuera también lo que quedó en cola antes de la nueva activación.
        self.activar(self.area_user, False)
        self.activar(self.area_user)
        self.assertEqual(procesar_pendientes(limite=5)["omitidos"], 1)
        nuevo.refresh_from_db()
        self.assertEqual((nuevo.estado, nuevo.codigo_error), ("omitido", "anterior_a_la_activacion"))
        self.assertEqual(mail.outbox, [])

    @override_settings(AVISOS_CORREO_MAX_POR_USUARIO=2)
    def test_tope_por_usuario_difiere_el_exceso_a_la_siguiente_corrida(self):
        self.activar(self.area_user)
        self.activar(self.pref_user)
        for n in range(3):
            self.assertEqual(self.publicar(self.oferta(n)).status_code, 200)
        self.assertEqual(EntregaCorreo.objects.count(), 6)
        por_destinatario = lambda: {u.email: sum(u.email in m.to for m in mail.outbox) for u in (self.area_user, self.pref_user)}
        self.assertEqual(procesar_pendientes(limite=10)["enviados"], 4)
        self.assertEqual(por_destinatario(), {self.area_user.email: 2, self.pref_user.email: 2})
        self.assertEqual(EntregaCorreo.objects.filter(estado="pendiente").count(), 2)  # el exceso no se pierde
        self.assertEqual(procesar_pendientes(limite=10)["enviados"], 2)
        self.assertEqual(por_destinatario(), {self.area_user.email: 3, self.pref_user.email: 3})
        self.assertEqual(procesar_pendientes(limite=10)["enviados"], 0)
        self.assertEqual(EntregaCorreo.objects.filter(estado="enviado").count(), 6)

    def test_idempotencia_un_aviso_un_correo(self):
        self.activar(self.area_user)
        offer = self.oferta()
        self.assertEqual(self.publicar(offer).status_code, 200)
        aviso = Notificacion.objects.get(usuario=self.area_user)
        avisar_publicacion(offer)  # la creación del aviso es el evento; repetirla no crea otro
        self.assertFalse(encolar_correo(aviso))
        self.assertEqual(EntregaCorreo.objects.count(), 1)
        self.assertEqual(procesar_pendientes(limite=5)["enviados"], 1)
        self.assertEqual(procesar_pendientes(limite=5)["enviados"], 0)  # segunda corrida de la tarea
        self.assertFalse(encolar_correo(aviso))  # ni siquiera tras enviarse
        self.assertEqual(procesar_pendientes(limite=5)["enviados"], 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_destinatarios_limita_el_aviso_a_esas_cuentas(self):
        self.activar(self.area_user)
        self.activar(self.pref_user)
        offer = self.oferta()
        offer.revision, offer.activa = "validada", True
        offer.save(update_fields=["revision", "activa"])
        self.assertEqual(avisar_publicacion(offer, destinatarios=[self.pref_user.pk]), 1)
        self.assertEqual(list(Notificacion.objects.values_list("usuario_id", flat=True)), [self.pref_user.pk])
        self.assertEqual(list(EntregaCorreo.objects.values_list("notificacion__usuario_id", flat=True)), [self.pref_user.pk])

    def test_fallo_de_conexion_reintenta_con_limite_y_queda_visible(self):
        self.activar(self.area_user)
        self.assertEqual(self.publicar(self.oferta()).status_code, 200)
        item = EntregaCorreo.objects.get()
        with patch("notificaciones.correo.get_connection", side_effect=ConnectionRefusedError):
            self.assertEqual(procesar_pendientes(limite=5)["reintentos"], 1)
            item.refresh_from_db()
            self.assertEqual((item.estado, item.intentos, item.codigo_error), ("pendiente", 1, "conexion_smtp"))
            self.assertGreater(item.proximo_intento_en, timezone.now())  # espera, sin bucle en la misma corrida
            for _ in range(MAX_INTENTOS + 2):
                EntregaCorreo.objects.filter(pk=item.pk).update(proximo_intento_en=timezone.now() - timedelta(seconds=1))
                procesar_pendientes(limite=5)
        item.refresh_from_db()
        self.assertEqual((item.estado, item.intentos, item.codigo_error), ("fallido", MAX_INTENTOS, "conexion_smtp"))
        self.assertEqual(procesar_pendientes(limite=5)["enviados"], 0)
        self.assertEqual(mail.outbox, [])

    @override_settings(EMAIL_HOST_PASSWORD="clave-de-prueba-no-real")
    def test_contenido_del_correo(self):
        self.activar(self.area_user)
        offer = self.oferta()
        self.assertEqual(self.publicar(offer).status_code, 200)
        self.assertEqual(procesar_pendientes(limite=5)["enviados"], 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.area_user.email])
        self.assertEqual(message.subject, "BecaNexo · Nueva beca: Beca sintética")
        self.assertIn(f"{BASE_URL}/becas/{offer.pk}", message.body)
        self.assertIn(f"{BASE_URL}/notificaciones", message.body)
        self.assertIn("Para dejar de recibirlos, desactiva", message.body)
        self.assertIn("área de estudio declarada", message.body)
        for secreto in ("clave-de-prueba-no-real", self.pref_user.email, "fecha_nacimiento", "2005"):
            self.assertNotIn(secreto, message.body)
