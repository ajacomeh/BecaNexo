"""Vectores semánticos guardados de las convocatorias y «Becas similares».

Mismo embedding y misma composición del texto que «Para ti · IA» (`vector_convocatoria(texto_convocatoria(c))`),
para que ambos resultados usen un solo criterio. Solo texto público: no depende del perfil de quien consulta.
"""
import hashlib
import logging

import numpy as np
from django.utils import timezone

from . import models as m
from .recomendaciones import texto_convocatoria
from .semantica import ModeloNoDisponible, vector_convocatoria

logger = logging.getLogger(__name__)

# Identifica el modelo y la forma de calcular el vector (archivo ONNX, pooling y truncado de semantica.py).
VERSION_MODELO = "paraphrase-multilingual-MiniLM-L12-v2/onnx-quint8-avx2/mean-pooling/128"
# Similitud coseno mínima. Entre las 55 convocatorias públicas reales (27/11/2026) la mediana de los pares es 0,57:
# por debajo de 0,65 casi todo coincide solo en lo genérico («beca», «programa»); desde 0,65 comparten tema.
UMBRAL_SIMILITUD = 0.65
MAX_SIMILARES = 4
VIGENTES = ("abierta", "cierre_hoy", "sin_fecha", "proxima")


def hash_texto(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def a_bytes(valores):
    return np.asarray(valores, dtype=np.float32).tobytes()


def de_bytes(datos):
    return np.frombuffer(bytes(datos), dtype=np.float32)


def guardar_vector(convocatoria, forzar=False):
    """Calcula y guarda el vector si falta o cambió el texto o el modelo. Devuelve 'calculado' o 'al_dia'.

    Propaga ModeloNoDisponible: quien llama decide si es un fallo tolerable.
    """
    texto = texto_convocatoria(convocatoria)
    huella = hash_texto(texto)
    actual = m.VectorConvocatoria.objects.filter(convocatoria=convocatoria).first()
    if not forzar and actual and actual.hash_texto == huella and actual.version_modelo == VERSION_MODELO:
        return "al_dia"
    datos = a_bytes(vector_convocatoria(texto))
    m.VectorConvocatoria.objects.update_or_create(convocatoria=convocatoria, defaults={
        "vector": datos, "version_modelo": VERSION_MODELO, "hash_texto": huella, "actualizado_en": timezone.now()})
    return "calculado"


def actualizar_sin_bloquear(convocatoria_id):
    """Tras publicar: el cálculo es un extra; si el modelo falla o no está, se registra y la publicación sigue."""
    try:
        convocatoria = m.Convocatoria.objects.filter(pk=convocatoria_id).first()
        if convocatoria is not None:
            guardar_vector(convocatoria)
    except Exception:
        logger.warning("No se pudo calcular el vector de la convocatoria %s; se calculará con el comando de vectores.",
                       convocatoria_id, exc_info=True)


def similares(convocatoria, candidatas, limite=MAX_SIMILARES, umbral=UMBRAL_SIMILITUD):
    """Hasta `limite` convocatorias de `candidatas` (sin la propia) con similitud >= `umbral`.

    Solo usa vectores guardados del modelo vigente. Si falta el de la convocatoria consultada, se calcula y guarda
    una vez; si el modelo no está disponible, no hay similares. Las vigentes van antes que las cerradas; dentro de
    cada grupo, por similitud. Devuelve [(convocatoria, similitud)].
    """
    base = m.VectorConvocatoria.objects.filter(convocatoria=convocatoria, version_modelo=VERSION_MODELO).first()
    if base is None:
        try:
            guardar_vector(convocatoria)
        except ModeloNoDisponible:
            logger.warning("Sin vector para la convocatoria %s: el modelo local no está disponible.", convocatoria.pk)
            return []
        base = m.VectorConvocatoria.objects.get(convocatoria=convocatoria)
    filas = list(m.VectorConvocatoria.objects.filter(version_modelo=VERSION_MODELO, convocatoria__in=candidatas)
                 .exclude(convocatoria=convocatoria).values_list("convocatoria_id", "vector"))
    if not filas:
        return []
    matriz = np.stack([de_bytes(v) for _, v in filas])
    puntajes = matriz @ de_bytes(base.vector)
    elegidas = {pk: float(p) for (pk, _), p in zip(filas, puntajes) if p >= umbral}
    if not elegidas:
        return []
    objetos = {c.pk: c for c in candidatas.filter(pk__in=elegidas)}
    orden = sorted(objetos.values(), key=lambda c: (c.estado not in VIGENTES, -elegidas[c.pk], c.pk))
    return [(c, elegidas[c.pk]) for c in orden[:limite]]
