from contextlib import contextmanager
from django.db import transaction, IntegrityError
from django.db.models import Q, F
from django.db.models.functions import Coalesce, TruncDate
from zoneinfo import ZoneInfo
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.response import Response
from usuarios.api import AuthView
from perfiles.api import CatalogosView as CatalogosPerfil
from perfiles.api import EsPostulante
from .comparacion import evaluar_convocatoria
from .recomendaciones import recomendar
from . import models as m, serializers as s
from .reglas import CONTRATOS, esquema
from .services import detalle, audit, touch, publicar, publicas


class Administrador(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.rol == "administrador"


@contextmanager
def escritura():
    try:
        with transaction.atomic(): yield
    except IntegrityError as exc:
        if getattr(exc.__cause__, "sqlstate", None) != "23505": raise
        raise serializers.ValidationError({"detail": "Ya existe ese registro o combinación. Revisa los datos."}) from exc


def parametros(request, allowed):
    for key in request.query_params:
        if key not in allowed or len(request.query_params.getlist(key)) != 1:
            raise serializers.ValidationError({key: "Parámetro desconocido o repetido."})


def entero(params, key, default, minimum=1, maximum=2147483647):
    try: value = int(params.get(key, default))
    except (ValueError, TypeError): raise serializers.ValidationError({key: "Debe ser un entero."})
    if not minimum <= value <= maximum: raise serializers.ValidationError({key: f"Debe estar entre {minimum} y {maximum}."})
    return value


def paginar(request, qs, render):
    page = entero(request.query_params, "page", 1)
    size = entero(request.query_params, "page_size", 12, maximum=50)
    count = qs.count()
    return Response({"count": count, "page": page, "page_size": size,
                     "results": [render(x) for x in qs[(page-1)*size:page*size]]})


class Catalogos(CatalogosPerfil):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        parametros(request, set())
        data = super().get(request).data
        data.update(tipos_beca=list(m.TipoBeca.objects.values("id", "nombre", "descripcion")),
                    tipos_requisito=[{"id": t.pk, "codigo": t.codigo, "nombre": t.nombre, "esquema_valor": esquema(t.codigo)}
                                     for t in m.TipoRequisito.objects.all() if t.codigo in CONTRATOS])
        return Response(data)


class Instituciones(AuthView):
    permission_classes = [Administrador]
    http_method_names = ["get", "post", "patch", "options"]

    def get(self, request, pk=None):
        parametros(request, {"page", "page_size", "q"})
        qs = m.Institucion.objects.select_related("pais")
        if pk is not None: return Response(s.InstitucionSerializer(get_object_or_404(qs, pk=pk)).data)
        query = request.query_params.get("q", "")
        if len(query) > 200: raise serializers.ValidationError({"q": "Máximo 200 caracteres."})
        return paginar(request, qs.filter(nombre__icontains=query), lambda x: s.InstitucionSerializer(x).data)

    def write(self, request, pk=None):
        with escritura():
            obj = get_object_or_404(m.Institucion.objects.select_for_update(), pk=pk) if pk else None
            before = s.InstitucionSerializer(obj).data if obj else None
            serializer = s.InstitucionSerializer(obj, data=request.data, partial=pk is not None)
            serializer.is_valid(raise_exception=True)
            obj = serializer.save()
            audit(request.user, "institucion_editar" if pk else "institucion_crear", before, serializer.data, institucion=obj)
            # Una modificación del oferente necesita nueva revisión de las ofertas asociadas.
            if pk:
                for conv in obj.convocatorias.select_for_update().order_by("id"):
                    snapshot = detalle(conv)
                    touch(conv)
                    audit(request.user, "oferente_modificado", snapshot, detalle(conv), convocatoria=conv)
            return Response(serializer.data, status=200 if pk else 201)

    def post(self, request, pk=None):
        return self.http_method_not_allowed(request) if pk else self.write(request)
    def patch(self, request, pk=None):
        return self.write(request, pk) if pk else self.http_method_not_allowed(request)


def filtrar(request, qs, admin=False):
    allowed = {"page", "page_size", "q", "nivel", "modalidad", "destino", "tipo_beca", "estado", "orden"}
    if admin: allowed.add("revision")
    parametros(request, allowed)
    p = request.query_params
    query = p.get("q", "").strip()
    if len(query) > 200: raise serializers.ValidationError({"q": "Máximo 200 caracteres."})
    if query: qs = qs.filter(Q(titulo__icontains=query) | Q(institucion__nombre__icontains=query) | Q(areas__area__nombre__icontains=query))
    options = {"activa": True}
    for key, choices in (("nivel", m.NIVELES), ("modalidad", m.MODALIDADES)):
        if key in p:
            if p[key] not in dict(choices): raise serializers.ValidationError({key: "Valor no permitido."})
            options[key] = p[key]
    if "destino" in p:
        if not m.Pais.objects.filter(codigo=p["destino"]).exists(): raise serializers.ValidationError({"destino": "País desconocido."})
        options["paises__codigo"] = p["destino"]
    if len(options) > 1:
        # Una única subconsulta garantiza que todos los atributos pertenezcan a la misma opción.
        qs = qs.filter(pk__in=m.OpcionEstudio.objects.filter(**options).values("convocatoria_id"))
    if "tipo_beca" in p:
        tipo = entero(p, "tipo_beca", 0)
        if not m.TipoBeca.objects.filter(pk=tipo).exists(): raise serializers.ValidationError({"tipo_beca": "Tipo desconocido."})
        qs = qs.filter(tipo_beca_id=tipo)
    now = timezone.now()
    today = timezone.localdate(now)
    current = Q(activa=True, revision="validada")
    started = Q(apertura__isnull=True) | Q(apertura__lte=now)
    states = {"abierta": current & started & (Q(cierre__gt=now) | Q(cierre_dia__gt=today)),
              "cerrada": current & (Q(cierre__lte=now) | Q(cierre_dia__lt=today)),
              "cierre_hoy": current & started & Q(cierre_dia=today),
              "proxima": current & Q(apertura__gt=now) & (Q(cierre__isnull=True) | Q(cierre__gt=now)) & (Q(cierre_dia__isnull=True) | Q(cierre_dia__gte=today)),
              "sin_fecha": current & started & Q(cierre__isnull=True, cierre_dia__isnull=True)}
    if admin: states.update(borrador=Q(activa=True, revision="pendiente"), pausada=Q(activa=False))
    if "estado" in p:
        if p["estado"] not in states: raise serializers.ValidationError({"estado": "Estado no permitido."})
        qs = qs.filter(states[p["estado"]])
    if "revision" in p:
        if p["revision"] not in dict(m.REVISIONES): raise serializers.ValidationError({"revision": "Revisión no permitida."})
        qs = qs.filter(revision=p["revision"])
    order = p.get("orden", "recientes")
    orders = {"recientes": ["-actualizado_en", "-id"], "titulo": ["titulo", "id"], "cierre": [F("fecha_cierre_orden").asc(nulls_last=True), "id"]}
    if order not in orders: raise serializers.ValidationError({"orden": "Orden no permitido."})
    if order == "cierre":
        qs = qs.annotate(fecha_cierre_orden=Coalesce("cierre_dia", TruncDate("cierre", tzinfo=ZoneInfo("America/Guayaquil"))))
    return qs.order_by(*orders[order]).distinct()


class Consulta(AuthView):
    permission_classes = [permissions.AllowAny]
    http_method_names = ["get", "options"]

    def get(self, request, pk=None):
        qs = publicas()
        postulante = request.user.is_authenticated and request.user.rol == "postulante"
        if postulante:
            from django.db.models import OuterRef, Subquery
            from favoritos.models import Favorito
            qs = qs.annotate(favorito_id=Subquery(Favorito.objects.filter(usuario=request.user, convocatoria_id=OuterRef("pk")).values("pk")[:1]))
        def render(obj):
            data = detalle(obj, publico=True)
            if postulante: data["favorito_id"] = obj.favorito_id
            return data
        if pk is not None:
            parametros(request, set())
            return Response(render(get_object_or_404(qs, pk=pk)))
        return paginar(request, filtrar(request, qs), render)


class Comparacion(AuthView):
    permission_classes = [EsPostulante]
    http_method_names = ["get", "options"]

    def get(self, request, pk):
        parametros(request, set())
        if request.data:
            raise serializers.ValidationError({"detail": "Esta consulta no acepta campos ni un usuario objetivo."})
        convocatoria = get_object_or_404(publicas(), pk=pk)
        return Response(evaluar_convocatoria(request.user, convocatoria))


class Recomendaciones(AuthView):
    permission_classes = [EsPostulante]
    http_method_names = ["get", "options"]

    def get(self, request):
        parametros(request, set())
        return Response({"results": recomendar(request.user),
                         "aviso": "La afinidad temática no acredita requisitos ni predice la adjudicación. Revisa las condiciones de cada convocatoria."})


class Convocatorias(AuthView):
    permission_classes = [Administrador]
    http_method_names = ["get", "post", "patch", "options"]

    def get(self, request, pk=None):
        qs = m.Convocatoria.objects.select_related("institucion", "tipo_beca")
        if pk is not None:
            parametros(request, set())
            return Response(detalle(get_object_or_404(qs, pk=pk)))
        return paginar(request, filtrar(request, qs, True), detalle)

    def write(self, request, pk=None):
        with escritura():
            # Orden único de locks: oferente antes de convocatoria.
            institution_id = request.data.get("institucion") if isinstance(request.data, dict) else None
            old_id = m.Convocatoria.objects.filter(pk=pk).values_list("institucion_id", flat=True).first() if pk else None
            ids = [x for x in (institution_id, old_id) if isinstance(x, int)]
            list(m.Institucion.objects.select_for_update().filter(pk__in=ids).order_by("id"))
            obj = get_object_or_404(m.Convocatoria.objects.select_for_update(), pk=pk) if pk else None
            before = detalle(obj) if obj else None
            serializer = s.ConvocatoriaSerializer(obj, data=request.data, partial=pk is not None)
            serializer.is_valid(raise_exception=True)
            obj = serializer.save()
            if pk: touch(obj)
            result = detalle(obj)
            audit(request.user, "convocatoria_editar" if pk else "convocatoria_crear", before, result, convocatoria=obj)
            return Response(result, status=200 if pk else 201)

    def post(self, request, pk=None):
        return self.http_method_not_allowed(request) if pk else self.write(request)
    def patch(self, request, pk=None):
        return self.write(request, pk) if pk else self.http_method_not_allowed(request)


RECURSOS = {"opciones": (m.OpcionEstudio, s.OpcionSerializer), "beneficios": (m.Beneficio, s.BeneficioSerializer), "requisitos": (m.Requisito, s.RequisitoSerializer)}


class Hijos(AuthView):
    permission_classes = [Administrador]
    http_method_names = ["get", "post", "patch", "delete", "options"]
    recurso = None

    def get(self, request, convocatoria, pk=None):
        parametros(request, {"page", "page_size"})
        get_object_or_404(m.Convocatoria, pk=convocatoria)
        model, serializer = RECURSOS[self.recurso]
        qs = model.objects.filter(convocatoria_id=convocatoria)
        if pk: return Response(serializer(get_object_or_404(qs, pk=pk)).data)
        return paginar(request, qs, lambda x: serializer(x).data)

    def write(self, request, convocatoria, pk=None, delete=False):
        model, serializer_type = RECURSOS[self.recurso]
        with escritura():
            obj = get_object_or_404(m.Convocatoria.objects.select_for_update(), pk=convocatoria)
            child = get_object_or_404(model.objects.filter(convocatoria=obj), pk=pk) if pk else None
            before = detalle(obj)
            if delete:
                if request.data: raise serializers.ValidationError({"detail": "La eliminación no acepta campos."})
                if self.recurso != "beneficios":
                    raise serializers.ValidationError({"detail": "Desactiva el registro para conservar su historial."})
                child.delete()
            else:
                serializer = serializer_type(child, data=request.data, partial=pk is not None, context={"convocatoria": obj})
                serializer.is_valid(raise_exception=True)
                serializer.save(convocatoria=obj)
            touch(obj)
            audit(request.user, f"{self.recurso}_{'eliminar' if delete else 'editar' if pk else 'crear'}", before, detalle(obj), convocatoria=obj)
            return Response(status=204) if delete else Response(serializer.data, status=200 if pk else 201)

    def post(self, request, convocatoria, pk=None):
        return self.http_method_not_allowed(request) if pk else self.write(request, convocatoria)
    def patch(self, request, convocatoria, pk=None):
        return self.write(request, convocatoria, pk) if pk else self.http_method_not_allowed(request)
    def delete(self, request, convocatoria, pk=None):
        return self.write(request, convocatoria, pk, True) if pk else self.http_method_not_allowed(request)


class Accion(AuthView):
    permission_classes = [Administrador]
    http_method_names = ["post", "options"]

    def post(self, request, pk, accion):
        if request.data: raise serializers.ValidationError({"detail": "Esta acción no acepta campos."})
        with escritura():
            institution_id = get_object_or_404(m.Convocatoria, pk=pk).institucion_id
            m.Institucion.objects.select_for_update().get(pk=institution_id)
            obj = get_object_or_404(m.Convocatoria.objects.select_for_update(), pk=pk)
            before = detalle(obj)
            if accion == "publicar": publicar(obj)
            else:
                obj.activa = False
                obj.version += 1
                obj.actualizado_en = timezone.now()
                obj.save()
            result = detalle(obj)
            audit(request.user, accion, before, result, convocatoria=obj)
            return Response(result)


class Auditoria(AuthView):
    permission_classes = [Administrador]
    http_method_names = ["get", "options"]

    def get(self, request, pk):
        parametros(request, {"page", "page_size"})
        get_object_or_404(m.Convocatoria, pk=pk)
        return paginar(request, m.Evento.objects.filter(convocatoria_id=pk),
                       lambda e: {"id": e.pk, "accion": e.accion, "creado_en": e.creado_en, "cambios": e.cambios})
