from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.exceptions import MethodNotAllowed
from usuarios.api import AuthView
from convocatorias.api import parametros, paginar
from .api import AdministradorActivo, identified
from .models import Publicacion, Propuesta
from .propuestas import guardar, representar, evaluar, latest
from .revisiones import vigentes


class Propuestas(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['get', 'post', 'patch', 'options']

    def get(self, request, pk=None, publication=None):
        parametros(request, {'page', 'page_size'} if publication else set())
        if pk is not None:
            return Response(representar(identified(Propuesta, pk)))
        source = identified(Publicacion, publication)
        rows = Propuesta.objects.filter(publicacion=source).select_related('actor').order_by('-id')
        result = paginar(request, rows, representar)
        obs = latest(publication)
        result.data['contexto'] = {'version_id': obs.version_id, 'observacion_base_id': obs.pk,
                              'revisiones': list(vigentes(obs.version_id).values_list('pk', flat=True))} if obs else None
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
