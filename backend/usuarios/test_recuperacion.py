"""Recuperación de contraseña de postulantes: respuesta genérica, token de Django, límites, envío aislado de la cola."""
import re
import smtplib
import threading
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core import mail
from django.core.cache import caches
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from notificaciones.models import EntregaCorreo, Notificacion
from . import recuperacion
from .models import Usuario

PASSWORD = "Pruebas!Rio-7392-Fuerte"
NUEVA = "Otra!Clave-5821-Segura"
RATES = {"registro": "100/hour", "login": "100/minute", "recuperacion_ip": "100/hour", "recuperacion_correo": "100/hour", "restablecer": "100/hour"}
BASE = "http://127.0.0.1:5173"


def sincrono(correo):
    recuperacion._enviar(correo)


@override_settings(AUTH_THROTTLE_RATES=RATES, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   BECANEXO_PUBLIC_BASE_URL=BASE, PASSWORD_RESET_TIMEOUT=3600)
@patch("usuarios.recuperacion.despachar", side_effect=sincrono)
class RecuperacionTests(TestCase):
    def setUp(self):
        caches["auth_throttle"].clear()
        self.addCleanup(caches["auth_throttle"].clear)
        self.postulante = Usuario.objects.create_user("ana@example.com", "Ana", PASSWORD)
        self.admin = Usuario.objects.create_user("admin@example.com", "Admin", PASSWORD, rol="administrador")
        self.inactivo = Usuario.objects.create_user("inactivo@example.com", "Inactivo", PASSWORD, is_active=False)
        self.client = self.nuevo_cliente()

    def nuevo_cliente(self):
        client = APIClient(enforce_csrf_checks=True)
        client.csrf = client.get("/api/auth/csrf/").json()["csrfToken"]
        return client

    def post(self, endpoint, data, client=None, **extra):
        client = client or self.client
        return client.post(f"/api/auth/{endpoint}/", data, format="json", HTTP_X_CSRFTOKEN=client.csrf, **extra)

    def solicitar(self, email, **extra):
        return self.post("recuperar-contrasena", {"email": email}, **extra)

    def enlace_del_correo(self):
        self.assertEqual(len(mail.outbox), 1)
        m = re.search(r"/restablecer-contrasena#uid=([^&\s]+)&token=(\S+)", mail.outbox[-1].body)
        self.assertIsNotNone(m)
        return m.group(1), m.group(2)

    def restablecer(self, uid, token, password=NUEVA, confirm=None, client=None):
        return self.post("restablecer-contrasena", {"uid": uid, "token": token, "password": password,
                                                    "password_confirm": password if confirm is None else confirm}, client=client)

    def login(self, password, client=None):
        return self.post("login", {"email": "ana@example.com", "password": password}, client=client)

    # --- Solicitud ---------------------------------------------------------------------------------------------

    def test_respuesta_identica_y_solo_envia_a_postulantes_activos(self, _):
        respuestas = [self.solicitar(email) for email in
                      ("ana@example.com", "nadie@example.com", "admin@example.com", "inactivo@example.com", " ANA@EXAMPLE.COM ")]
        for r in respuestas:
            self.assertEqual((r.status_code, r.json()), (200, {"detail": recuperacion.MENSAJE_SOLICITUD}))
        self.assertEqual([m.to for m in mail.outbox], [["ana@example.com"], ["ana@example.com"]])

    def test_correo_con_enlace_vigencia_y_aviso(self, _):
        self.solicitar("ana@example.com")
        correo = mail.outbox[0]
        self.assertEqual(correo.subject, "Restablece tu contraseña de BecaNexo")
        self.assertIn(f"{BASE}/restablecer-contrasena#uid=", correo.body)
        self.assertIn("El enlace vale 60 minutos", correo.body)
        self.assertIn("Si no fuiste tú, ignora este mensaje: tu contraseña no cambia.", correo.body)
        self.assertNotIn(PASSWORD, correo.body)
        self.assertNotIn("Ana", correo.body)  # sin datos innecesarios

    def test_correo_invalido_o_campos_extra_400(self, _):
        self.assertEqual(self.solicitar("no-es-correo").status_code, 400)
        self.assertEqual(self.post("recuperar-contrasena", {"email": "ana@example.com", "rol": "x"}).status_code, 400)
        self.assertEqual(mail.outbox, [])

    def test_fallo_del_envio_no_cambia_la_respuesta(self, _):
        with patch("django.core.mail.EmailMessage.send", side_effect=smtplib.SMTPException("fallo simulado")), \
                self.assertLogs("usuarios.recuperacion", level="WARNING") as logs:
            r = self.solicitar("ana@example.com")
        self.assertEqual((r.status_code, r.json()), (200, {"detail": recuperacion.MENSAJE_SOLICITUD}))
        self.assertTrue(all("token" not in l and "restablecer-contrasena#" not in l for l in logs.output))

    def test_no_toca_la_cola_de_avisos(self, _):
        self.solicitar("ana@example.com")
        self.assertEqual((EntregaCorreo.objects.count(), Notificacion.objects.count()), (0, 0))

    # --- Confirmación ------------------------------------------------------------------------------------------

    def test_enlace_cambia_la_contrasena_un_solo_uso_y_sin_iniciar_sesion(self, _):
        self.solicitar("ana@example.com")
        uid, token = self.enlace_del_correo()
        r = self.restablecer(uid, token)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)  # no inicia sesión
        self.assertEqual(self.login(PASSWORD).status_code, 400)  # la anterior ya no vale
        self.assertEqual(self.login(NUEVA, client=self.nuevo_cliente()).status_code, 200)
        otra = self.restablecer(uid, token, password="Tercera!Clave-4417-Larga", client=self.nuevo_cliente())
        self.assertEqual((otra.status_code, otra.json()["codigo"]), (400, "enlace_invalido"))

    def test_sesiones_previas_quedan_invalidadas(self, _):
        abierta = self.nuevo_cliente()
        r = self.login(PASSWORD, client=abierta)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(abierta.get("/api/auth/me/").status_code, 200)
        self.solicitar("ana@example.com")
        self.assertEqual(self.restablecer(*self.enlace_del_correo()).status_code, 200)
        self.assertEqual(abierta.get("/api/auth/me/").status_code, 403)

    def test_token_vence(self, _):
        self.solicitar("ana@example.com")
        uid, token = self.enlace_del_correo()
        futuro = PasswordResetTokenGenerator._now(default_token_generator) + timedelta(minutes=61)
        with patch.object(PasswordResetTokenGenerator, "_now", return_value=futuro):
            r = self.restablecer(uid, token)
        self.assertEqual((r.status_code, r.json()["codigo"]), (400, "enlace_invalido"))
        self.assertTrue(Usuario.objects.get(pk=self.postulante.pk).check_password(PASSWORD))

    def test_token_alterado_uid_invalido_y_cuentas_no_admitidas(self, _):
        self.solicitar("ana@example.com")
        uid, token = self.enlace_del_correo()
        casos = [(uid, token[:-1] + ("0" if token[-1] != "0" else "1")), ("no-es-uid", token), (urlsafe_base64_encode(b"999999"), token),
                 (urlsafe_base64_encode(force_bytes(self.admin.pk)), default_token_generator.make_token(self.admin)),
                 (urlsafe_base64_encode(force_bytes(self.inactivo.pk)), default_token_generator.make_token(self.inactivo))]
        for u, t in casos:
            with self.subTest(uid=u):
                r = self.restablecer(u, t)
                self.assertEqual((r.status_code, r.json()), (400, {"detail": recuperacion.MENSAJE_ENLACE_INVALIDO, "codigo": "enlace_invalido"}))
        self.assertTrue(Usuario.objects.get(pk=self.admin.pk).check_password(PASSWORD))

    def test_contrasena_debil_o_distinta_rechazada(self, _):
        self.solicitar("ana@example.com")
        uid, token = self.enlace_del_correo()
        for password, confirm, campo in (("12345678", None, "password"), ("corta", None, "password"), ("ana@example.com", None, "password"),
                                         (NUEVA, NUEVA + "x", "password_confirm")):
            with self.subTest(password=password):
                r = self.restablecer(uid, token, password, confirm)
                self.assertEqual(r.status_code, 400)
                self.assertIn(campo, r.json())
        self.assertTrue(Usuario.objects.get(pk=self.postulante.pk).check_password(PASSWORD))
        self.assertEqual(self.restablecer(uid, token).status_code, 200)  # el enlace seguía vigente

    # --- Límites -----------------------------------------------------------------------------------------------

    @override_settings(AUTH_THROTTLE_RATES={**RATES, "recuperacion_correo": "2/hour"})
    def test_limite_por_correo(self, _):
        for _ in range(2):
            self.assertEqual(self.solicitar("nadie@example.com").status_code, 200)
        r = self.solicitar("NADIE@example.com ")
        self.assertEqual(r.status_code, 429)
        self.assertNotIn("nadie", str(r.json()).lower())
        self.assertEqual(self.solicitar("otra@example.com").status_code, 200)  # otro correo sigue permitido

    @override_settings(AUTH_THROTTLE_RATES={**RATES, "recuperacion_ip": "3/hour"})
    def test_limite_por_ip(self, _):
        for n in range(3):
            self.assertEqual(self.solicitar(f"correo{n}@example.com").status_code, 200)
        self.assertEqual(self.solicitar("correo9@example.com").status_code, 429)
        self.assertEqual(self.solicitar("correo9@example.com", REMOTE_ADDR="10.0.0.9").status_code, 200)

    @override_settings(AUTH_THROTTLE_RATES={**RATES, "restablecer": "2/hour"})
    def test_limite_de_confirmacion(self, _):
        for _ in range(2):
            self.assertEqual(self.restablecer("x", "y").status_code, 400)
        self.assertEqual(self.restablecer("x", "y").status_code, 429)


@override_settings(AUTH_THROTTLE_RATES=RATES, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   BECANEXO_PUBLIC_BASE_URL=BASE)
class EnvioEnSegundoPlanoTests(TestCase):
    def test_envio_real_en_hilo_aparte(self):
        caches["auth_throttle"].clear()
        Usuario.objects.create_user("ana@example.com", "Ana", PASSWORD)
        client = APIClient(enforce_csrf_checks=True)
        token = client.get("/api/auth/csrf/").json()["csrfToken"]
        r = client.post("/api/auth/recuperar-contrasena/", {"email": "ana@example.com"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 200)
        for hilo in [t for t in threading.enumerate() if t.name == "becanexo-restablecer-contrasena"]:
            hilo.join(timeout=10)
        self.assertEqual(len(mail.outbox), 1)
