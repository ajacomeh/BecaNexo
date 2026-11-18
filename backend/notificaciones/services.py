"""Avisos internos posteriores a una publicación autorizada, sin inferencia semántica."""

import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from perfiles.models import Perfil
from convocatorias.comparacion import evaluar_convocatoria
from .models import Notificacion, PreferenciaCorreo, EntregaCorreo


logger = logging.getLogger(__name__)


def avisar_publicacion(convocatoria):
    from convocatorias.services import postulables
    if not postulables().filter(pk=convocatoria.pk).exists():
        return 0
    opciones = list(convocatoria.opciones.filter(activa=True).prefetch_related("paises"))
    if not opciones:
        return 0
    areas = set(convocatoria.areas.values_list("area_id", flat=True))
    creadas = 0
    usuarios = get_user_model().objects.filter(is_active=True, rol="postulante", perfil__isnull=False).order_by("id")
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
            usuario=usuario, convocatoria=convocatoria, defaults={"motivos": motivos})
        creadas += int(creada)
        # El correo se encola; SMTP nunca se usa en la solicitud de publicación.
        if (creada and settings.AVISOS_CORREO_HABILITADOS
                and not convocatoria.titulo.rstrip().endswith("(Ficticia)")
                and convocatoria.institucion_id
                and any(opcion["resultado"] == "cumple" for opcion in comparacion["opciones"])):
            try:
                with transaction.atomic():
                    if PreferenciaCorreo.objects.filter(usuario=usuario, habilitada=True).exists():
                        EntregaCorreo.objects.get_or_create(notificacion=aviso)
            except DatabaseError:
                # Un problema en la cola no revierte la notificación interna.
                logger.warning("No se pudo encolar un aviso de correo; la notificación interna se conservó.")
    return creadas
