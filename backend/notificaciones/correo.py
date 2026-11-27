"""Entrega diferida de avisos, sin bloquear la publicación ni inferir elegibilidad."""
import smtplib
import socket
from collections import Counter
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from convocatorias.services import publicas
from .models import EntregaCorreo, PreferenciaCorreo

MAX_INTENTOS = 3


def _enlace(ruta):
    base = settings.BECANEXO_PUBLIC_BASE_URL
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("La URL pública de BecaNexo no es válida.")
    return f"{base}{ruta}"


def enlace_detalle(pk):
    return _enlace(f"/becas/{pk}")


def motivo_omision(aviso):
    """Condiciones de entrega, no de generación: el aviso interno ya decidió el evento y la coincidencia."""
    user = aviso.usuario
    if not user.is_active or user.rol != "postulante":
        return "cuenta_no_activa"
    preferencia = PreferenciaCorreo.objects.filter(usuario=user, habilitada=True).first()
    if preferencia is None:
        return "sin_consentimiento"
    if aviso.creada_en < preferencia.actualizada_en:
        # Desactivó y volvió a activar el correo: lo anterior a la nueva activación no se envía.
        return "anterior_a_la_activacion"
    if not publicas().filter(pk=aviso.convocatoria_id).exists():
        # Igual que la bandeja: un aviso de una convocatoria que dejó de ser pública no se ofrece.
        return "oferta_no_publica"
    if aviso.tipo == "cierre_proximo" and aviso.convocatoria.estado not in ("abierta", "cierre_hoy"):
        # Avisar de un cierre ya ocurrido confundiría; el aviso interno sigue en la bandeja.
        return "oferta_ya_cerrada"
    return ""


def mensaje(aviso):
    offer = aviso.convocatoria
    if aviso.tipo == "cierre_proximo":
        from .services import texto_cierre
        body = render_to_string("notificaciones/cierre_proximo.txt", {
            "nombre": aviso.usuario.nombre,
            "titulo": offer.titulo,
            "institucion": offer.institucion.nombre if offer.institucion_id else None,
            "cierre": texto_cierre(offer),
            "enlace": enlace_detalle(offer.pk),
            "enlace_avisos": _enlace("/notificaciones"),
        })
        return EmailMessage(f"BecaNexo · Cierre próximo: {offer.titulo}", body,
                            settings.DEFAULT_FROM_EMAIL, [aviso.usuario.email])
    cierre = offer.cierre_dia or (timezone.localtime(offer.cierre).date() if offer.cierre else None)
    body = render_to_string("notificaciones/nueva_beca.txt", {
        "nombre": aviso.usuario.nombre,
        "titulo": offer.titulo,
        "institucion": offer.institucion.nombre if offer.institucion_id else None,
        "cierre": cierre.strftime("%d/%m/%Y") if cierre else None,
        "motivos": aviso.motivos,
        "enlace": enlace_detalle(offer.pk),
        "enlace_avisos": _enlace("/notificaciones"),
    })
    return EmailMessage(f"BecaNexo · Nueva beca: {offer.titulo}", body,
                        settings.DEFAULT_FROM_EMAIL, [aviso.usuario.email])


def procesar_pendientes(limite=10, solo_id=None):
    """Los resultados SMTP indeterminados quedan retenidos; nunca se reenvían solos.

    Como máximo `AVISOS_CORREO_MAX_POR_USUARIO` intentos por destinatario en cada ejecución; el exceso sigue
    pendiente, en orden, para la siguiente.
    """
    resumen = {"enviados": 0, "reintentos": 0, "fallidos": 0, "omitidos": 0}
    tope = settings.AVISOS_CORREO_MAX_POR_USUARIO
    intentos_por_usuario = Counter()
    # Una caída del proceso puede dejar el resultado SMTP incierto. Se registra
    # como fallido tras el plazo de seguridad, sin devolverlo a la cola.
    resumen["fallidos"] += EntregaCorreo.objects.filter(
        estado="enviando", actualizado_en__lt=timezone.now() - timedelta(minutes=30)
    ).update(estado="fallido", codigo_error="resultado_indeterminado", actualizado_en=timezone.now())
    for _ in range(limite):
        with transaction.atomic():
            qs = EntregaCorreo.objects.select_for_update(skip_locked=True, of=("self",)).filter(
                estado="pendiente", proximo_intento_en__lte=timezone.now()).exclude(
                notificacion__usuario_id__in=[u for u, n in intentos_por_usuario.items() if n >= tope]
            ).order_by("proximo_intento_en", "id")
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
            intentos_por_usuario[item.notificacion.usuario_id] += 1
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
