"""Sugerencias para completar y revisar borradores: nivel, tipo de beca y posibles duplicados.

Solo sugiere: no guarda nada, no publica y no cambia borradores, requisitos ni elegibilidad. Todo se calcula al consultar;
el vector de un borrador se calcula en memoria y no se guarda. Si no hay una sugerencia fiable, no se sugiere nada.

Calibración con datos reales (27/11/2026, «dejar uno fuera» sobre las publicadas):
- Nivel por reglas (texto con una sola familia de nivel; «bachillerato» excluido porque suele ser un requisito): ver
  docs/recomendacion-semantica.md.
- Nivel por vecinos: k=3, similitud ≥ 0,85 y unanimidad → 8 de 8 aciertos (con k=1 la precisión era 61–70 %).
- Tipo de beca: ninguna publicada tiene tipo, así que no hay vecinos que votar; solo reglas sobre el título.
"""
import re
import unicodedata
from difflib import SequenceMatcher

import numpy as np

from . import models as m
from .comparacion import familias_nivel
from .recomendaciones import texto_convocatoria
from .semantica import ModeloNoDisponible, vector_convocatoria
from .services import descartado, publicas
from .vectores import VERSION_MODELO, de_bytes

# Nivel: reglas sobre el texto. «Bachiller» suele ser requisito de ingreso, no el nivel que se financia.
NIVELES_POR_REGLA = {"grado", "especializacion", "maestria", "doctorado"}
K_NIVEL, UMBRAL_NIVEL = 3, 0.85
# Tipo de beca: solo una señal inequívoca en el título (nombre del catálogo → patrón sobre el título normalizado).
TIPO_POR_TITULO = {"Investigación": r"\bbecas? (?:de|para) investigacion\b|\binvestigador",
                   "Mérito académico": r"\bmerito academico\b|\bexcelencia academica\b"}
# Duplicados: títulos con el mismo nivel y muy parecidos, o textos casi idénticos.
UMBRAL_TITULO, UMBRAL_TEXTO, UMBRAL_TEXTO_ENTIDAD, UMBRAL_TITULO_URL = 0.90, 0.985, 0.97, 0.85
MAX_DUPLICADOS, MAX_BORRADORES_AL_VUELO = 5, 40
ORIGEN_REGLAS, ORIGEN_VECINOS, ORIGEN_TITULO = "deducido del texto", "según becas publicadas parecidas", "deducido del título"


def normal(texto):
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", texto).split())


def niveles(c):
    return set(c.opciones.filter(activa=True).values_list("nivel", flat=True))


def nivel_por_reglas(c):
    familias = familias_nivel(f"{c.titulo}. {c.descripcion or ''}")
    nivel = next(iter(familias)) if len(familias) == 1 else None
    return nivel if nivel in NIVELES_POR_REGLA else None


def nivel_por_vecinos(vector, excluir):
    """Los k vecinos publicados más cercanos (con un único nivel) deben superar el umbral y coincidir todos."""
    filas = []
    for c in publicas().exclude(pk=excluir).prefetch_related("opciones"):
        nivs = {o.nivel for o in c.opciones.all() if o.activa}
        if len(nivs) == 1:
            filas.append((c.pk, next(iter(nivs))))
    guardados = dict(m.VectorConvocatoria.objects.filter(version_modelo=VERSION_MODELO, convocatoria__in=[pk for pk, _ in filas])
                     .values_list("convocatoria_id", "vector"))
    filas = [(pk, nivel) for pk, nivel in filas if pk in guardados]
    if len(filas) < K_NIVEL:
        return None
    puntajes = np.stack([de_bytes(guardados[pk]) for pk, _ in filas]) @ vector
    mejores = np.argsort(-puntajes)[:K_NIVEL]
    if any(puntajes[i] < UMBRAL_NIVEL for i in mejores):
        return None
    votos = {filas[i][1] for i in mejores}
    return next(iter(votos)) if len(votos) == 1 else None


def tipo_por_titulo(c):
    titulo = normal(c.titulo)
    nombres = [nombre for nombre, patron in TIPO_POR_TITULO.items() if re.search(patron, titulo)]
    if len(nombres) != 1:
        return None
    return m.TipoBeca.objects.filter(nombre=nombres[0]).first()


def estado(c):
    if c.revision == "validada":
        return "publicada"
    return "descartada" if descartado(c) else "borrador"


def motivo_duplicado(a, b, va, vb):
    """Motivo en palabras si a y b parecen la misma convocatoria; None si no."""
    if familias_nivel(a.titulo) != familias_nivel(b.titulo):
        return None  # «…Maestría…» frente a «…Grado…» de la misma entidad son becas distintas
    titulo = SequenceMatcher(None, normal(a.titulo), normal(b.titulo)).ratio()
    texto = float(va @ vb)
    if titulo >= UMBRAL_TITULO:
        return "título casi idéntico"
    if texto >= UMBRAL_TEXTO:
        return "texto casi idéntico"
    if a.institucion_id and a.institucion_id == b.institucion_id and texto >= UMBRAL_TEXTO_ENTIDAD:
        return "misma entidad y texto muy parecido"
    if a.url_oficial and a.url_oficial == b.url_oficial and titulo >= UMBRAL_TITULO_URL:
        return "mismo enlace oficial y título parecido"
    return None


def vector_de(c, guardados):
    if c.pk in guardados:
        return guardados[c.pk]
    return np.asarray(vector_convocatoria(texto_convocatoria(c)), dtype=np.float32)


def duplicados(c, vector):
    guardados = {pk: de_bytes(v) for pk, v in m.VectorConvocatoria.objects.filter(version_modelo=VERSION_MODELO).values_list("convocatoria_id", "vector")}
    otras = list(m.Convocatoria.objects.exclude(pk=c.pk).order_by("-pk"))
    sin_vector = [o for o in otras if o.pk not in guardados][:MAX_BORRADORES_AL_VUELO]
    candidatas = [o for o in otras if o.pk in guardados] + sin_vector
    encontrados = []
    for o in candidatas:
        motivo = motivo_duplicado(c, o, vector, vector_de(o, guardados))
        if motivo:
            encontrados.append({"id": o.pk, "titulo": o.titulo, "estado": estado(o), "motivo": motivo})
    return encontrados[:MAX_DUPLICADOS]


def sugerencias(c):
    vacio = {"nivel": None, "tipo_beca": None, "duplicados": []}
    try:
        guardado = m.VectorConvocatoria.objects.filter(convocatoria=c, version_modelo=VERSION_MODELO).first()
        vector = de_bytes(guardado.vector) if guardado else np.asarray(vector_convocatoria(texto_convocatoria(c)), dtype=np.float32)
        resultado = dict(vacio)
        if not niveles(c):
            nivel, origen = nivel_por_reglas(c), ORIGEN_REGLAS
            if nivel is None:
                nivel, origen = nivel_por_vecinos(vector, c.pk), ORIGEN_VECINOS
            if nivel:
                resultado["nivel"] = {"valor": nivel, "etiqueta": dict(m.NIVELES_OPCION)[nivel], "origen": origen}
        if c.tipo_beca_id is None and (tipo := tipo_por_titulo(c)):
            resultado["tipo_beca"] = {"id": tipo.pk, "nombre": tipo.nombre, "origen": ORIGEN_TITULO}
        resultado["duplicados"] = duplicados(c, vector)
        return resultado
    except ModeloNoDisponible:
        return vacio
