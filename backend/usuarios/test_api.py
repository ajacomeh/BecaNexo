from django.conf import settings
from django.core.cache import caches
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Usuario


PASSWORD = "Pruebas!Rio-7392-Fuerte"


@override_settings(AUTH_THROTTLE_RATES={"registro": "100/hour", "login": "100/minute"})
class AuthAPITests(TestCase):
    def setUp(self):
        caches["auth_throttle"].clear()
        self.addCleanup(caches["auth_throttle"].clear)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/auth/csrf/").json()["csrfToken"]
        self.data = {"nombre": "Ana", "email": "ana@example.com", "password": PASSWORD,
                     "password_confirm": PASSWORD}

    def post(self, endpoint, data=None, **extra):
        return self.client.post(f"/api/auth/{endpoint}/", data or {}, format="json",
                                HTTP_X_CSRFTOKEN=self.token, **extra)

    def user(self, **kwargs):
        return Usuario.objects.create_user("ana@example.com", "Ana", PASSWORD, **kwargs)

    def login(self):
        response = self.post("login", {"email": " ANA@EXAMPLE.COM ", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.token = response.json()["csrfToken"]
        return response

    def test_registro_hash_sin_sesion(self):
        response = self.post("registro", {**self.data, "email": " ANA@EXAMPLE.COM "})
        self.assertEqual(response.status_code, 201)
        user = Usuario.objects.get()
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertEqual(user.email, "ana@example.com")
        self.assertEqual(user.rol, "postulante")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(set(response.json()), {"id", "email", "nombre", "rol"})
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_validaciones_registro(self):
        for change in [{"password": "123", "password_confirm": "123"},
                       {"password_confirm": "diferente"}, {"email": "invalido"},
                       {"nombre": "  "}, {"email": ""}]:
            with self.subTest(change=list(change)):
                response = self.post("registro", {**self.data, **change})
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(PASSWORD, response.content.decode())
        self.assertFalse(Usuario.objects.exists())

    def test_duplicado_base_datos(self):
        # No hay preconsulta de existencia: se ejercita el IntegrityError real
        # que también produce la base ante dos altas concurrentes.
        self.user()
        response = self.post("registro", {**self.data, "email": " ANA@EXAMPLE.COM "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Usuario.objects.count(), 1)

    def test_privilegios_y_campos_desconocidos(self):
        for field in ["rol", "is_staff", "is_superuser", "is_active", "activo", "id",
                      "groups", "user_permissions", "password_hash", "creado_en"]:
            with self.subTest(field=field):
                self.assertEqual(self.post("registro", {**self.data, field: True}).status_code, 400)
        self.assertFalse(Usuario.objects.exists())

    def test_login_me_cookies_y_rotacion(self):
        user = self.user()
        old_token = self.token
        response = self.login()
        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertNotEqual(old_token, self.token)
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json(), {"id": user.pk, "email": user.email, "nombre": "Ana", "rol": "postulante"})
        for result in [response, me]:
            self.assertNotIn(user.password, result.content.decode())
            self.assertNotIn(PASSWORD, result.content.decode())
            self.assertIn("no-store", result["Cache-Control"])
        self.assertEqual(self.client.post("/api/auth/logout/", {}, format="json",
                                         HTTP_X_CSRFTOKEN=old_token).status_code, 403)
        self.assertEqual(self.post("logout").status_code, 204)

    def test_credenciales_genericas(self):
        user = self.user()
        responses = [self.post("login", {"email": "ausente@example.com", "password": PASSWORD}),
                     self.post("login", {"email": user.email, "password": "incorrecta"})]
        user.is_active = False
        user.save()
        responses.append(self.post("login", {"email": user.email, "password": PASSWORD}))
        for response in responses:
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {"detail": "Correo o contraseña incorrectos."})

    def test_me_y_logout_anonimos(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)
        self.assertEqual(self.post("logout").status_code, 403)

    def test_csrf_ausente_invalido_y_origen(self):
        self.user()
        for endpoint in ["registro", "login", "logout"]:
            if endpoint == "logout":
                self.login()
            for headers in [{}, {"HTTP_X_CSRFTOKEN": "invalido"},
                            {"HTTP_X_CSRFTOKEN": self.token, "HTTP_ORIGIN": "https://ajeno.example"}]:
                with self.subTest(endpoint=endpoint, headers=list(headers)):
                    response = self.client.post(f"/api/auth/{endpoint}/", self.data, format="json", **headers)
                    self.assertEqual(response.status_code, 403)
                    self.assertIn("no-store", response["Cache-Control"])

    def test_csrf_sin_cookie(self):
        for endpoint in ["registro", "login"]:
            client = APIClient(enforce_csrf_checks=True)
            self.assertEqual(client.post(f"/api/auth/{endpoint}/", self.data, format="json").status_code, 403)

    def test_logout_invalida_sesion(self):
        self.user()
        self.login()
        old_session = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        response = self.post("logout")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = old_session
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_metodos_no_permitidos(self):
        self.user()
        self.login()
        for endpoint in ["registro", "login", "logout"]:
            self.assertEqual(self.client.get(f"/api/auth/{endpoint}/").status_code, 405)
        for endpoint in ["csrf", "me"]:
            self.assertEqual(self.post(endpoint).status_code, 405)
        self.assertEqual(self.client.delete("/api/auth/login/", HTTP_X_CSRFTOKEN=self.token).status_code, 405)

    @override_settings(AUTH_THROTTLE_RATES={"registro": "2/hour", "login": "2/minute"})
    def test_limites_y_x_forwarded_for(self):
        for endpoint in ["registro", "login"]:
            for index in range(2):
                self.assertEqual(self.post(endpoint, {}, HTTP_X_FORWARDED_FOR=f"192.0.2.{index}").status_code, 400)
            response = self.post(endpoint, {}, HTTP_X_FORWARDED_FOR="192.0.2.99")
            self.assertEqual(response.status_code, 429)
            self.assertIn("Retry-After", response)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(self.post(endpoint, {}, REMOTE_ADDR="192.0.2.10").status_code, 400)

    def test_csrf_cookie_y_no_cache(self):
        response = self.client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.CSRF_COOKIE_NAME, response.cookies)
        self.assertIn("no-store", response["Cache-Control"])

    @override_settings(CSRF_TRUSTED_ORIGINS=["http://127.0.0.1:5173"])
    def test_origen_vite_conserva_exigencia_csrf(self):
        self.user()
        data = {"email": "ana@example.com", "password": PASSWORD}
        response = self.client.post("/api/auth/login/", data, format="json",
                                    HTTP_ORIGIN="http://127.0.0.1:5173")
        self.assertEqual(response.status_code, 403)
        response = self.post("login", data, HTTP_ORIGIN="http://127.0.0.1:5173")
        self.assertEqual(response.status_code, 200)
