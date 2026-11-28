"""Límites de intentos detrás de un proxy: con DJANGO_NUM_PROXIES se usa la IP real del cliente; sin él, como siempre."""
from django.core.cache import caches
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

RATES = {"registro": "100/hour", "login": "2/minute", "recuperacion_ip": "100/hour", "recuperacion_correo": "100/hour", "restablecer": "100/hour"}
PROXY = "10.0.0.1"


@override_settings(AUTH_THROTTLE_RATES=RATES)
class ProxyThrottleTests(TestCase):
    def setUp(self):
        caches["auth_throttle"].clear()
        self.addCleanup(caches["auth_throttle"].clear)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/auth/csrf/").json()["csrfToken"]

    def login(self, cliente):
        return self.client.post("/api/auth/login/", {}, format="json", HTTP_X_CSRFTOKEN=self.token,
                                REMOTE_ADDR=PROXY, HTTP_X_FORWARDED_FOR=cliente)

    @override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1})
    def test_con_un_proxy_el_limite_es_por_cliente_real(self):
        for _ in range(2):
            self.assertEqual(self.login("198.51.100.7").status_code, 400)
        self.assertEqual(self.login("198.51.100.7").status_code, 429)
        self.assertEqual(self.login("198.51.100.8").status_code, 400)  # otro cliente tras el mismo proxy no queda bloqueado
        # Lo que el cliente antepone a X-Forwarded-For no cambia su identidad: cuenta el último salto (el que añade el proxy).
        self.assertEqual(self.login("203.0.113.50, 198.51.100.7").status_code, 429)

    def test_sin_proxies_configurados_se_ignora_x_forwarded_for(self):
        for cliente in ("198.51.100.7", "198.51.100.8"):
            self.assertEqual(self.login(cliente).status_code, 400)
        self.assertEqual(self.login("198.51.100.9").status_code, 429)  # todos comparten la IP del proxy, como hoy
