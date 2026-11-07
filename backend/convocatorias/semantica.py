"""Afinidad temática local; nunca modifica la elegibilidad ni guarda datos personales."""

from functools import lru_cache
from pathlib import Path

from django.conf import settings


class ModeloNoDisponible(Exception):
    pass


@lru_cache(maxsize=1)
def _modelo():
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        root = Path(settings.SEMANTIC_MODEL_DIR)
        model = root / "onnx" / "model_quint8_avx2.onnx"
        tokenizer = root / "tokenizer.json"
        if not model.is_file() or not tokenizer.is_file():
            raise ModeloNoDisponible("Faltan los archivos del modelo semántico local.")
        session = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
        if session.get_providers() != ["CPUExecutionProvider"]:
            raise ModeloNoDisponible("La inferencia debe usar únicamente CPU.")
        tokens = Tokenizer.from_file(str(tokenizer))
        tokens.enable_truncation(max_length=128)
        return session, tokens
    except ModeloNoDisponible:
        raise
    except Exception as exc:
        raise ModeloNoDisponible("No se pudo cargar el modelo semántico local.") from exc


def vector(texto):
    """Embedding normalizado con mean pooling y máscara de atención."""
    try:
        import numpy as np

        session, tokenizer = _modelo()
        encoded = tokenizer.encode(texto)
        if not encoded.ids:
            raise ModeloNoDisponible("No hay texto utilizable para calcular afinidad.")
        inputs = {
            "input_ids": np.asarray([encoded.ids], dtype=np.int64),
            "attention_mask": np.asarray([encoded.attention_mask], dtype=np.int64),
            "token_type_ids": np.asarray([encoded.type_ids], dtype=np.int64),
        }
        feed = {item.name: inputs[item.name] for item in session.get_inputs()}
        output = session.run(None, feed)[0]
        if output.ndim == 3:
            mask = inputs["attention_mask"][..., None]
            pooled = (output * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
        elif output.ndim == 2:
            pooled = output
        else:
            raise ModeloNoDisponible("La salida del modelo no tiene el formato esperado.")
        result = pooled[0].astype(np.float32)
        norm = np.linalg.norm(result)
        if not np.isfinite(norm) or norm == 0:
            raise ModeloNoDisponible("El modelo produjo un vector inválido.")
        return tuple((result / norm).tolist())
    except ModeloNoDisponible:
        raise
    except Exception as exc:
        raise ModeloNoDisponible("Falló la inferencia semántica local.") from exc


@lru_cache(maxsize=512)
def vector_convocatoria(texto):
    # Solo texto público. Nunca almacenar el perfil del postulante en caché compartida.
    return vector(texto)


def similitud(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))
