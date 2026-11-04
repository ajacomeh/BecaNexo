from contextlib import contextmanager
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.response import Response
from usuarios.api import AuthView
from . import models as m, serializers as s


class EsPostulante(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.rol == "postulante"


@contextmanager
def escritura(user):
    # Serializa también la creación inicial: aún puede no existir la fila de perfil.
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        yield


def incrementar(perfil):
    m.Perfil.objects.filter(pk=perfil.pk).update(version=F("version") + 1, actualizado_en=timezone.now())


class PerfilView(AuthView):
    permission_classes = [EsPostulante]
    http_method_names = ["get", "patch", "options"]

    def get(self, request):
        perfil = m.Perfil.objects.filter(usuario=request.user).first()
        return Response({"perfil": s.PerfilSerializer(perfil).data if perfil else None})

    def patch(self, request):
        with escritura(request.user):
            perfil = m.Perfil.objects.filter(usuario=request.user).first()
            if perfil is None and not m.Pais.objects.filter(codigo="EC").exists():
                return Response({"detail": "Falta Ecuador en el catálogo de países."}, status=503)
            serializer = s.PerfilSerializer(perfil, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            if perfil is None:
                perfil = serializer.save(usuario=request.user)
                status = 201
            else:
                perfil = serializer.save()
                incrementar(perfil)
                perfil.refresh_from_db()
                status = 200
            return Response({"perfil": s.PerfilSerializer(perfil).data}, status=status)


class CatalogosView(AuthView):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "options"]

    def get(self, request):
        def choices(values): return [{"valor": v, "nombre": n} for v, n in values]
        return Response({
            "paises": list(m.Pais.objects.values("id", "codigo", "nombre")),
            "idiomas": list(m.Idioma.objects.values("id", "codigo", "nombre")),
            "areas": list(m.Area.objects.values("id", "nombre")),
            "niveles": choices(m.NIVELES), "modalidades": choices(m.MODALIDADES),
            "niveles_idioma": choices(m.MCER), "estados": choices(m.ESTADOS), "dedicaciones": choices(m.DEDICACIONES),
        })


RECURSOS = {
    "formaciones": (m.Formacion, s.FormacionSerializer),
    "experiencias": (m.Experiencia, s.ExperienciaSerializer),
    "idiomas": (m.PerfilIdioma, s.IdiomaSerializer),
    "areas": (m.PerfilArea, s.AreaSerializer),
    "preferencias": (m.Preferencia, s.PreferenciaSerializer),
    "destinos": (m.PerfilPais, s.DestinoSerializer),
}


class RelacionView(AuthView):
    permission_classes = [EsPostulante]
    recurso = None
    http_method_names = ["get", "post", "patch", "delete", "options"]

    def get(self, request, pk=None):
        model, serializer = RECURSOS[self.recurso]
        qs = model.objects.filter(perfil__usuario=request.user)
        return Response(serializer(get_object_or_404(qs, pk=pk)).data if pk is not None else serializer(qs, many=True).data)

    def mutate(self, request, pk=None, delete=False):
        model, serializer_type = RECURSOS[self.recurso]
        try:
            with escritura(request.user):
                # Los IDs ajenos y los inexistentes siempre producen el mismo 404.
                instance = get_object_or_404(model.objects.filter(perfil__usuario=request.user), pk=pk) if pk is not None else None
                perfil = m.Perfil.objects.filter(usuario=request.user).first()
                if perfil is None:
                    return Response({"detail": "Guarda primero los datos personales del perfil."}, status=409)
                if delete:
                    if request.data:
                        raise serializers.ValidationError({"detail": "La eliminación no acepta campos."})
                    instance.delete()
                    incrementar(perfil)
                    return Response(status=204)
                serializer = serializer_type(instance, data=request.data, partial=pk is not None)
                serializer.is_valid(raise_exception=True)
                serializer.save(perfil=perfil)
                incrementar(perfil)
                return Response(serializer.data, status=200 if pk is not None else 201)
        except IntegrityError as exc:
            if getattr(exc.__cause__, "sqlstate", None) != "23505": raise
            field = {"idiomas": "idioma", "areas": "area", "preferencias": "modalidad", "destinos": "pais"}.get(self.recurso, "non_field_errors")
            raise serializers.ValidationError({field: "Esta selección ya está registrada en tu perfil."}) from exc

    def post(self, request): return self.mutate(request)
    def patch(self, request, pk): return self.mutate(request, pk)
    def delete(self, request, pk): return self.mutate(request, pk, delete=True)
