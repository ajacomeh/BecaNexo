"""Inicio y seguimiento administrativo de una ejecución manual de SIAU."""
import json
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response

from usuarios.api import AuthView
from .api import AdministradorActivo
from convocatorias.siau_red import INDEX
from .models import Ejecucion, Fuente
from .services import next_due, supported_policy
from .web_frequency import extraordinary_enabled, manual_window, source_blocked
from .web_launch import LaunchBusy, launch_lock, marker_path, result_path, start_worker


class ControlRastreo(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['get', 'post', 'options']

    @staticmethod
    def estado():
        fuente = get_object_or_404(Fuente, url_base=INDEX)
        ultima = Ejecucion.objects.filter(fuente=fuente).order_by('-inicio', '-id').first()
        activa = Ejecucion.objects.filter(fuente=fuente, estado='en_curso').first()
        proxima = next_due(fuente)
        extraordinaria = extraordinary_enabled()
        try:
            proxima_manual = manual_window(fuente) if extraordinaria else proxima
            registro_invalido = False
        except ValueError:
            proxima_manual, registro_invalido = None, True
        bloqueo_fuente = source_blocked(fuente) if extraordinaria else False
        marker = marker_path(fuente.pk)
        inicio_pendiente = marker.exists()
        requiere_revision = False
        if inicio_pendiente:
            try:
                json.loads(marker.read_text(encoding='utf-8'))
                # Un marcador antiguo exige revisión incluso si ya hay fila
                # en_curso: el trabajador pudo terminar abruptamente.
                requiere_revision = timezone.now().timestamp() - marker.stat().st_mtime > timedelta(minutes=2).total_seconds()
            except (OSError, ValueError, TypeError, AttributeError, ValidationError):
                requiere_revision = True
        try:
            resultado_web = json.loads(result_path(fuente.pk).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            resultado_web = None
        permitida = fuente.activa and fuente.adaptador == 'siau' and supported_policy(fuente) and not fuente.aprobada_publicacion_automatica
        puede_iniciar = (permitida and not activa and not inicio_pendiente and not registro_invalido
                        and not bloqueo_fuente and (not proxima_manual or proxima_manual <= timezone.now()))
        return {'fuente_id': fuente.pk, 'politica_version': fuente.politica_version,
                'frecuencia_min': fuente.frecuencia_min, 'proxima_ejecucion': proxima,
                'proxima_manual': proxima_manual, 'intervalo_manual_seg': 300 if extraordinaria else None,
                'rastreo_extraordinario_habilitado': extraordinaria,
                'bloqueo_fuente': bloqueo_fuente, 'registro_invalido': registro_invalido,
                'ejecucion_activa': activa.pk if activa else None,
                'inicio_pendiente': inicio_pendiente, 'requiere_revision': requiere_revision,
                'ultimo_inicio_web': resultado_web, 'puede_iniciar': puede_iniciar,
                'ultima_ejecucion': ({'id': ultima.pk, 'estado': ultima.estado, 'origen': ultima.origen,
                                      'inicio': ultima.inicio, 'fin': ultima.fin} if ultima else None)}

    def get(self, request):
        return Response(self.estado())

    def post(self, request):
        reason = request.data.get('motivo') if isinstance(request.data, dict) else None
        if (not isinstance(reason, str) or not reason.strip().isprintable()
                or len(reason.strip()) < 10 or len(reason.strip()) > 240
                or set(request.data) != {'motivo'}):
            return Response({'detail': 'Indica un motivo administrativo entre 10 y 240 caracteres.'}, status=400)
        try:
            with launch_lock():
                state = self.estado()
                if not state['puede_iniciar']:
                    return Response({'detail': 'La fuente no está disponible, hay una ejecución activa o aún no corresponde por frecuencia.',
                                     **state}, status=409)
                key = start_worker(state['fuente_id'], request.user.pk, reason.strip(),
                                   state['rastreo_extraordinario_habilitado'])
        except LaunchBusy:
            return Response({'detail': 'Ya existe una solicitud de inicio en proceso.'}, status=409)
        except OSError:
            return Response({'detail': 'No se pudo iniciar el proceso local; verifica el entorno del servidor.'}, status=503)
        return Response({'estado': 'iniciando', 'clave': str(key), 'fuente_id': state['fuente_id']}, status=202)
