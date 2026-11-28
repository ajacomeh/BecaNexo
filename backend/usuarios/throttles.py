from django.conf import settings
from django.core.cache import caches
from django.utils.crypto import salted_hmac
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class AuthThrottle(SimpleRateThrottle):
    def __init__(self):
        self.cache = caches["auth_throttle"]
        super().__init__()

    def get_rate(self):
        return settings.AUTH_THROTTLE_RATES[self.scope]

    def client_address(self, request):
        # Sin proxies de confianza (por defecto) no se usa X-Forwarded-For: el cliente podría falsificarlo. Con
        # DJANGO_NUM_PROXIES, DRF toma la IP real de X-Forwarded-For contando esos proxies desde el final.
        if api_settings.NUM_PROXIES:
            return self.get_ident(request)
        return request.META.get("REMOTE_ADDR", "unknown")

    def get_cache_key(self, request, view):
        # La caché es local a cada proceso: con 2 procesos el límite efectivo se duplica (aceptable para el demo).
        ident = salted_hmac("auth-throttle", self.client_address(request)).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}


class RegistroThrottle(AuthThrottle):
    scope = "registro"


class LoginThrottle(AuthThrottle):
    scope = "login"


class RecuperacionIPThrottle(AuthThrottle):
    scope = "recuperacion_ip"


class RecuperacionCorreoThrottle(AuthThrottle):
    """Por correo solicitado (normalizado y con HMAC: la caché no guarda direcciones). Cuenta también correos inexistentes."""
    scope = "recuperacion_correo"

    def get_cache_key(self, request, view):
        email = request.data.get("email") if isinstance(request.data, dict) else None
        if not isinstance(email, str) or not email.strip():
            return None  # sin correo no hay envío; el límite por IP sigue aplicando
        ident = salted_hmac("recuperacion-correo", email.strip().lower()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}


class RestablecerThrottle(AuthThrottle):
    scope = "restablecer"
