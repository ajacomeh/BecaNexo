"""Avisos internos: beca publicada que coincide con el perfil y cierre próximo de una favorita. Sin inferencia semántica."""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from perfiles.models import Perfil
from convocatorias.comparacion import evaluar_convocatoria
from .models import Notificacion, PreferenciaCorreo, EntregaCorreo


logger = logging.getLogger(__name__)


def avisar_publicacion(convocatoria, destinatarios=None):
    """`destinatarios` (IDs de usuario) limita a quién se evalúa, para una prueba controlada; por omisión, a todos."""
    from convocatorias.services import postulables
    if not postulables().filter(pk=convocatoria.pk).exists():
        return 0
    opciones = list(convocatoria.opciones.filter(activa=True).prefetch_related("paises"))
    if not opciones:
        return 0
    areas = set(convocatoria.areas.values_list("area_id", flat=True))
    creadas = 0
    usuarios = get_user_model().objects.filter(is_active=True, rol="postulante", perfil__isnull=False).order_by("id")
    if destinatarios is not None:
        usuarios = usuarios.filter(pk__in=list(destinatarios))
    for usuario in usuarios.iterator():
        perfil = Perfil.objects.get(usuario=usuario)
        motivos = []
        interes = set(perfil.areas.values_list("area_id", flat=True)) | set(
            perfil.formaciones.exclude(area=None).values_list("area_id", flat=True))
        if areas & interes:
            motivos.append("área de estudio declarada")
        preferencias = set(perfil.preferencias.values_list("nivel", "modalidad"))
        if any((opcion.nivel, opcion.modalidad) in preferencias for opcion in opciones):
            motivos.append("nivel y modalidad preferidos")
        destinos = set(perfil.destinos.values_list("pais_id", flat=True))
        if destinos and any(destinos.intersection(p.pk for p in opcion.paises.all()) for opcion in opciones):
            motivos.append("destino de estudio preferido")
        if not motivos:
            continue
        comparacion = evaluar_convocatoria(usuario, convocatoria)
        if not any(opcion["resultado"] != "no_cumple" for opcion in comparacion["opciones"]):
            continue
        aviso, creada = Notificacion.objects.get_or_create(
            usuario=usuario, convocatoria=convocatoria, tipo="publicacion", defaults={"motivos": motivos})
        creadas += int(creada)
        if creada and settings.AVISOS_CORREO_HABILITADOS:
            encolar_correo(aviso)
    return creadas


def encolar_correo(aviso):
    """El correo refleja el aviso interno recién creado: mismo evento y mismo criterio, sin reglas propias.

    Solo se añade el consentimiento: se encola si la persona tiene el correo activado desde antes del aviso
    (nunca se envía el historial). La entrega es única por aviso. SMTP nunca se usa en la solicitud web.
    """
    try:
        with transaction.atomic():
            if PreferenciaCorreo.objects.filter(usuario_id=aviso.usuario_id, habilitada=True,
                                                actualizada_en__lte=aviso.creada_en).exists():
                return EntregaCorreo.objects.get_or_create(notificacion=aviso)[1]
    except DatabaseError:
        # Un problema en la cola no revierte la notificación interna.
        logger.warning("No se pudo encolar un aviso de correo; la notificación interna se conservó.")
    return False


# --- Cierre próximo de becas favoritas ------------------------------------------------------------------
VIGENTES_CIERRE = ("abierta", "cierre_hoy")  # cerradas, próximas y sin fecha no avisan


def texto_cierre(convocatoria):
    """«cierra el 30/11/2026 a las 17:00 (hora de Ecuador)», «cierra el 30/11/2026 · hora no informada» o «cierra hoy · hora no informada»."""
    if convocatoria.estado == "cierre_hoy":
        return "cierra hoy · hora no informada"
    if convocatoria.cierre:
        local = timezone.localtime(convocatoria.cierre)
        dia = "hoy" if local.date() == timezone.localdate() else f"el {local:%d/%m/%Y}"
        return f"cierra {dia} a las {local:%H:%M} (hora de Ecuador)"
    if convocatoria.cierre_dia:
        return f"cierra el {convocatoria.cierre_dia:%d/%m/%Y} · hora no informada"
    return None


def favoritos_por_cerrar(dias=None):
    """Favoritos de postulantes activos cuya beca pública y vigente cierra dentro de `dias` y aún sin aviso de cierre."""
    from convocatorias.services import publicas
    from favoritos.models import Favorito
    dias = settings.AVISOS_CIERRE_DIAS if dias is None else dias
    limite = timezone.now() + timedelta(days=dias)
    avisado = Notificacion.objects.filter(usuario=OuterRef("usuario"), convocatoria=OuterRef("convocatoria"), tipo="cierre_proximo")
    favoritos = (Favorito.objects.filter(usuario__is_active=True, usuario__rol="postulante", convocatoria__in=publicas())
                 .filter(Q(convocatoria__cierre__lte=limite)
                         | Q(convocatoria__cierre__isnull=True, convocatoria__cierre_dia__lte=timezone.localdate(limite)))
                 .exclude(Exists(avisado)).select_related("usuario", "convocatoria").order_by("id"))
    return [f for f in favoritos if f.convocatoria.estado in VIGENTES_CIERRE]


def generar_avisos_cierre(dias=None, dry_run=False):
    """Crea un aviso «cierre_proximo» por (usuario, convocatoria), una sola vez; su correo sigue la regla general."""
    candidatos = favoritos_por_cerrar(dias)
    resumen = {"candidatos": len(candidatos), "avisos": 0, "encolados": 0,
               "detalle": [(f.usuario_id, f.convocatoria_id, f.convocatoria.estado, texto_cierre(f.convocatoria)) for f in candidatos]}
    if dry_run:
        return resumen
    for favorito in candidatos:
        with transaction.atomic():
            aviso, creada = Notificacion.objects.get_or_create(
                usuario=favorito.usuario, convocatoria=favorito.convocatoria, tipo="cierre_proximo",
                defaults={"motivos": ["cierre próximo de una beca favorita"]})
        resumen["avisos"] += int(creada)
        if creada and settings.AVISOS_CORREO_HABILITADOS:
            resumen["encolados"] += int(encolar_correo(aviso))
    return resumen
