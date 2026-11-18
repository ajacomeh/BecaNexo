"""Proceso aislado para leer texto PDF local con límites; sin Django ni red."""
import json
import sys
from pathlib import Path

from pypdf import PdfReader

MAX_PAGINAS = 12
MAX_BYTES_PAGINA = 300_000
MAX_CARACTERES_PAGINA = 3_000


def leer(path):
    if path.stat().st_size > 2_097_152 or path.stat().st_size < 8:
        return {'estado': 'limite_tamano', 'paginas': []}
    with path.open('rb') as stream:
        if stream.read(5) != b'%PDF-':
            return {'estado': 'invalido', 'paginas': []}
        stream.seek(0)
        reader = PdfReader(stream, strict=False)
        if reader.is_encrypted:
            return {'estado': 'protegido', 'paginas': []}
        total = len(reader.pages)
        pages = []
        for number in range(min(total, MAX_PAGINAS)):
            page = reader.pages[number]
            try:
                content = page.get_contents()
                if content is not None and len(content.get_data()) > MAX_BYTES_PAGINA:
                    pages.append({'pagina': number + 1, 'estado': 'limite_contenido', 'texto': ''})
                    continue
                text = page.extract_text() or ''
                pages.append({'pagina': number + 1, 'estado': 'texto' if text.strip() else 'sin_texto',
                              'texto': text[:MAX_CARACTERES_PAGINA],
                              'texto_recortado': len(text) > MAX_CARACTERES_PAGINA})
            except Exception:
                pages.append({'pagina': number + 1, 'estado': 'no_interpretable', 'texto': ''})
        return {'estado': 'limite_paginas' if total > MAX_PAGINAS else
                'sin_texto' if not any(page['texto'].strip() for page in pages) else 'extraido',
                'total_paginas': total, 'paginas': pages}


if __name__ == '__main__':
    try:
        output = leer(Path(sys.argv[1]))
    except Exception:
        output = {'estado': 'invalido', 'paginas': []}
    # JSON ASCII evita depender de la codificación de consola de Windows.
    print(json.dumps(output, ensure_ascii=True))
