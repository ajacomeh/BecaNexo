"""Descarga exclusiva de los artefactos ONNX aprobados; ejecutar desde .venv."""

import ctypes
import hashlib
import json
import shutil
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


def main():
    if not ctypes.windll.kernel32.IsProcessorFeaturePresent(40):
        raise SystemExit("AVX2 no está disponible; no se descargó otro modelo.")
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
