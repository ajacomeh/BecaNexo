from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.response import Response
from usuarios.api import AuthView
from convocatorias.services import campos_conocimiento, publicas
from .models import Notificacion, PreferenciaCorreo
from .services import texto_cierre


class PostulanteActivo(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_active and request.user.rol == "postulante"


def representar(aviso, publicas_ids, campos=None):
    disponible = aviso.convocatoria_id in publicas_ids
    return {"id": aviso.pk, "convocatoria_id": aviso.convocatoria_id,
            "titulo": aviso.convocatoria.titulo if disponible else "Convocatoria no disponible públicamente",
            "motivos": aviso.motivos,
            "creada_en": aviso.creada_en, "leida_en": aviso.leida_en, "disponible": disponible,
            # Área única de la convocatoria (icono de la tarjeta); None si no está disponible, tiene varias o ninguna.
            "campo_conocimiento": (campos or {}).get(aviso.convocatoria_id) if disponible else None,
            # «publicacion» o «cierre_proximo»; para este último, la fecha de cierre en el mismo texto que el correo.
            "tipo": aviso.tipo,
            "cierre_texto": texto_cierre(aviso.convocatoria) if disponible and aviso.tipo == "cierre_proximo" else None}


class Bandeja(AuthView):
    permission_classes = [PostulanteActivo]
    http_method_names = ["get", "options"]

    def get(self, request):
        params = request.query_params
        if any(k not in {"page", "page_size"} or len(params.getlist(k)) != 1 for k in params):
            raise serializers.ValidationError({"detail": "Parámetro desconocido o repetido."})
        try:
            page = int(params.get("page", 1))
            size = int(params.get("page_size", 10))
        except (TypeError, ValueError):
            raise serializers.ValidationError({"detail": "Página y tamaño deben ser enteros."})
        if page < 1 or not 1 <= size <= 20:
            raise serializers.ValidationError({"detail": "Página o tamaño fuera de rango."})
        qs = Notificacion.objects.filter(usuario=request.user).select_related("convocatoria")
        count = qs.count()
        unread = qs.filter(leida_en=None).count()
        items = list(qs[(page - 1) * size: page * size])
        publicas_ids = set(publicas().filter(pk__in=[item.convocatoria_id for item in items]).values_list("id", flat=True))
        campos = campos_conocimiento(publicas_ids)
        return Response({"count": count, "no_leidas": unread, "page": page, "page_size": size,
                         "results": [representar(item, publicas_ids, campos) for item in items]})


class MarcarLeida(AuthView):
    permission_classes = [PostulanteActivo]
    http_method_names = ["post", "options"]

    def post(self, request, pk):
        if request.query_params or request.data:
            raise serializers.ValidationError({"detail": "Esta acción no acepta datos."})
        qs = Notificacion.objects.filter(usuario=request.user, pk=pk)
        qs.filter(leida_en__isnull=True).update(leida_en=timezone.now())
        aviso = get_object_or_404(qs)
        return Response({"id": aviso.pk, "leida_en": aviso.leida_en})


class PreferenciaEmail(AuthView):
    permission_classes = [PostulanteActivo]
    http_method_names = ["get", "patch", "options"]

    def get(self, request):
        if request.query_params:
            raise serializers.ValidationError({"detail": "Esta consulta no acepta parámetros."})
        habilitado = (PreferenciaCorreo.objects.filter(usuario=request.user, habilitada=True).exists()
                      if settings.AVISOS_CORREO_HABILITADOS else False)
        return Response({"habilitado": habilitado, "disponible": settings.AVISOS_CORREO_HABILITADOS})

    def patch(self, request):
        if request.query_params or set(request.data) != {"habilitado"} or type(request.data["habilitado"]) is not bool:
            raise serializers.ValidationError({"habilitado": "Indica true o false, sin otros campos."})
        if not settings.AVISOS_CORREO_HABILITADOS:
            return Response({"detail": "El correo aún no está habilitado."}, status=503)
        pref, _ = PreferenciaCorreo.objects.get_or_create(usuario=request.user)
        # actualizada_en marca el último cambio real: con el correo activado es la fecha de activación, y solo los
        # avisos posteriores se envían. Repetir el mismo valor no la mueve.
        if pref.habilitada != request.data["habilitado"]:
            pref.habilitada = request.data["habilitado"]
            pref.actualizada_en = timezone.now()
            pref.save(update_fields=["habilitada", "actualizada_en"])
        return Response({"habilitado": pref.habilitada, "disponible": True})
