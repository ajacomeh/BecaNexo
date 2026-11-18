"""Entrega diferida de avisos, sin bloquear la publicación ni inferir elegibilidad."""
import smtplib
import socket
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from convocatorias.comparacion import evaluar_convocatoria
from convocatorias.services import postulables
from .models import EntregaCorreo, PreferenciaCorreo

MAX_INTENTOS = 3


def enlace_detalle(pk):
    base = settings.BECANEXO_PUBLIC_BASE_URL
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("La URL pública de BecaNexo no es válida.")
    return f"{base}/becas/{pk}"


def motivo_omision(aviso):
    user, offer = aviso.usuario, aviso.convocatoria
    if not user.is_active or user.rol != "postulante":
        return "cuenta_no_activa"
    if not PreferenciaCorreo.objects.filter(usuario=user, habilitada=True).exists():
        return "sin_consentimiento"
    if (offer.titulo.rstrip().endswith("(Ficticia)") or not offer.institucion_id
            or offer.institucion.pais.codigo != "EC"):
        return "oferta_no_real_confirmada"
    if not postulables().filter(pk=offer.pk).exists():
        return "oferta_no_postulable"
    if not aviso.motivos:
        return "sin_coincidencia_declarada"
    comparison = evaluar_convocatoria(user, offer)
    if not any(option["resultado"] == "cumple" for option in comparison["opciones"]):
        return "compatibilidad_no_confirmada"
    return ""


def mensaje(aviso):
    offer = aviso.convocatoria
    cierre = offer.cierre_dia or (timezone.localtime(offer.cierre).date() if offer.cierre else None)
    body = render_to_string("notificaciones/nueva_beca.txt", {
        "nombre": aviso.usuario.nombre,
        "titulo": offer.titulo,
        "institucion": offer.institucion.nombre,
        "cierre": cierre.strftime("%d/%m/%Y") if cierre else None,
        "motivos": aviso.motivos,
        "enlace": enlace_detalle(offer.pk),
    })
    return EmailMessage(f"BecaNexo · Nueva beca: {offer.titulo}", body,
                        settings.DEFAULT_FROM_EMAIL, [aviso.usuario.email])


def procesar_pendientes(limite=10, solo_id=None):
    """Los resultados SMTP indeterminados quedan retenidos; nunca se reenvían solos."""
    resumen = {"enviados": 0, "reintentos": 0, "fallidos": 0, "omitidos": 0}
    # Una caída del proceso puede dejar el resultado SMTP incierto. Se registra
    # como fallido tras el plazo de seguridad, sin devolverlo a la cola.
    resumen["fallidos"] += EntregaCorreo.objects.filter(
        estado="enviando", actualizado_en__lt=timezone.now() - timedelta(minutes=30)
    ).update(estado="fallido", codigo_error="resultado_indeterminado", actualizado_en=timezone.now())
    for _ in range(limite):
        with transaction.atomic():
            qs = EntregaCorreo.objects.select_for_update(skip_locked=True).filter(
                estado="pendiente", proximo_intento_en__lte=timezone.now()).order_by("proximo_intento_en", "id")
            if solo_id is not None:
                qs = qs.filter(pk=solo_id)
            item = qs.select_related("notificacion__usuario", "notificacion__convocatoria").first()
            if item is None:
                break
            error = motivo_omision(item.notificacion)
            if error:
                item.estado, item.codigo_error = "omitido", error
                item.actualizado_en = timezone.now()
                item.save(update_fields=["estado", "codigo_error", "actualizado_en"])
                resumen["omitidos"] += 1
                continue
            item.estado = "enviando"
            item.intentos += 1
            item.actualizado_en = timezone.now()
            item.save(update_fields=["estado", "intentos", "actualizado_en"])
            pk = item.pk

        # La transacción terminó antes de abrir una conexión de red.
        connection = None
        try:
            email = mensaje(item.notificacion)
            connection = get_connection()
            connection.open()
        except (smtplib.SMTPConnectError, ConnectionRefusedError, TimeoutError, socket.gaierror):
            if connection is not None:
                connection.close()
            with transaction.atomic():
                item = EntregaCorreo.objects.select_for_update().get(pk=pk)
                item.estado = "pendiente" if item.intentos < MAX_INTENTOS else "fallido"
                item.codigo_error = "conexion_smtp"
                item.proximo_intento_en = timezone.now() + timedelta(minutes=15 * 2 ** (item.intentos - 1))
                item.actualizado_en = timezone.now()
                item.save(update_fields=["estado", "codigo_error", "proximo_intento_en", "actualizado_en"])
                resumen["reintentos" if item.estado == "pendiente" else "fallidos"] += 1
            continue
        except Exception:
            # Error de configuración o resultado indeterminado: no reintentar automáticamente.
            if connection is not None:
                connection.close()
            EntregaCorreo.objects.filter(pk=pk, estado="enviando").update(
                estado="fallido", codigo_error="preparacion", actualizado_en=timezone.now())
            resumen["fallidos"] += 1
            continue
        try:
            if motivo_omision(item.notificacion):
                EntregaCorreo.objects.filter(pk=pk, estado="enviando").update(
                    estado="omitido", codigo_error="condiciones_cambiaron", actualizado_en=timezone.now())
                resumen["omitidos"] += 1
                continue
            email.connection = connection
            if email.send(fail_silently=False) != 1:
                raise RuntimeError("SMTP no confirmó el envío.")
            EntregaCorreo.objects.filter(pk=pk, estado="enviando").update(
                estado="enviado", enviado_en=timezone.now(), codigo_error="", actualizado_en=timezone.now())
            resumen["enviados"] += 1
        except Exception:
            # El servidor pudo aceptar el mensaje: evitar un segundo envío automático.
            EntregaCorreo.objects.filter(pk=pk, estado="enviando").update(
                estado="fallido", codigo_error="resultado_indeterminado", actualizado_en=timezone.now())
            resumen["fallidos"] += 1
        finally:
            if connection is not None:
                connection.close()
    return resumen
