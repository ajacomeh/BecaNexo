from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from usuarios.api import AuthView
from perfiles.api import EsPostulante
from convocatorias.api import parametros, paginar
from convocatorias.services import publicas
from .models import Favorito


class GuardarSerializer(serializers.Serializer):
    convocatoria = serializers.IntegerField(min_value=1)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - {"convocatoria"}:
            raise serializers.ValidationError({key: "Campo no permitido." for key in set(data) - {"convocatoria"}})
        return super().to_internal_value(data)


def representar(fav, disponibles):
    convocatoria = disponibles.get(fav.convocatoria_id)
    if convocatoria is None:
        return {"id": fav.pk, "disponible": False, "convocatoria": None,
                "aviso": "Esta oportunidad ya no está disponible."}
    return {"id": fav.pk, "creado_en": fav.creado_en, "disponible": True, "convocatoria": {
        "id": convocatoria.pk, "titulo": convocatoria.titulo, "institucion": convocatoria.institucion.nombre,
        "tipo_beca": convocatoria.tipo_beca.nombre if convocatoria.tipo_beca else None,
        "estado": convocatoria.estado, "cierre": convocatoria.cierre}}


class Lista(AuthView):
    permission_classes = [EsPostulante]
    http_method_names = ["get", "post", "options"]

    def get(self, request):
        parametros(request, {"page", "page_size"})
        qs = Favorito.objects.filter(usuario=request.user)
        # Primero se pagina, después se consultan solo ofertas públicas de esa página.
        response = paginar(request, qs, lambda f: f)
        rows = response.data["results"]
        disponibles = {c.pk: c for c in publicas().filter(pk__in=[f.convocatoria_id for f in rows])}
        response.data["results"] = [representar(f, disponibles) for f in rows]
        return response

    def post(self, request):
        parametros(request, set())
        serializer = GuardarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            # Serializa con cambios de publicación y otros guardados de la misma oferta.
            convocatoria = get_object_or_404(publicas().select_for_update(of=("self",)), pk=serializer.validated_data["convocatoria"])
            favorito, created = Favorito.objects.get_or_create(usuario=request.user, convocatoria=convocatoria)
            return Response(representar(favorito, {convocatoria.pk: convocatoria}), status=201 if created else 200)


class Quitar(AuthView):
    permission_classes = [EsPostulante]
    http_method_names = ["delete", "options"]

    def delete(self, request, pk):
        parametros(request, set())
        if request.data:
            raise serializers.ValidationError({"detail": "La eliminación no acepta campos."})
        with transaction.atomic():
            favorito = get_object_or_404(Favorito.objects.select_for_update().filter(usuario=request.user), pk=pk)
            favorito.delete()
        return Response(status=204)
