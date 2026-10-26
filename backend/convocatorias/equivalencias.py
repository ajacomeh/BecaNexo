"""Equivalencias locales a una regla, con procedencia y contexto territorial."""
import unicodedata
from rest_framework.exceptions import ValidationError

ACADEMICOS = {"FORMACION", "TITULO_AREA", "PROMEDIO"}


def normalizar(texto):
    return " ".join(unicodedata.normalize("NFC", texto or "").split()).casefold()


def validar_equivalencias(codigo, valor, filas):
    if not isinstance(filas, list) or len(filas) > 100:
        raise ValidationError({"equivalencias": "Usa una lista de hasta 100 equivalencias."})
    seen = set()
    for fila in filas:
        if not isinstance(fila, dict) or set(fila) != {"tipo", "origen", "admitido", "referencia", "pais", "provincia"}:
            raise ValidationError({"equivalencias": "Cada fila requiere tipo, origen, admitido, referencia, país y provincia (nulos si no aplican)."})
        for key in ("tipo", "origen", "admitido", "referencia"):
            if not isinstance(fila[key], str) or not fila[key].strip() or len(fila[key]) > 1000:
                raise ValidationError({"equivalencias": "Completa textos y referencia a las bases, máximo 1000 caracteres."})
        tipo = fila["tipo"]
        campo = {"titulo": "titulos_admitidos", "provincia": "provincias", "ciudad": "ciudades"}.get(tipo)
        if not campo or (codigo, tipo) not in (("TITULO_AREA", "titulo"), ("RESIDENCIA", "provincia"), ("RESIDENCIA", "ciudad")):
            raise ValidationError({"equivalencias": "Tipo de equivalencia incompatible con el requisito."})
        if normalizar(fila["admitido"]) not in [normalizar(x) for x in valor.get(campo, [])]:
            raise ValidationError({"equivalencias": "El destino de equivalencia debe ser un valor admitido en esta regla."})
        if tipo == "titulo":
            if fila["pais"] is not None or fila["provincia"] is not None:
                raise ValidationError({"equivalencias": "La equivalencia de título no usa contexto territorial."})
        else:
            if not isinstance(fila["pais"], str) or fila["pais"] not in valor.get("codigos_pais", []):
                raise ValidationError({"equivalencias": "Indica un país admitido para contextualizar la equivalencia."})
            if tipo == "ciudad":
                if not isinstance(fila["provincia"], str) or normalizar(fila["provincia"]) not in [normalizar(x) for x in valor.get("provincias", [])]:
                    raise ValidationError({"equivalencias": "La ciudad requiere una provincia admitida explícita."})
            elif fila["provincia"] is not None:
                raise ValidationError({"equivalencias": "La equivalencia de provincia solo requiere país."})
        key = (tipo, normalizar(fila["origen"]), fila["pais"], normalizar(fila["provincia"]))
        if key in seen:
            raise ValidationError({"equivalencias": "No repitas un origen en el mismo contexto ni configures equivalencias contradictorias."})
        seen.add(key)


def coincidir(texto, admitidos, filas, tipo, pais=None, provincia=None, literal=True):
    """Devuelve nombre canónico y referencia usada, sin encadenar equivalencias."""
    for nombre in admitidos:
        if literal and normalizar(texto) == normalizar(nombre): return nombre, None
    for fila in filas:
        if (fila["tipo"] == tipo and normalizar(fila["origen"]) == normalizar(texto)
                and fila["pais"] == pais and normalizar(fila["provincia"]) == normalizar(provincia)):
            return fila["admitido"], fila["referencia"]
    return None, None
