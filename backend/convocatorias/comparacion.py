"""Comparación orientativa por reglas, sin persistencia ni acreditación documental.

La IA local solo añade sugerencias aparte (`sugerencia`) y nunca cambia `resultado` ni la elegibilidad.
"""
import re
from decimal import Decimal
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from perfiles.models import Perfil, MCER
from .reglas import CONTRATOS, EXTERNOS, esquema, validar  # EXTERNOS: tipos que verifica la entidad oferente.
from .equivalencias import coincidir, validar_equivalencias

ACADEMICOS = {"FORMACION", "TITULO_AREA", "PROMEDIO"}
ETIQUETAS = {
    "cumple": "Coincide según tus datos declarados",
    "no_cumple": "No coincide con un requisito obligatorio",
    "desconocido": "Pendiente de comprobar",
}
SECCIONES_PERFIL = {
    "NACIONALIDAD": "datos-personales", "EDAD": "datos-personales", "RESIDENCIA": "datos-personales",
    "FORMACION": "formacion-academica", "TITULO_AREA": "formacion-academica", "PROMEDIO": "formacion-academica",
    "IDIOMA": "idiomas", "EXPERIENCIA": "experiencia", "DEDICACION": "disponibilidad", "TRASLADO": "disponibilidad",
}


def conclusion(coincide, dato):
    return ("cumple" if coincide else "no_cumple",
            "Coincide según tus datos declarados; no acredita la condición." if coincide else
            "El dato declarado no coincide con la condición publicada; no es una decisión de adjudicación.", dato,
            not coincide)


def pendiente(motivo, dato=None, actualizable=False):
    return "desconocido", motivo, dato, actualizable


# FORMACION sin `niveles_admitidos`: el nivel solo se deduce (en memoria, sin persistir) si el texto del requisito
# nombra únicamente la familia de su `nivel_minimo`. Así, «Ser Bachiller» admite bachillerato; «Título de tercer nivel
# (solo maestría)» nombra dos niveles y no se deduce.
FAMILIAS_NIVEL = {
    "bachillerato": r"\bbachiller",
    "grado": r"tercer\s+nivel|\bgrado\b|licenciatur|ingenier",
    "posgrado": r"cuarto\s+nivel|especializ|maestr|m[aá]ster|mag[ií]ster|doctor|posgrado|postgrado",
    "tecnico": r"t[eé]cnic|tecnol[oó]g",
}
NOMBRE_NIVEL = {"bachillerato": "Bachillerato", "grado": "Tercer nivel / grado"}


def nivel_deducido(valor, texto):
    nivel = (valor or {}).get("nivel_minimo")
    if (valor or {}).get("niveles_admitidos") or nivel not in NOMBRE_NIVEL:
        return None
    familias = {f for f, patron in FAMILIAS_NIVEL.items() if re.search(patron, (texto or "").lower())}
    return nivel if familias == {nivel} else None


def academico(codigo, valor, formaciones, equivalencias, texto=None):
    """Nunca toma título de una fila y área/promedio de otra."""
    if not formaciones:
        return pendiente("No has declarado formaciones; no se interpreta como ausencia de estudios.", actualizable=True)
    intentos = []
    for f in formaciones:
        if codigo == "FORMACION":
            dato = {"nivel": f.nivel, "estado_estudios": f.estado_estudios, "titulo_obtenido": f.titulo_obtenido}
            if not valor.get("niveles_admitidos"):
                deducido = nivel_deducido(valor, texto)
                # El nivel deducido solo confirma una coincidencia exacta; nunca produce «no_cumple».
                if deducido and f.nivel == deducido and f.estado_estudios == valor.get("estado_exigido") and (
                        not valor.get("titulo_obtenido") or f.titulo_obtenido):
                    intentos.append(("cumple", f"Coincide según tus datos declarados; el nivel admitido ({NOMBRE_NIVEL[deducido]}) "
                                               "se dedujo del texto de la convocatoria. No acredita la condición.", dato, False))
                else:
                    intentos.append(pendiente("Las bases indican un mínimo, pero falta determinar los niveles admitidos. No se infiere una jerarquía.", dato))
            else:
                intentos.append(conclusion(f.nivel in valor["niveles_admitidos"] and f.estado_estudios == valor["estado_exigido"] and
                                          (not valor["titulo_obtenido"] or f.titulo_obtenido), dato))
        elif codigo == "TITULO_AREA":
            dato = {}
            estados = []
            if valor.get("areas_admitidas"):
                dato["area"] = f.area.nombre if f.area else None
                estados.append(None if f.area_id is None else f.area_id in valor["areas_admitidas"])
            if valor.get("titulos_admitidos"):
                dato["nombre_titulo"] = f.nombre_titulo
                # Un texto diferente no demuestra que los títulos no sean equivalentes.
                canonico, fuente = coincidir(f.nombre_titulo, valor["titulos_admitidos"], equivalencias, "titulo")
                estados.append(True if canonico else None)
                if fuente: dato["equivalencia_documentada"] = fuente
            if False in estados:
                intentos.append(conclusion(False, dato))
            elif estados and all(e is True for e in estados):
                intentos.append(conclusion(True, dato))
            else:
                falta_dato = (bool(valor.get("areas_admitidas")) and f.area_id is None) or (bool(valor.get("titulos_admitidos")) and not f.nombre_titulo)
                intentos.append(pendiente("Falta título/área o una equivalencia de títulos revisada. No se infiere equivalencia legal.", dato, falta_dato))
        else:
            dato = {"promedio": str(f.promedio) if f.promedio is not None else None,
                    "escala_min": str(f.escala_min) if f.escala_min is not None else None,
                    "escala_max": str(f.escala_max) if f.escala_max is not None else None}
            if f.promedio is None:
                intentos.append(pendiente("Falta promedio con su escala original.", dato, True))
            elif f.escala_min != Decimal(str(valor["escala_min"])) or f.escala_max != Decimal(str(valor["escala_max"])):
                intentos.append(pendiente("Las escalas difieren; no hay una conversión ejecutable aprobada. El texto de equivalencia no se interpreta automáticamente.", dato))
            else:
                intentos.append(conclusion(f.promedio >= Decimal(str(valor["minimo"])), dato))
    # Existe una formación que coincide; si ninguna coincide, un dato incompleto conserva incertidumbre.
    for estado in ("cumple", "desconocido", "no_cumple"):
        for intento in intentos:
            if intento[0] == estado:
                return intento


def comparar_dato(r, perfil, formaciones, idiomas, destino=None):
    codigo, v = r.tipo_requisito.codigo, r.valor_estructurado
    if codigo in EXTERNOS:
        return pendiente("La entidad oferente debe comprobar esta condición. BecaNexo no recibe ni acredita documentos.")
    if codigo == "TRASLADO" and not v["requerido"]:
        return "cumple", "La condición publicada indica expresamente que no se requiere traslado.", None, False
    if perfil is None:
        return pendiente("Aún no has declarado tu perfil. Completa los datos necesarios para comparar.", actualizable=codigo in SECCIONES_PERFIL)
    if codigo in ACADEMICOS:
        return academico(codigo, v, formaciones, r.equivalencias, r.texto_original)
    if codigo == "NACIONALIDAD":
        if perfil.nacionalidad_id is None:
            return pendiente("Falta declarar la nacionalidad.", actualizable=True)
        return conclusion(perfil.nacionalidad.codigo in v["codigos_pais"], {"nacionalidad": perfil.nacionalidad.codigo})
    if codigo == "EDAD":
        nacimiento, fecha = perfil.fecha_nacimiento, r.fecha_referencia
        if nacimiento is None or fecha is None:
            return pendiente("Falta fecha de nacimiento o fecha de referencia publicada; no se utiliza la fecha de hoy.", actualizable=nacimiento is None and fecha is not None)
        if nacimiento > fecha:
            return pendiente("La fecha de referencia es anterior al nacimiento declarado.")
        edad = fecha.year - nacimiento.year - ((fecha.month, fecha.day) < (nacimiento.month, nacimiento.day))
        return conclusion((v.get("minimo") is None or edad >= v["minimo"]) and
                          (v.get("maximo") is None or edad <= v["maximo"]), {"edad_a_fecha_referencia": edad})
    if codigo == "IDIOMA":
        nivel = idiomas.get(v["codigo_idioma"])
        if nivel is None:
            return pendiente("Falta idioma o nivel declarado; no se interpreta como desconocimiento del idioma.", actualizable=True)
        orden = [n for n, _ in MCER]
        if nivel not in orden:
            return pendiente("El nivel declarado no pertenece al marco MCER soportado.")
        return conclusion(orden.index(nivel) >= orden.index(v["nivel_minimo"]), {"idioma": v["codigo_idioma"], "nivel": nivel})
    if codigo == "EXPERIENCIA":
        return experiencia(r, perfil)
    if codigo == "DEDICACION":
        if perfil.dedicacion_disponible is None:
            return pendiente("Falta declarar disponibilidad de dedicación.", actualizable=True)
        # Tiempo completo permite participar también a tiempo parcial. "Ambas" del
        # requisito conserva su significado propio y no se satisface solo con completo.
        capacidades = {"completa": {"completa", "parcial"}, "parcial": {"parcial"},
                       "ambas": {"completa", "parcial", "ambas"}}
        return conclusion(bool(capacidades[perfil.dedicacion_disponible].intersection(v["valores_admitidos"])),
                          {"dedicacion": perfil.dedicacion_disponible})
    if codigo == "TRASLADO":
        if destino is None:
            return pendiente("Falta el país de esta alternativa para comparar el traslado exigido.")
        if v.get("destino") and v["destino"] != destino.codigo:
            return pendiente("La condición antigua menciona otro destino. El administrador debe aclarar su ámbito, sin inferirlo.")
        dato = {"disponible_traslado": perfil.disponible_traslado}
        valores = [perfil.disponible_traslado]
        if destino.codigo != "EC":
            dato["disponible_extranjero"] = perfil.disponible_extranjero
            valores.append(perfil.disponible_extranjero)
        if False in valores:
            return conclusion(False, dato)
        if None in valores:
            return pendiente("Falta declarar la disponibilidad de traslado requerida.", dato, True)
        return conclusion(True, dato)
    if codigo == "RESIDENCIA":
        dato, resultados = {}, []
        pais = perfil.residencia.codigo if perfil.residencia else None
        if v.get("codigos_pais"):
            pais = perfil.residencia.codigo if perfil.residencia else None
            dato["pais"] = pais
            resultados.append(None if pais is None else pais in v["codigos_pais"])
        provincia = None
        for key, attr, tipo in (("provincias", "provincia_residencia", "provincia"), ("ciudades", "ciudad_residencia", "ciudad")):
            if v.get(key):
                texto = getattr(perfil, attr)
                dato[attr] = texto
                contexto = pais in v.get("codigos_pais", []) and (tipo == "provincia" or provincia is not None)
                literal = len(v.get("codigos_pais", [])) == 1 and (tipo == "provincia" or len(v.get("provincias", [])) == 1)
                nombre, fuente = coincidir(texto, v[key], r.equivalencias, tipo, pais, provincia if tipo == "ciudad" else None, literal=literal) if contexto else (None, None)
                if tipo == "provincia": provincia = nombre
                if fuente: dato[f"equivalencia_{tipo}"] = fuente
                resultados.append(True if nombre else None)
        if False in resultados:
            return conclusion(False, dato)
        if not resultados or None in resultados:
            faltan = (bool(v.get("codigos_pais")) and pais is None) or (bool(v.get("provincias")) and not perfil.provincia_residencia) or (bool(v.get("ciudades")) and not perfil.ciudad_residencia)
            return pendiente("Falta ubicación o una equivalencia territorial revisada para el texto declarado.", dato, faltan)
        return conclusion(True, dato)
    return pendiente("No existe una interpretación aprobada para este tipo.")


def experiencia(r, perfil):
    registros = list(perfil.experiencias.all())
    if not registros: return pendiente("Experiencia no declarada; no se presume experiencia cero.", actualizable=True)
    if not r.fecha_referencia: return pendiente("Falta fecha de referencia publicada para limitar los periodos de experiencia.")
    if r.fecha_referencia > timezone.localdate() and any(e.actual for e in registros):
        return pendiente("La referencia publicada es futura y hay experiencia en curso. No se proyecta como realizada experiencia futura ni se inventa una fecha de finalización.")
    area = r.valor_estructurado.get("area")
    intervalos = []
    for registro in registros:
        if area is not None and registro.area_id != area: continue
        fin = min(registro.fecha_fin or r.fecha_referencia, r.fecha_referencia)
        if registro.fecha_inicio <= fin: intervalos.append((registro.fecha_inicio, fin))
    unidos = []
    for inicio, fin in sorted(intervalos):
        if unidos and inicio <= unidos[-1][1]: unidos[-1][1] = max(fin, unidos[-1][1])
        else: unidos.append([inicio, fin])
    return pendiente("Periodos del área requerida sin superposiciones, limitados a la fecha publicada. Falta una convención ejecutable de meses aprobada; el texto no se ejecuta ni se convierten jornadas.",
                     {"periodos_sin_superposicion": [[a.isoformat(), b.isoformat()] for a, b in unidos], "fecha_corte": r.fecha_referencia.isoformat()})


def regla_comparable(r):
    """Revisada, con contrato soportado y valor válido: solo entonces se compara con el perfil."""
    codigo = r.tipo_requisito.codigo
    if not (r.validado and codigo in CONTRATOS and r.tipo_requisito.esquema_valor == esquema(codigo)):
        return False
    try:
        validar(codigo, r.valor_estructurado, r.fecha_referencia, r.modo_comprobacion, r.operador)
        validar_equivalencias(codigo, r.valor_estructurado, r.equivalencias)
    except ValidationError:
        return False
    return True


def evaluar_requisito(r, perfil, formaciones, idiomas, relacion_academica_pendiente=False, destino=None):
    codigo = r.tipo_requisito.codigo
    externa = codigo in EXTERNOS or r.modo_comprobacion == "entidad_oferente" or bool(r.documento_exigido or r.detalle_acreditacion)
    resultado = pendiente("La regla no está revisada o su contrato no está soportado; requiere revisión administrativa.")
    if regla_comparable(r):
        resultado = comparar_dato(r, perfil, formaciones, idiomas, destino)
        if relacion_academica_pendiente and r.relacion_formacion == "pendiente" and r.obligatorio and codigo in ACADEMICOS and resultado[0] == "cumple":
            resultado = pendiente("Hay varias condiciones académicas obligatorias sin vínculo de misma formación. Falta definir esa relación; no se mezclan datos de títulos distintos.")
    estado, explicacion, dato, actualizable = resultado
    return {"id": r.pk, "tipo": codigo, "descripcion": r.texto_original, "obligatorio": r.obligatorio,
            "ambito": "destino" if r.destino_id else "opcion" if r.opcion_estudio_id else "comun", "resultado": estado, "grupo_formacion": r.grupo_formacion,
            "explicacion": explicacion, "dato_declarado": dato,
            "seccion_perfil": SECCIONES_PERFIL.get(codigo) if actualizable and estado != "cumple" else None,
            "condicion_exigida": {"valores": r.valor_estructurado, "fecha_referencia": r.fecha_referencia,
                                  "documento": r.documento_exigido, "acreditacion": r.detalle_acreditacion,
                                  "referencia_bases": r.referencia_bases},
            "comprobacion_externa": externa, "estado_documental": "pendiente_entidad_oferente" if externa else "no_evaluado"}


def agregar(evaluaciones):
    obligatorios = [e for e in evaluaciones if e["obligatorio"]]
    comparables = [e for e in obligatorios if e["tipo"] not in EXTERNOS]
    if any(e["resultado"] == "no_cumple" for e in obligatorios): return "no_cumple"
    if not comparables or any(e["resultado"] == "desconocido" for e in comparables): return "desconocido"
    return "cumple"


def evaluar_alternativa(reglas, perfil, formaciones, idiomas, destino):
    academicos = [r for r in reglas if r.obligatorio and r.tipo_requisito.codigo in ACADEMICOS]
    evaluaciones = {r.pk: evaluar_requisito(r, perfil, formaciones, idiomas, len(academicos) > 1, destino) for r in reglas}
    grupos = {}
    for r in reglas:
        if r.relacion_formacion == "misma_formacion" and r.grupo_formacion:
            grupos.setdefault(r.grupo_formacion, []).append(r)
    for nombre, miembros in grupos.items():
        candidatos = []
        for formacion in formaciones:
            valores = [evaluar_requisito(r, perfil, [formacion], idiomas, False, destino) for r in miembros]
            estado = "no_cumple" if any(e["resultado"] == "no_cumple" for e in valores) else "desconocido" if any(e["resultado"] == "desconocido" for e in valores) else "cumple"
            candidatos.append((estado, valores))
        elegido = next((c for estado in ("cumple", "desconocido", "no_cumple") for c in candidatos if c[0] == estado), None)
        estado = elegido[0] if elegido else "desconocido"
        for index, r in enumerate(miembros):
            e = elegido[1][index] if elegido else evaluaciones[r.pk]
            e["resultado"] = estado
            e["explicacion"] = {
                "cumple": f"Grupo {nombre}: una misma formación coincide con todas sus condiciones según los datos declarados.",
                "no_cumple": f"Grupo {nombre}: ninguna formación declarada satisface conjuntamente las condiciones; todas se descartan por al menos un dato conocido.",
                "desconocido": f"Grupo {nombre}: falta información para confirmar una misma formación que satisfaga todas las condiciones. No se mezclan títulos."
            }[estado]
            if estado == "no_cumple": e["dato_declarado"] = None
            evaluaciones[r.pk] = e
    return [evaluaciones[r.pk] for r in reglas]


# Sugerencia semántica de TITULO_AREA. Umbral calibrado el 27/11/2026: carreras distintas ≤ 0,48; requisitos que solo
# piden un nivel («título de maestría…») ≤ 0,66; carreras equivalentes 0,51–0,83. Con 0,70 no aparece ninguna falsa.
UMBRAL_SUGERENCIA_TITULO = 0.70
ETIQUETA_SUGERENCIA = "Posible coincidencia (sugerida por IA local)"


def texto_formacion(f):
    return " ".join(filter(None, [f.carrera, f.nombre_titulo, f.area.nombre if f.area_id else None]))


def sugerir_titulos(opciones, requisitos, formaciones):
    """Añade `sugerencia` a los TITULO_AREA revisados que quedaron «desconocido». No toca `resultado` ni la elegibilidad.

    El texto del requisito es público y usa la caché de convocatorias; el de la formación se calcula una vez por
    consulta y no se guarda. Sin modelo, no hay sugerencia.
    """
    from perfiles.models import Area
    from .semantica import ModeloNoDisponible, similitud, vector, vector_convocatoria
    por_id = {r.pk: r for r in requisitos}
    textos = [(f, texto_formacion(f)) for f in formaciones]
    textos = [(f, t) for f, t in textos if t.strip()]
    if not textos:
        return
    vistos, vectores, cache = set(), {}, {}
    try:
        for opcion in opciones:
            for alternativa in opcion["resultados_destino"]:
                for e in alternativa["requisitos"]:
                    r = por_id.get(e["id"])
                    if id(e) in vistos or e["tipo"] != "TITULO_AREA" or e["resultado"] != "desconocido" or r is None or not regla_comparable(r):
                        continue
                    vistos.add(id(e))
                    if r.pk not in cache:
                        v = r.valor_estructurado or {}
                        nombres = list(Area.objects.filter(pk__in=v.get("areas_admitidas") or []).values_list("nombre", flat=True))
                        exigido = "; ".join([*(v.get("titulos_admitidos") or []), *nombres])
                        mejor = None
                        if exigido:
                            requisito = vector_convocatoria(exigido)
                            for f, texto in textos:
                                if f.pk not in vectores:
                                    vectores[f.pk] = vector("Formación: " + texto)
                                puntaje = similitud(requisito, vectores[f.pk])
                                if puntaje >= UMBRAL_SUGERENCIA_TITULO and (mejor is None or puntaje > mejor[0]):
                                    mejor = (puntaje, f)
                        cache[r.pk] = None if mejor is None else {
                            "etiqueta": ETIQUETA_SUGERENCIA, "formacion": mejor[1].carrera,
                            "explicacion": f"El modelo de IA local encuentra parecido entre tu formación «{mejor[1].carrera}» y el título o área "
                                           "exigidos. No acredita el requisito: confirma la equivalencia en las bases o con la entidad oferente."}
                    if cache[r.pk]:
                        e["sugerencia"] = cache[r.pk]
    except ModeloNoDisponible:
        for opcion in opciones:
            for alternativa in opcion["resultados_destino"]:
                for e in alternativa["requisitos"]:
                    e.pop("sugerencia", None)


def evaluar_convocatoria(usuario, convocatoria, sugerencias=False):
    from .models import BorradorRastreo
    origin = BorradorRastreo.objects.filter(convocatoria=convocatoria).first()
    unstructured = bool(origin and origin.datos_iniciales.get('requisitos_originales')
                        and not convocatoria.requisitos.filter(activo=True).exists())
    perfil = Perfil.objects.select_related("nacionalidad", "residencia").filter(usuario=usuario).first()
    formaciones = list(perfil.formaciones.select_related("area")) if perfil else []
    idiomas = {i.idioma.codigo: i.nivel for i in perfil.idiomas.select_related("idioma")} if perfil else {}
    preferencias = {(p.nivel, p.modalidad) for p in perfil.preferencias.all()} if perfil else set()
    requisitos = list(convocatoria.requisitos.filter(activo=True).select_related("tipo_requisito"))
    opciones = []
    for opcion in convocatoria.opciones.filter(activa=True).prefetch_related("paises"):
        aplicables = [r for r in requisitos if r.opcion_estudio_id in (None, opcion.pk)]
        destinos = list(opcion.paises.all())
        alternativas = []
        for destino in destinos or [None]:
            reglas = [r for r in aplicables if r.destino_id is None or (destino and r.destino_id == destino.pk)]
            evaluaciones = evaluar_alternativa(reglas, perfil, formaciones, idiomas, destino)
            estado = agregar(evaluaciones)
            if (destino is None or unstructured) and estado == "cumple": estado = "desconocido"
            alternativas.append({"pais": destino.codigo if destino else None, "nombre": destino.nombre if destino else "Destino no especificado",
                                 "resultado": estado, "resumen": ETIQUETAS[estado], "requisitos": evaluaciones})
        estado = next(estado for estado in ("cumple", "desconocido", "no_cumple") if any(a["resultado"] == estado for a in alternativas))
        # Una alternativa seleccionada para el resumen nunca mezcla evidencias de distintos pa?ses.
        principal = next(a for a in alternativas if a["resultado"] == estado)
        modalidad_preferencia = (
            "desconocido" if opcion.nivel == "no_aplica" or not preferencias else
            "coincide" if (opcion.nivel, opcion.modalidad) in preferencias else "no_coincide"
        )
        opciones.append({"id": opcion.pk, "programa": opcion.programa, "nivel": opcion.nivel,
                         "modalidad": opcion.modalidad, "destinos": [p.nombre for p in destinos],
                         "preferencia_modalidad": modalidad_preferencia,
                         "resultado": estado, "resumen": ETIQUETAS[estado], "requisitos": principal["requisitos"],
                         "resultados_destino": alternativas,
                         "verificaciones_externas_pendientes": len({e["id"] for a in alternativas for e in a["requisitos"] if e["comprobacion_externa"]}),
                         "aviso": "No hay requisitos identificados. No significa que no se exijan condiciones." if not aplicables else None})
    if sugerencias:
        sugerir_titulos(opciones, requisitos, formaciones)
    destacada = next((o for estado in ("cumple", "desconocido") for o in opciones if o["resultado"] == estado), None)
    texto = "Se destaca una opción con coincidencias según tus datos declarados; revisa sus destinos y comprobaciones pendientes." if destacada and destacada["resultado"] == "cumple" else "Se destaca una opción pendiente de comprobar; completa o revisa la información indicada." if destacada else "Las opciones presentan incumplimientos obligatorios. Puedes consultar sus condiciones."
    return {"convocatoria_id": convocatoria.pk, "calculado_en": timezone.now(), "opcion_destacada_id": destacada["id"] if destacada else None,
            "criterio_destacada": texto,
            "aviso": "Comparación orientativa de datos declarados. La entidad oferente verifica documentos y decide la adjudicación.", "opciones": opciones}
