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
        actual = evaluar(obj.version, obj.observacion_base_id, obj.datos, obj.procedencia, list(obj.revisiones.values_list('revision_id', flat=True)))
        return Response({'guardado': obj.pendientes, 'actual': actual, 'contexto_cambio': actual != obj.pendientes})


class CrearBorrador(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['post', 'options']

    def post(self, request, pk):
        parametros(request, set())
        identified(Propuesta, pk)
        applied, created = crear_borrador(request.user.pk, pk, request.data)
        return Response(representar_aplicacion(applied), status=201 if created else 200)


class OrigenBorrador(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['get', 'post', 'options']

    def get(self, request, pk):
        parametros(request, set())
        offer = identified(Convocatoria, pk)
        applied = Revision.objects.filter(convocatoria=offer, dimension='integracion', decision='aplicada').select_related('propuesta').first()
        if not applied:
            return Response({'aplicacion': None})
        source = applied.propuesta
        return Response({'aplicacion': representar_aplicacion(applied), 'publicacion_id': source.publicacion_id,
            'version_id': source.version_id, 'observacion_base_id': source.observacion_base_id,
            'estado': estado_publicacion_integrada(offer), 'version_convocatoria': offer.version,
            'hash_convocatoria': digest(detalle(offer)),
            'resoluciones': [{'id': row.pk, 'pendiente_id': row.detalle.get('pendiente_id'), 'motivo': row.motivo,
                             'evidencia_id': row.detalle.get('evidencia_id'), 'creada_en': row.creada_en}
                            for row in Revision.objects.filter(aplicacion=applied, dimension='integracion', decision='resuelta').order_by('id')]})

    def post(self, request, pk):
        parametros(request, set())
        identified(Convocatoria, pk)
        row, created = resolver_pendiente(request.user.pk, pk, request.data)
        return Response({'id': row.pk, 'pendiente_id': row.detalle['pendiente_id']}, status=201 if created else 200)
