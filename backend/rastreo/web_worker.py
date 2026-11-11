"""Proceso independiente iniciado por el panel administrativo."""
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def main():
    if len(sys.argv) != 5:
        return 2
    source_id, actor_id, key = int(sys.argv[1]), int(sys.argv[2]), str(uuid.UUID(sys.argv[3]))
    root = Path(sys.argv[4])
    marker = root / f'fuente-{source_id}.json'
    result = root / f'resultado-{source_id}.json'
    outcome = {'clave': key, 'fecha_utc': datetime.now(timezone.utc).isoformat()}
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        import django
        django.setup()
        from django.utils import timezone as django_timezone
        from rastreo.models import Fuente
        from rastreo.services import exclusion, next_due, run_manual
        from rastreo.web_frequency import extraordinary_enabled, manual_window, source_blocked

        request = json.loads(marker.read_text(encoding='utf-8'))
        if (request.get('clave') != key or request.get('fuente_id', source_id) != source_id
                or request.get('actor_id', actor_id) != actor_id):
            raise ValueError('Marcador de inicio inconsistente.')
        extraordinary = request.get('extraordinario') is True
        reason = request.get('motivo')
        if extraordinary and (not extraordinary_enabled() or not isinstance(reason, str)):
            raise ValueError('Excepción extraordinaria no autorizada.')
        if extraordinary:
            from rastreo.web_frequency import accepted_path
            receipt = json.loads(accepted_path(source_id, key).read_text(encoding='utf-8'))
            if receipt != request:
                raise ValueError('Solicitud extraordinaria sin comprobante íntegro.')

        # El bloqueo compartido con el Programador impide una captura entre
        # la comprobación de frecuencia y el inicio de run_manual.
        with exclusion(source_id) as acquired:
            if not acquired:
                outcome['estado'] = 'omitida_concurrencia'
            else:
                source = Fuente.objects.get(pk=source_id)
                # La aceptación propia no puede bloquear a su trabajador.
                due = manual_window(source, exclude_key=key) if extraordinary else next_due(source)
                if extraordinary and source_blocked(source):
                    outcome['estado'] = 'bloqueada_fuente'
                elif due and due > django_timezone.now():
                    outcome.update(estado='omitida_frecuencia', proxima_ejecucion=due.isoformat())
                else:
                    context = ({'motivo': reason, 'actor_id': actor_id,
                                'aceptada_en': request['aceptada_en'], 'modalidad': 'extraordinaria'}
                               if extraordinary else {'motivo': reason, 'modalidad': 'ordinaria'} if reason else None)
                    execution = run_manual(source_id, actor_id, key, context) if context else run_manual(source_id, actor_id, key)
                    execution.refresh_from_db()
                    outcome.update(estado=execution.estado, ejecucion_id=execution.pk)
    except Exception as exc:
        # Solo la clase de error; nunca se escriben credenciales o rutas privadas.
        outcome.update(estado='fallo_infraestructura', codigo=type(exc).__name__)
    temporary = result.with_suffix('.tmp')
    temporary.write_text(json.dumps(outcome), encoding='utf-8')
    os.replace(temporary, result)
    try:
        if json.loads(marker.read_text(encoding='utf-8')).get('clave') == key:
            marker.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass
    return 1 if outcome['estado'] == 'fallo_infraestructura' else 0


if __name__ == '__main__':
    raise SystemExit(main())
