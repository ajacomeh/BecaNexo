"""Inicio y seguimiento administrativo de fuentes de rastreo autorizadas."""
import json
from datetime import datetime, timedelta, timezone as utc_timezone

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.response import Response

from usuarios.api import AuthView
from .api import AdministradorActivo
from convocatorias.siau_red import INDEX
from .models import Ejecucion, Fuente, Publicacion
from .services import next_due, resumen_corrida, supported_policy
from .portal_fuentes import PORTALES, portal_for_source
from convocatorias.siau_red import AccessError
from convocatorias.models import BorradorRastreo
from .web_frequency import block_details, extraordinary_enabled, manual_window, source_blocked, unlock_source
from .web_launch import LaunchBusy, lanzamiento_web_habilitado, launch_lock, marker_path, result_path, start_worker

MENSAJE_LANZAMIENTO_DESACTIVADO = 'El rastreo desde la web está desactivado en este entorno.'


class ControlRastreo(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['get', 'post', 'options']

    @staticmethod
    def estado():
        sources = list(Fuente.objects.order_by('id'))
        ultima = Ejecucion.objects.order_by('-inicio', '-id').select_related('fuente').first()
        activa = Ejecucion.objects.filter(estado='en_curso').first()
        # Resultado de la última corrida de la tarea programada (también si fue omitida), con su resumen legible.
        programada = Ejecucion.objects.filter(origen='programada').order_by('-inicio', '-id').first()
        ultima_programada = resumen_corrida(programada) if programada else None
        extraordinaria = extraordinary_enabled()
        now = timezone.now()
        available = []
        windows = []
        permitted = []
        invalid_log = False
        blocked = False
        block_rows = []
        for source in sources:
            if not source.activa or source.aprobada_publicacion_automatica:
                continue
            try:
                if source.adaptador == 'siau':
                    valid = source.url_base == INDEX and supported_policy(source)
                elif source.adaptador.startswith('portal_ec:'):
                    portal_for_source(source)
                    valid = True
                else:
                    valid = False
            except AccessError:
                valid = False
            if not valid:
                continue
            permitted.append(source)
            try:
                due = manual_window(source) if source.adaptador == 'siau' and extraordinaria else next_due(source)
                source_block = source_blocked(source)
            except ValueError:
                invalid_log = True
                continue
            blocked = blocked or source_block
            if source_block:
                block_rows.append(block_details(source))
            if due:
                windows.append(due)
            if not source_block and (not due or due <= now):
                last = Ejecucion.objects.filter(fuente=source).exclude(estado='omitida').order_by('-inicio', '-id').first()
                available.append((last.inicio if last else datetime.min.replace(tzinfo=utc_timezone.utc), source))
        available.sort(key=lambda entry: (entry[0], entry[1].pk))
        selected = available[0][1] if available else None
        marker_sources = [source for source in sources if marker_path(source.pk).exists()]
        inicio_pendiente = bool(marker_sources)
        requiere_revision = False
        for source in marker_sources:
            marker = marker_path(source.pk)
            try:
                json.loads(marker.read_text(encoding='utf-8'))
                # Un marcador antiguo exige revisión incluso si ya hay fila
                # en_curso: el trabajador pudo terminar abruptamente.
                requiere_revision = requiere_revision or now.timestamp() - marker.stat().st_mtime > timedelta(minutes=2).total_seconds()
            except (OSError, ValueError, TypeError, AttributeError, ValidationError):
                requiere_revision = True
        results = []
        for source in permitted:
            path = result_path(source.pk)
            if path.exists():
                try:
                    results.append((path.stat().st_mtime, json.loads(path.read_text(encoding='utf-8'))))
                except (OSError, ValueError):
                    invalid_log = True
        resultado_web = max(results, key=lambda row: row[0])[1] if results else None
        proxima = min(windows) if windows else None
        puede_iniciar = bool(selected and not activa and not inicio_pendiente and not invalid_log)
        display = selected or (permitted[0] if permitted else None)
        configured_adapters = {source.adaptador for source in sources}
        unregistered = ([{'nombre': 'SIAU', 'adaptador': 'siau'}] if 'siau' not in configured_adapters else [])
        unregistered.extend({'nombre': portal.nombre, 'adaptador': f'portal_ec:{key}'}
                            for key, portal in PORTALES.items() if f'portal_ec:{key}' not in configured_adapters)
        permitted_ids = {source.pk for source in permitted}
        return {'fuente_id': selected.pk if selected else None,
                'fuente_nombre': selected.nombre if selected else None,
                'fuentes_activas': sum(source.activa for source in sources),
                'fuentes_habilitadas': len(permitted),
                'fuentes_registradas': [{'id': source.pk, 'nombre': source.nombre,
                    'activa': source.activa, 'utilizable': source.pk in permitted_ids,
                    'politica_version': source.politica_version, 'frecuencia_min': source.frecuencia_min}
                    for source in sources],
                'conectores_sin_registro': unregistered,
                'fuentes_configuracion': [{'id': source.pk, 'nombre': source.nombre,
                    'politica_version': source.politica_version, 'frecuencia_min': source.frecuencia_min}
                    for source in permitted],
                'publicaciones_total': Publicacion.objects.count(),
                'borradores_total': BorradorRastreo.objects.count(),
                'politica_version': display.politica_version if display else None,
                'frecuencia_min': display.frecuencia_min if display else None,
                'proxima_ejecucion': proxima,
                'proxima_manual': proxima, 'intervalo_manual_seg': 300 if extraordinaria and selected and selected.adaptador == 'siau' else None,
                'rastreo_extraordinario_habilitado': bool(extraordinaria and selected and selected.adaptador == 'siau'),
                'bloqueo_fuente': blocked, 'bloqueos': [row for row in block_rows if row],
                'registro_invalido': invalid_log,
                'ejecucion_activa': activa.pk if activa else None,
                'inicio_pendiente': inicio_pendiente, 'requiere_revision': requiere_revision,
                'ultimo_inicio_web': resultado_web, 'puede_iniciar': puede_iniciar,
                'ultima_programada': ultima_programada,
                'ultima_ejecucion': ({'id': ultima.pk, 'estado': ultima.estado, 'origen': ultima.origen,
                                      'inicio': ultima.inicio, 'fin': ultima.fin,
                                      'fuente': ultima.fuente.nombre} if ultima else None)}

    def get(self, request):
        state = self.estado()
        if not lanzamiento_web_habilitado():
            # Solo en entornos que lo desactivan (por ejemplo el demo): por defecto la respuesta no cambia.
            state.update(puede_iniciar=False, lanzamiento_web_habilitado=False, motivo_no_disponible=MENSAJE_LANZAMIENTO_DESACTIVADO)
        return Response(state)

    def post(self, request):
        if not lanzamiento_web_habilitado():
            return Response({'detail': MENSAJE_LANZAMIENTO_DESACTIVADO, 'lanzamiento_web_habilitado': False}, status=409)
        reason = request.data.get('motivo') if isinstance(request.data, dict) else None
        if (not isinstance(reason, str) or not reason.strip().isprintable()
                or len(reason.strip()) < 10 or len(reason.strip()) > 240
                or set(request.data) != {'motivo'}):
            return Response({'detail': 'Indica un motivo administrativo entre 10 y 240 caracteres.'}, status=400)
        try:
            with launch_lock():
                state = self.estado()
                if not state['puede_iniciar']:
                    return Response({'detail': 'No hay fuentes autorizadas disponibles, hay una ejecución activa o aún no corresponde por frecuencia.',
                                     **state}, status=409)
                key = start_worker(state['fuente_id'], request.user.pk, reason.strip(),
                                   state['rastreo_extraordinario_habilitado'])
        except LaunchBusy:
            return Response({'detail': 'Ya existe una solicitud de inicio en proceso.'}, status=409)
        except OSError:
            return Response({'detail': 'No se pudo iniciar el proceso local; verifica el entorno del servidor.'}, status=503)
        return Response({'estado': 'iniciando', 'clave': str(key), 'fuente_id': state['fuente_id']}, status=202)


class DesbloqueoFuente(AuthView):
    """Levanta el bloqueo por HTTP 429/503 con motivo y auditoría; no inicia ninguna captura."""
    permission_classes = [AdministradorActivo]
    http_method_names = ['post', 'options']

    def post(self, request, pk):
        if not isinstance(request.data, dict) or set(request.data) != {'motivo', 'clave_accion'}:
            return Response({'detail': 'Indica motivo y clave de acción.'}, status=400)
        if not Fuente.objects.filter(pk=pk).exists():
            return Response({'detail': 'Fuente inexistente.'}, status=404)
        try:
            row, created = unlock_source(pk, request.user.pk, request.data['motivo'], request.data['clave_accion'])
        except ValidationError as exc:
            return Response({'detail': ' '.join(exc.messages)}, status=400)
        return Response({'revision_id': row.pk, 'fuente_id': row.fuente_id, 'creado': created,
                         'detalle': row.detalle, 'motivo': row.motivo, 'actor_id': row.actor_id},
                        status=201 if created else 200)
