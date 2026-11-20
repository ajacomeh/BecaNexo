from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.exceptions import MethodNotAllowed
from usuarios.api import AuthView
from convocatorias.api import parametros, paginar
from .api import AdministradorActivo, identified
from .models import Publicacion, Propuesta
from .propuestas import guardar, representar, evaluar, latest
from .revisiones import vigentes
from .integracion import crear_borrador, representar_aplicacion, resolver_pendiente, estado_publicacion_integrada
from .models import Revision
from .propuestas import digest
from convocatorias.models import Convocatoria
from convocatorias.services import detalle


class Propuestas(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['get', 'post', 'patch', 'options']

    def get(self, request, pk=None, publication=None):
        parametros(request, {'page', 'page_size'} if publication else set())
        if pk is not None:
            obj = identified(Propuesta, pk)
            result = representar(obj)
            applied = Revision.objects.filter(propuesta=obj, dimension='integracion', decision='aplicada').select_related('convocatoria').first()
            result['aplicacion'] = representar_aplicacion(applied) if applied else None
            return Response(result)
        source = identified(Publicacion, publication)
        rows = Propuesta.objects.filter(publicacion=source).select_related('actor').order_by('-id')
        result = paginar(request, rows, representar)
        from convocatorias.models import BorradorRastreo
        automatic = BorradorRastreo.objects.filter(publicacion=source).first()
        result.data['borrador_automatico_id'] = automatic.convocatoria_id if automatic else None
        obs = latest(publication)
        result.data['contexto'] = {'version_id': obs.version_id, 'observacion_base_id': obs.pk,
                              'revisiones': list(vigentes(obs.version_id).values_list('pk', flat=True))} if obs else None
        applied = Revision.objects.filter(propuesta__publicacion=source, dimension='integracion', decision='aplicada').select_related('convocatoria').first()
        result.data['aplicacion'] = representar_aplicacion(applied) if applied else None
        return result

    def post(self, request, publication=None, pk=None):
        if publication is None:
            raise MethodNotAllowed('POST')
        parametros(request, set())
        identified(Publicacion, publication)
        obj, created = guardar(request.user.pk, publication, request.data)
        return Response(representar(obj), status=201 if created else 200)

    def patch(self, request, pk=None, publication=None):
        if pk is None:
            raise MethodNotAllowed('PATCH')
        parametros(request, set())
        old = identified(Propuesta, pk)
        obj, _ = guardar(request.user.pk, old.publicacion_id, request.data, previous=old.pk)
        return Response(representar(obj))


class ValidarPropuesta(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['post', 'options']

    def post(self, request, pk):
        parametros(request, set())
        if request.data != {}:
            raise serializers.ValidationError('La validación utiliza el snapshot guardado; no acepta campos.')
        obj = identified(Propuesta, pk)
        from convocatorias.models import BorradorRastreo
        automatic = BorradorRastreo.objects.filter(publicacion=obj.publicacion).first()
        actual = evaluar(obj.version, obj.observacion_base_id, obj.datos, obj.procedencia,
                        list(obj.revisiones.values_list('revision_id', flat=True)),
                        automatic.convocatoria_id if automatic else None)
        return Response({'guardado': obj.pendientes, 'actual': actual, 'contexto_cambio': actual != obj.pendientes})


class CrearBorrador(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['post', 'options']

    def post(self, request, pk):
        parametros(request, set())
        identified(Propuesta, pk)
        applied, created = crear_borrador(request.user.pk, pk, request.data)
        return Response(representar_aplicacion(applied), status=201 if created else 200)


class AplicarPropuestaBorrador(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['post', 'options']

    def post(self, request, pk):
        parametros(request, set())
        if set(request.data) != {'version_convocatoria', 'hash_propuesta', 'campos', 'motivo'}:
            raise serializers.ValidationError('Indica versión, hash, campos seleccionados y motivo.')
        from .aplicar_propuesta import ALLOWED_FIELDS, apply_proposal
        version = serializers.IntegerField(min_value=1).run_validation(request.data['version_convocatoria'])
        proposal_hash = serializers.RegexField(r'^[0-9a-f]{64}$').run_validation(request.data['hash_propuesta'])
        fields = serializers.ListField(child=serializers.ChoiceField(choices=sorted(ALLOWED_FIELDS)), min_length=1).run_validation(request.data['campos'])
        reason = serializers.CharField(max_length=1000, trim_whitespace=True).run_validation(request.data['motivo'])
        return Response(apply_proposal(pk, request.user.pk, version, proposal_hash, fields, reason))


class OrigenBorrador(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['get', 'post', 'options']

    def get(self, request, pk):
        parametros(request, set())
        offer = identified(Convocatoria, pk)
        applied = Revision.objects.filter(convocatoria=offer, dimension='integracion', decision='aplicada').select_related('propuesta').first()
        if not applied:
            from convocatorias.models import BorradorRastreo
            auto = BorradorRastreo.objects.filter(convocatoria=offer).select_related('publicacion', 'version').first()
            if auto:
                from .auto_borradores import latest_version, materially_changed, version_confirmed, review_baseline
                from .llenado import evidencia_visible
                from convocatorias.services import errores_publicacion
                current = latest_version(auto.publicacion)
                evidence_version = current or auto.version
                extracted = evidence_version.datos_extraidos or {}
                return Response({'aplicacion': None, 'automatico': True, 'publicacion_id': auto.publicacion_id,
                    'version_id': auto.version_id,
                    'enlaces_origen': {'publicacion': auto.publicacion.url_original,
                        'bases': extracted.get('enlaces_bases') or [],
                        'postulacion': extracted.get('enlaces_postulacion') or []},
                    'version_actual_id': current.pk if current else None,
                    'cambio_relevante': materially_changed(review_baseline(auto, offer), current),
                    'revision_confirmada': version_confirmed(offer, current) if current else False,
                    'version_convocatoria': offer.version,
                    'para_publicar': errores_publicacion(offer, estricto=False),
                    'evidencia': evidencia_visible(auto)})
            return Response({'aplicacion': None})
        source = applied.propuesta
        return Response({'aplicacion': representar_aplicacion(applied), 'publicacion_id': source.publicacion_id,
            'version_id': source.version_id, 'observacion_base_id': source.observacion_base_id,
            'estado': estado_publicacion_integrada(offer), 'version_convocatoria': offer.version,
            'hash_convocatoria': digest(detalle(offer)),
            'resoluciones': [{'id': row.pk, 'pendiente_id': row.detalle.get('pendiente_id'), 'motivo': row.motivo,
                             'opcion_candidata_id': row.detalle.get('opcion_candidata_id'),
                             'opcion_estudio_id': row.detalle.get('opcion_estudio_id'),
                             'evidencia_id': row.detalle.get('evidencia_id'), 'creada_en': row.creada_en}
                            for row in Revision.objects.filter(aplicacion=applied, dimension='integracion', decision='resuelta').order_by('id')]})

    def post(self, request, pk):
        parametros(request, set())
        identified(Convocatoria, pk)
        from convocatorias.models import BorradorRastreo
        if BorradorRastreo.objects.filter(convocatoria_id=pk).exists():
            if set(request.data) != {'version_id', 'version_convocatoria', 'motivo'}:
                raise serializers.ValidationError('Confirma únicamente versión, versión del borrador y motivo.')
            from .auto_borradores import confirm_latest_version
            version_id = serializers.IntegerField(min_value=1).run_validation(request.data['version_id'])
            offer_version = serializers.IntegerField(min_value=1).run_validation(request.data['version_convocatoria'])
            version, created = confirm_latest_version(pk, version_id, offer_version, request.user.pk, request.data['motivo'])
            return Response({'version_id': version.pk, 'confirmada': True}, status=201 if created else 200)
        row, created = resolver_pendiente(request.user.pk, pk, request.data)
        return Response({'id': row.pk, 'pendiente_id': row.detalle['pendiente_id']}, status=201 if created else 200)
