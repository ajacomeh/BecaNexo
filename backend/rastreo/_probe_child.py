"""Solo para validar proceso separado; no importa Django ni abre la red."""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


if __name__ == '__main__':
    folder = Path(sys.argv[1])
    (folder / 'started.json').write_text(json.dumps({'pid': os.getpid(),
        'utc': datetime.now(timezone.utc).isoformat()}), encoding='utf-8')
    time.sleep(3)
    (folder / 'completed.json').write_text(json.dumps({'completed': True,
        'utc': datetime.now(timezone.utc).isoformat()}), encoding='utf-8')
    if len(sys.argv) == 4:
        source_id, key = sys.argv[2:]
        (folder / f'resultado-{source_id}.json').write_text(json.dumps({
            'clave': key, 'estado': 'finalizada', 'prueba_inocua': True}), encoding='utf-8')
        marker = folder / f'fuente-{source_id}.json'
        if marker.exists() and json.loads(marker.read_text(encoding='utf-8')).get('clave') == key:
            marker.unlink()
