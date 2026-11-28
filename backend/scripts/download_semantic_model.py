"""Descarga exclusiva de los artefactos ONNX aprobados; ejecutar desde .venv."""

import ctypes
import hashlib
import json
import shutil
import sys
from pathlib import Path

from huggingface_hub import snapshot_download


REPO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
FILES = (
    "onnx/model_quint8_avx2.onnx",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "config.json",
    "1_Pooling/config.json",
)
EXPECTED_SHA256 = {
    "onnx/model_quint8_avx2.onnx": "98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f",
    "tokenizer.json": "2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8",
}
ROOT = Path(__file__).resolve().parents[2] / ".local-models" / "miniLM-multilingual"


def tiene_avx2(plataforma=None, cpuinfo=Path("/proc/cpuinfo")):
    """True o False si se puede determinar; None si no (otra plataforma o /proc/cpuinfo ilegible)."""
    plataforma = sys.platform if plataforma is None else plataforma
    if plataforma == "win32":
        return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))  # PF_AVX2_INSTRUCTIONS_AVAILABLE
    if plataforma.startswith("linux"):
        try:
            texto = Path(cpuinfo).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        indicadores = [linea.split(":", 1)[1].split() for linea in texto.splitlines()
                       if linea.split(":", 1)[0].strip() in ("flags", "Features") and ":" in linea]
        if not indicadores:
            return None
        return all("avx2" in grupo for grupo in indicadores)
    return None


def main():
    avx2 = tiene_avx2()
    if avx2 is False:
        raise SystemExit("AVX2 no está disponible en este procesador; el modelo aprobado (model_quint8_avx2.onnx) lo necesita. "
                         "No se descargó ningún modelo.")
    if avx2 is None:
        print("Aviso: no se pudo comprobar si el procesador tiene AVX2; se descarga igualmente el modelo aprobado.", file=sys.stderr)
    if shutil.disk_usage(ROOT.parents[1]).free < 500_000_000:
        raise SystemExit("Falta espacio libre para descargar el modelo.")
    ROOT.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=REPO, revision=REVISION, local_dir=ROOT, allow_patterns=FILES, max_workers=2)
    inventory = {}
    for name in FILES:
        path = ROOT / name
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if name in EXPECTED_SHA256 and digest != EXPECTED_SHA256[name]:
            raise SystemExit(f"La huella del artefacto {name} no coincide con la revisión comprobada.")
        inventory[name] = {"bytes": path.stat().st_size, "sha256": digest}
    (ROOT / "manifest.json").write_text(json.dumps({"repo": REPO, "revision": REVISION,
                                                       "license": "apache-2.0", "files": inventory}, indent=2), encoding="utf-8")
    print("Modelo ONNX y tokenizer verificados en", ROOT)
    print("Revisión", REVISION, "bytes", sum(item["bytes"] for item in inventory.values()))


if __name__ == "__main__":
    main()
