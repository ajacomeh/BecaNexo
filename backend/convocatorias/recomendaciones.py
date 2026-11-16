"""Orden orientativo: primero elegibilidad declarada, luego afinidad temática local."""

from perfiles.models import Perfil
from favoritos.models import Favorito

from .comparacion import evaluar_convocatoria
from .semantica import ModeloNoDisponible, similitud, vector, vector_convocatoria
from .services import detalle, postulables


PRIORIDAD = {"cumple": 0, "desconocido": 1, "no_cumple": 2}


def texto_perfil(perfil):
    if perfil is None:
        return "", []
    partes = []
    fuentes = []
    areas = [item.area.nombre for item in perfil.areas.select_related("area")]
    if areas:
        partes.append("Áreas de interés: " + ", ".join(areas))
        fuentes.append("áreas de interés")
    formaciones = [" ".join(filter(None, [f.carrera, f.nombre_titulo, f.area.nombre if f.area else None]))
                   for f in perfil.formaciones.select_related("area")]
    if formaciones:
        partes.append("Formación: " + "; ".join(formaciones))
        fuentes.append("formación declarada")
    if perfil.preferencias.filter(modalidad="hibrida").exists():
        partes.append("Modalidad de estudio preferida: híbrida")
        fuentes.append("modalidad preferida")
    if perfil.descripcion and perfil.descripcion.strip():
        partes.append("Intereses y objetivos: " + perfil.descripcion.strip())
        fuentes.append("descripción del perfil")
    return ". ".join(partes), fuentes


def texto_convocatoria(convocatoria):
    partes = [convocatoria.titulo]
    partes.extend(item.area.nombre for item in convocatoria.areas.select_related("area"))
    partes.extend(o.programa for o in convocatoria.opciones.filter(activa=True) if o.programa)
    if convocatoria.opciones.filter(activa=True, modalidad="hibrida").exists():
        partes.append("Modalidad de estudio: híbrida")
    if convocatoria.descripcion:
        partes.append(convocatoria.descripcion)
    return ". ".join(partes)


def preferencias_coincidentes(perfil, convocatoria):
    if perfil is None:
        return {"declaradas": False, "coincidencias": []}
    preferencias = list(perfil.preferencias.all())
    destinos = set(perfil.destinos.values_list("pais_id", flat=True))
    if not preferencias and not destinos:
        return {"declaradas": False, "coincidencias": []}
    opciones = list(convocatoria.opciones.filter(activa=True).prefetch_related("paises"))
    coincidencias = []
    if preferencias and any(o.nivel == p.nivel for o in opciones for p in preferencias):
        coincidencias.append("nivel de estudio")
    if preferencias and any((o.nivel, o.modalidad) == (p.nivel, p.modalidad) for o in opciones for p in preferencias):
        coincidencias.append("modalidad")
    if destinos and any(p.pk in destinos for o in opciones for p in o.paises.all()):
        coincidencias.append("destino")
    return {"declaradas": True, "coincidencias": coincidencias}


def recomendar(usuario):
    perfil = Perfil.objects.filter(usuario=usuario).first()
    texto, fuentes = texto_perfil(perfil)
    perfil_vector = None
    modelo_disponible = True
    if texto:
        try:
            perfil_vector = vector(texto)
        except ModeloNoDisponible:
            modelo_disponible = False
    resultados = []
    areas_declaradas = {item.area.nombre for item in perfil.areas.select_related("area")} if perfil else set()
    convocatorias = list(postulables().order_by("id"))
    favoritos = dict(Favorito.objects.filter(usuario=usuario, convocatoria_id__in=[c.pk for c in convocatorias])
                     .values_list("convocatoria_id", "id"))
    for convocatoria in convocatorias:
        comparacion = evaluar_convocatoria(usuario, convocatoria)
        estados = [o["resultado"] for o in comparacion["opciones"]]
        elegibilidad = min(estados, key=PRIORIDAD.get) if estados else "desconocido"
        afinidad = {"estado": "sin_datos_perfil", "explicacion": "Declara áreas, formación o intereses para calcular afinidad temática."}
        puntuacion = None
        if texto and not modelo_disponible:
            afinidad = {"estado": "modelo_no_disponible", "explicacion": "El modelo local no está disponible; se conserva el orden por requisitos."}
        elif perfil_vector is not None:
            try:
                puntuacion = similitud(perfil_vector, vector_convocatoria(texto_convocatoria(convocatoria)))
                comunes = sorted(areas_declaradas & {item.area.nombre for item in convocatoria.areas.select_related("area")})
                motivo = ("Área declarada presente también en la convocatoria: " + ", ".join(comunes) + ". ") if comunes else ""
                afinidad = {"estado": "calculada", "explicacion":
                            motivo + "Se compararon " + ", ".join(fuentes) + " con el título, las áreas, los programas y la descripción publicados."}
            except ModeloNoDisponible:
                modelo_disponible = False
                afinidad = {"estado": "modelo_no_disponible", "explicacion": "El modelo local no está disponible; se conserva el orden por requisitos."}
        datos = detalle(convocatoria, publico=True)
        datos["favorito_id"] = favoritos.get(convocatoria.pk)
        resultados.append({"convocatoria": datos, "elegibilidad": elegibilidad,
                           "preferencias": preferencias_coincidentes(perfil, convocatoria),
                           "afinidad": afinidad, "_puntuacion": puntuacion})
    resultados.sort(key=lambda item: (PRIORIDAD[item["elegibilidad"]], item["_puntuacion"] is None,
                                     -(item["_puntuacion"] or 0), item["convocatoria"]["id"]))
    for item in resultados:
        del item["_puntuacion"]
    return resultados
