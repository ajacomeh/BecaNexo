"""Solo para Playwright local: cuentas DEMO estables y sesiones en memoria.

No cambia cuentas existentes, no contiene contraseñas y no crea convocatorias.
Su salida debe capturarse en memoria por el test, nunca imprimirse en reportes.
"""
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from importlib import import_module
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY

assert settings.DATABASES["default"]["NAME"] == "becanexo_db", "Solo desarrollo local."
result = {}
for role in ("administrador", "postulante"):
    email = f"demo-catalogo-{role}@example.com"
    user = get_user_model().objects.filter(email=email).first()
    if user is None:
        user = get_user_model().objects.create_user(email=email, nombre=f"DEMOSTRACION catalogo {role}", password=None, rol=role)
    assert user.rol == role and user.is_active and not user.is_staff and not user.is_superuser and not user.has_usable_password(), "La cuenta preexistente no coincide con la fixture; no se modifica."
    # Sesión de fixture sin emitir la señal de login ni cambiar last_login del usuario.
    session = import_module(settings.SESSION_ENGINE).SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    result[role] = session.session_key
print(json.dumps(result))
