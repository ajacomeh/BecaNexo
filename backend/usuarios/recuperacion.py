"""Recuperación de contraseña de postulantes por correo.

- El token es el de Django (`default_token_generator`): no se guarda en la base, caduca a los `PASSWORD_RESET_TIMEOUT`
  segundos y depende del hash de la contraseña y del último inicio de sesión, así que deja de valer tras el cambio.
- El enlace usa la URL pública del frontend (`BECANEXO_PUBLIC_BASE_URL`) y lleva uid y token en el fragmento (#),
  que el navegador no envía al servidor ni en cabeceras Referer.
- El correo sale en un hilo aparte, fuera de la cola de avisos: un fallo o una demora de Gmail no cambia la respuesta.
- Nunca se registran tokens ni enlaces.
"""
import logging
import threading
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import Usuario

logger = logging.getLogger(__name__)

MENSAJE_SOLICITUD = "Si el correo corresponde a una cuenta, te enviamos un enlace para restablecer la contraseña."
MENSAJE_ENLACE_INVALIDO = "El enlace no es válido o ya venció. Solicita uno nuevo."
RUTA_FRONTEND = "/restablecer-contrasena"


def destinatario(email):
    """Solo postulantes activos reciben el enlace; el resto obtiene la misma respuesta sin envío."""
    return Usuario.objects.filter(email__iexact=Usuario.objects.normalize_email(email), is_active=True,
                                  rol=Usuario.Rol.POSTULANTE).first()


def enlace(usuario):
    base = settings.BECANEXO_PUBLIC_BASE_URL
    partes = urlsplit(base)
    if partes.scheme not in ("http", "https") or not partes.netloc or partes.query or partes.fragment:
        raise ValueError("La URL pública de BecaNexo no es válida.")
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    return f"{base}{RUTA_FRONTEND}#uid={uid}&token={default_token_generator.make_token(usuario)}"


def mensaje(usuario):
    minutos = max(1, settings.PASSWORD_RESET_TIMEOUT // 60)
    cuerpo = render_to_string("usuarios/restablecer_contrasena.txt", {"enlace": enlace(usuario), "minutos": minutos})
    return EmailMessage("Restablece tu contraseña de BecaNexo", cuerpo, settings.DEFAULT_FROM_EMAIL, [usuario.email])


def _enviar(correo):
    try:
        if correo.send(fail_silently=False) != 1:
            raise RuntimeError("SMTP no confirmó el envío.")
    except Exception as exc:  # El detalle puede incluir el mensaje: solo se registra el tipo.
        logger.warning("No se pudo enviar el correo de restablecimiento de contraseña (%s).", type(exc).__name__)


def despachar(correo):
    """Envío en segundo plano: la solicitud responde sin esperar a Gmail (EMAIL_TIMEOUT acota el hilo)."""
    threading.Thread(target=_enviar, args=(correo,), name="becanexo-restablecer-contrasena", daemon=True).start()


def solicitar(email):
    usuario = destinatario(email)
    if usuario is not None:
        try:
            despachar(mensaje(usuario))
        except Exception as exc:
            logger.warning("No se pudo preparar el correo de restablecimiento de contraseña (%s).", type(exc).__name__)


def usuario_del_enlace(uid, token):
    """Postulante activo cuyo token es válido, o None (enlace inválido, vencido o ya usado)."""
    try:
        pk = int(force_str(urlsafe_base64_decode(uid)))
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError):
        return None
    usuario = Usuario.objects.filter(pk=pk, is_active=True, rol=Usuario.Rol.POSTULANTE).first()
    if usuario is None or not default_token_generator.check_token(usuario, token):
        return None
    return usuario
