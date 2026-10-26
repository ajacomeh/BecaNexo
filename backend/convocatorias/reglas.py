"""Contratos versionados v0.6; conserva representaciones antiguas sin inferirlas."""
from decimal import Decimal, InvalidOperation
from rest_framework.exceptions import ValidationError
from perfiles.models import Pais, Idioma, Area, NIVELES, MCER


def campo(label, kind="text", required=True, options=None):
    return dict(label=label, kind=kind, required=required, **({"options": options} if options else {}))


CONTRATOS = {
    "NACIONALIDAD": ("Nacionalidad", "pertenece", {"codigos_pais": campo("Nacionalidades admitidas", "paises")}),
    "FORMACION": ("Estudios mínimos", "minimo", {
        "nivel_minimo": campo("Mínimo original (sin lista admitida queda pendiente)", required=False, options=[v for v, _ in NIVELES]),
        "niveles_admitidos": campo("Niveles admitidos expresamente en las bases", "lista", False, options=[v for v, _ in NIVELES]),
        "estado_exigido": campo("Estado exigido", options=["en_curso", "concluidos"]), "titulo_obtenido": campo("Título obtenido", "boolean")}),
    "TITULO_AREA": ("Título y área", "pertenece", {
        "titulos_admitidos": campo("Títulos admitidos (uno por línea)", "textos", False), "areas_admitidas": campo("Áreas admitidas", "areas", False)}),
    "EDAD": ("Edad", "rango", {"minimo": campo("Edad mínima", "integer", False), "maximo": campo("Edad máxima", "integer", False)}),
    "PROMEDIO": ("Promedio y escala", "minimo", {
        "minimo": campo("Promedio mínimo", "number"), "escala_min": campo("Mínimo de la escala", "number"),
        "escala_max": campo("Máximo de la escala", "number"), "equivalencia_documentada": campo("Equivalencia expresamente publicada", required=False)}),
    "IDIOMA": ("Idioma y nivel", "minimo", {"codigo_idioma": campo("Idioma", "idioma"), "nivel_minimo": campo("Nivel MCER mínimo", options=[v for v, _ in MCER])}),
    "EXPERIENCIA": ("Experiencia", "minimo", {"meses_minimos": campo("Meses mínimos", "integer"), "area": campo("Área requerida", "area", False), "convencion_documentada": campo("Convención literal publicada (no se ejecuta como fórmula)", required=False)}),
    "DEDICACION": ("Dedicación", "pertenece", {"valores_admitidos": campo("Dedicaciones admitidas", "lista", options=["completa", "parcial", "ambas"])}),
    "TRASLADO": ("Disponibilidad de traslado", "igual", {"requerido": campo("Traslado requerido", "boolean"), "destino": campo("País de destino", "pais", False)}),
    "RESIDENCIA": ("Residencia", "pertenece", {"codigos_pais": campo("Países de residencia", "paises", False),
        "provincias": campo("Provincias admitidas (una por línea)", "textos", False), "ciudades": campo("Ciudades admitidas (una por línea)", "textos", False)}),
    "ACREDITACION": ("Certificación externa", "externo", {"certificados_admitidos": campo("Certificados admitidos según las bases"), "vigencia": campo("Vigencia publicada", required=False)}),
    "DOCUMENTO": ("Documento externo", "externo", {"documento": campo("Documento exigido"), "condiciones": campo("Condiciones documentales", required=False)}),
    "OTRO": ("Otra condición externa", "externo", {"descripcion": campo("Descripción publicada")}),
}


def esquema(codigo):
    nombre, operador, campos = CONTRATOS[codigo]
    return {"version": 2 if codigo in ("FORMACION", "EXPERIENCIA") else 1, "operadores": [operador], "campos": campos}


def validar(codigo, valor, fecha, modo, operador):
    if codigo not in CONTRATOS: raise ValidationError({"tipo_requisito": "Tipo no soportado."})
    _, esperado, campos = CONTRATOS[codigo]
    if operador != esperado: raise ValidationError({"operador": "Operador incompatible con este tipo."})
    externo = codigo in ("ACREDITACION", "DOCUMENTO", "OTRO")
    if modo != ("entidad_oferente" if externo else "dato_declarado"):
        raise ValidationError({"modo_comprobacion": "La condición documental se verifica exclusivamente por la entidad oferente; separa las reglas declaradas."})
    if not isinstance(valor, dict) or set(valor) - set(campos):
        raise ValidationError({"valor_estructurado": "Campos no permitidos para este tipo."})
    errors = {}
    for key, spec in campos.items():
        v = valor.get(key)
        if v is None:
            if spec["required"]: errors[key] = "Campo obligatorio."
            continue
        kind = spec["kind"]
        ok = True
        if kind == "boolean": ok = type(v) is bool
        elif kind in ("integer", "area"):
            ok = type(v) is int and v >= 0
            if ok and kind == "area": ok = Area.objects.filter(pk=v).exists()
        elif kind == "number":
            try: ok = type(v) in (int, float) and Decimal(str(v)).is_finite()
            except InvalidOperation: ok = False
        elif kind in ("paises", "areas", "textos", "lista"):
            ok = isinstance(v, list) and 0 < len(v) <= 249 and all(type(x) is (int if kind == "areas" else str) for x in v)
            if ok: ok = len(set(v)) == len(v)
            if ok and kind == "paises": ok = Pais.objects.filter(codigo__in=v).count() == len(v)
            if ok and kind == "areas": ok = Area.objects.filter(pk__in=v).count() == len(v)
            if ok and kind == "textos": ok = all(x.strip() and len(x) <= 500 for x in v)
            if ok and kind == "lista": ok = all(x in spec["options"] for x in v)
        else:
            ok = isinstance(v, str) and bool(v.strip()) and len(v) <= 5000
            if ok and kind == "pais": ok = Pais.objects.filter(codigo=v).exists()
            if ok and kind == "idioma": ok = Idioma.objects.filter(codigo=v).exists()
            if ok and spec.get("options"): ok = v in spec["options"]
        if not ok: errors[key] = "Valor inválido para este campo."
    if errors: raise ValidationError({"valor_estructurado": errors})
    def fail(message): raise ValidationError({"valor_estructurado": message})
    if codigo == "NACIONALIDAD" and valor["codigos_pais"] != ["EC"]: fail("El alcance de nacionalidad es Ecuador.")
    if codigo in ("EDAD", "TITULO_AREA", "RESIDENCIA") and not any(v is not None for v in valor.values()): fail("Declara al menos una condición.")
    if codigo == "EDAD":
        if not fecha: raise ValidationError({"fecha_referencia": "Indica la fecha de referencia publicada."})
        if valor.get("minimo") is not None and valor.get("maximo") is not None and valor["minimo"] > valor["maximo"]: fail("El mínimo supera al máximo.")
    if codigo == "FORMACION" and valor["titulo_obtenido"] and valor["estado_exigido"] != "concluidos": fail("Un título obtenido requiere estudios concluidos.")
    if codigo == "FORMACION" and not (valor.get("nivel_minimo") or valor.get("niveles_admitidos")): fail("Indica los niveles admitidos o conserva el mínimo original como pendiente.")
    if codigo == "PROMEDIO" and not valor["escala_min"] <= valor["minimo"] <= valor["escala_max"]: fail("El promedio debe estar dentro de la escala.")
    if codigo == "PROMEDIO" and valor["escala_min"] >= valor["escala_max"]: fail("Escala inválida.")
    if codigo == "TRASLADO" and not valor["requerido"] and valor.get("destino"): fail("Un destino no puede exigir traslado si este no se requiere.")
    return valor
