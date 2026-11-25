from contextlib import contextmanager
from django.db import transaction, IntegrityError
from django.db.models import Case, Count, Exists, F, IntegerField, OuterRef, Q, Value, When
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
from .services import descartado, detalle, audit, touch, publicar, publicas, postulables, con_contadores, eliminar_institucion, EntidadConConvocatoriasPublicas, muestra_publicas


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


def paginar(request, qs, render, default_size=12):
    page = entero(request.query_params, "page", 1)
    size = entero(request.query_params, "page_size", default_size, maximum=50)
    count = qs.count()
    return Response({"count": count, "page": page, "page_size": size,
                     "results": [render(x) for x in qs[(page-1)*size:page*size]]})


class Catalogos(CatalogosPerfil):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        parametros(request, set())
        data = super().get(request).data
        data.update(niveles_opcion=[{"valor": value, "nombre": label} for value, label in m.NIVELES_OPCION],
                    tipos_beca=list(m.TipoBeca.objects.values("id", "nombre", "descripcion")),
                    tipos_requisito=[{"id": t.pk, "codigo": t.codigo, "nombre": t.nombre, "esquema_valor": esquema(t.codigo)}
                                     for t in m.TipoRequisito.objects.all() if t.codigo in CONTRATOS])
        return Response(data)


class Instituciones(AuthView):
    permission_classes = [Administrador]
    http_method_names = ["get", "post", "patch", "delete", "options"]

    def get(self, request, pk=None):
        parametros(request, {"page", "page_size", "q"})
        qs = m.Institucion.objects.select_related("pais")
        if pk is not None:
            obj = get_object_or_404(con_contadores(qs), pk=pk)
            # Contadores y una muestra breve de convocatorias públicas para explicar por qué no se puede eliminar.
            return Response({**s.InstitucionSerializer(obj).data, "convocatorias_publicas": obj.convocatorias_publicas,
                             "borradores_privados": obj.borradores_privados, "muestra_publicas": muestra_publicas(obj)})
        query = request.query_params.get("q", "")
        if len(query) > 200: raise serializers.ValidationError({"q": "Máximo 200 caracteres."})
        # Contadores por entidad (anotaciones, sin N+1): convocatorias en el catálogo público y borradores privados.
        return paginar(request, con_contadores(qs.filter(nombre__icontains=query)), lambda x: {
            **s.InstitucionSerializer(x).data, "convocatorias_publicas": x.convocatorias_publicas, "borradores_privados": x.borradores_privados})

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

    def delete(self, request, pk=None):
        if pk is None: return self.http_method_not_allowed(request)
        parametros(request, set())
        try:
            with escritura():
                obj = get_object_or_404(m.Institucion.objects.select_for_update(of=("self",)).select_related("pais"), pk=pk)
                resumen = eliminar_institucion(obj, request.user)
        except EntidadConConvocatoriasPublicas as exc:
            return Response({"detail": str(exc), "convocatorias_publicas": exc.n, "muestra_publicas": exc.muestra}, status=409)
        return Response(resumen, status=200)


INCLUIR_NO_ECUATORIANAS = {"1": True, "true": True, "0": False, "false": False}


AMBITOS_DESTINO = ("ecuador", "exterior")


def destino_q(ambito=None, codigo=None):
    """Condición sobre una opción de estudio: un país concreto, Ecuador o algún destino distinto de Ecuador."""
    paises = m.OpcionPais.objects.filter(opcion_estudio=OuterRef("pk"))
    if codigo is not None: return Exists(paises.filter(pais__codigo=codigo))
    if ambito == "ecuador": return Exists(paises.filter(pais__codigo="EC"))
    return Exists(paises.exclude(pais__codigo="EC"))


def filtrar(request, qs, admin=False, facetas=False):
    allowed = {"page", "page_size", "q", "nivel", "modalidad", "destino", "tipo_beca", "estado", "orden"}
    allowed |= {"revision"} if admin else {"incluir_no_ecuatorianas", "destino_ambito"}
    parametros(request, allowed)
    p = request.query_params
    if not admin:
        # Catálogo público: por defecto solo convocatorias con entidad oferente ecuatoriana asignada (toda entidad
        # del catálogo de instituciones es ecuatoriana). Las demás, solo si se piden de forma expresa.
        incluir = p.get("incluir_no_ecuatorianas", "false").lower()
        if incluir not in INCLUIR_NO_ECUATORIANAS:
            raise serializers.ValidationError({"incluir_no_ecuatorianas": "Usa true o false."})
        if not INCLUIR_NO_ECUATORIANAS[incluir]:
            qs = qs.filter(institucion__isnull=False)
    query = p.get("q", "").strip()
    if len(query) > 200: raise serializers.ValidationError({"q": "Máximo 200 caracteres."})
    # Condiciones que debe cumplir una misma opción de estudio, por dimensión (nivel, modalidad y destino).
    condiciones = {}
    for key, choices in (("nivel", m.NIVELES_OPCION), ("modalidad", m.MODALIDADES)):
        if key in p:
            if p[key] not in dict(choices): raise serializers.ValidationError({key: "Valor no permitido."})
            condiciones[key] = Q(**{key: p[key]})
    if "destino" in p and "destino_ambito" in p:
        raise serializers.ValidationError({"destino_ambito": "No combines el destino rápido con un país concreto."})
    if "destino" in p:
        if not m.Pais.objects.filter(codigo=p["destino"]).exists(): raise serializers.ValidationError({"destino": "País desconocido."})
        condiciones["destino"] = destino_q(codigo=p["destino"])
    if "destino_ambito" in p:
        if p["destino_ambito"] not in AMBITOS_DESTINO: raise serializers.ValidationError({"destino_ambito": "Usa ecuador o exterior."})
        condiciones["destino"] = destino_q(ambito=p["destino_ambito"])
    if "tipo_beca" in p:
        tipo = entero(p, "tipo_beca", 0)
        if not m.TipoBeca.objects.filter(pk=tipo).exists(): raise serializers.ValidationError({"tipo_beca": "Tipo desconocido."})
        qs = qs.filter(tipo_beca_id=tipo)
    now = timezone.now()
    today = timezone.localdate(now)
    current = Q(activa=True, revision="validada")
    started = Q(apertura__isnull=True) | Q(apertura__lte=now)
    ongoing = Q(cierre__gt=now) | Q(cierre_dia__gte=today)
    states = {"todas": current,
              "vigentes": current & started & ongoing,
              "abierta": current & started & (Q(cierre__gt=now) | Q(cierre_dia__gt=today)),
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
    base = qs
    texto = (Q(titulo__icontains=query) | Q(institucion__nombre__icontains=query) |
             Q(areas__area__nombre__icontains=query) | Q(descripcion__icontains=query))

    def opciones(sin=None):
        return m.OpcionEstudio.objects.filter(*[c for k, c in condiciones.items() if k != sin], activa=True)

    if query:
        # Al buscar por programa, el texto y los filtros académicos deben pertenecer a la misma opción.
        qs = qs.filter(texto | Q(pk__in=opciones().filter(programa__icontains=query).values("convocatoria_id")))
    if condiciones:
        # Una única subconsulta garantiza que todos los atributos pertenezcan a la misma opción.
        qs = qs.filter(pk__in=opciones().values("convocatoria_id"))
    if order == "cierre":
        qs = qs.annotate(fecha_cierre_orden=Coalesce("cierre_dia", TruncDate("cierre", tzinfo=ZoneInfo("America/Guayaquil"))))
    qs = qs.order_by(*orders[order]).distinct()
    if not facetas: return qs

    def candidatas(sin):
        # Opciones con las que habría resultados si se eligiera su valor en la dimensión `sin`, manteniendo los demás
        # filtros (búsqueda facetada: el conteo de un selector no cuenta su propio filtro). Una convocatoria cuenta si
        # una misma opción cumple ese valor y las demás condiciones, y la búsqueda coincide en la convocatoria o en el
        # programa de esa opción; equivale exactamente a aplicar el valor junto con el resto de filtros.
        ops = opciones(sin).filter(convocatoria__in=base.values("pk"))
        if query: ops = ops.filter(Q(convocatoria__in=base.filter(texto).values("pk")) | Q(programa__icontains=query))
        return ops

    def conteo(sin, campo):
        filas = (candidatas(sin).exclude(**{f"{campo}__isnull": True}).values(campo)
                 .annotate(total=Count("convocatoria", distinct=True)).order_by(campo))
        return [{"valor": f[campo], "total": f["total"]} for f in filas]

    destinos = candidatas("destino")
    resumen = {"nivel": conteo("nivel", "nivel"), "modalidad": conteo("modalidad", "modalidad"),
               "destino": conteo("destino", "paises__codigo"),
               "destino_ambito": {a: destinos.filter(destino_q(ambito=a)).aggregate(total=Count("convocatoria", distinct=True))["total"]
                                  for a in AMBITOS_DESTINO}}
    return qs, resumen


class Consulta(AuthView):
    permission_classes = [permissions.AllowAny]
    http_method_names = ["get", "options"]

    def get(self, request, pk=None):
        qs = publicas() if pk is not None or request.query_params.get('estado') in ('cerrada', 'sin_fecha', 'proxima', 'todas') else postulables()
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
        # El listado público añade las facetas: valores presentes y su número de resultados según los demás filtros.
        resultados, facetas = filtrar(request, qs, facetas=True)
        respuesta = paginar(request, resultados, render)
        respuesta.data["facetas"] = facetas
        return respuesta


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
        render = lambda obj: detalle(obj, con_diagnostico=True)
        if pk is not None:
            parametros(request, set())
            return Response(render(get_object_or_404(qs, pk=pk)))
        return paginar(request, filtrar(request, qs, True), render)

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


def ya_eliminado(obj, recurso, pk):
    """El registro existió en esta convocatoria y una eliminación auditada lo quitó (directa o con su opción)."""
    for event in m.Evento.objects.filter(convocatoria=obj, accion__in=[f"{nombre}_eliminar" for nombre in RECURSOS]).only("cambios"):
        antes = {row.get("id") for row in (event.cambios.get("antes") or {}).get(recurso) or []}
        despues = {row.get("id") for row in (event.cambios.get("despues") or {}).get(recurso) or []}
        if pk in antes and pk not in despues:
            return True
    return False


def eliminar(obj, recurso, child):
    """Eliminación física sin dejar huérfanos. Una opción arrastra sus requisitos propios en la misma transacción."""
    if recurso == "opciones":
        if m.Beneficio.objects.filter(opcion_estudio=child).exists():
            raise serializers.ValidationError({"detail": "Esta opción tiene beneficios propios. Elimínalos o asígnalos a toda la "
                                                         "convocatoria antes de eliminar la opción."})
        if obj.revision == "validada" and child.activa and not obj.opciones.filter(activa=True).exclude(pk=child.pk).exists():
            raise serializers.ValidationError({"detail": "No se puede eliminar la última opción activa de una convocatoria publicada: "
                                                         "publicar exige al menos una opción activa. Añade o activa otra opción antes."})
        # Los requisitos propios de la opción (también los de un destino de esa opción) se eliminan con ella.
        m.Requisito.objects.filter(convocatoria=obj, opcion_estudio=child).delete()
    child.delete()


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
            if delete and request.data: raise serializers.ValidationError({"detail": "La eliminación no acepta campos."})
            if delete and not model.objects.filter(convocatoria=obj, pk=pk).exists() and ya_eliminado(obj, self.recurso, pk):
                # Idempotente: repetir la eliminación de un registro ya eliminado no cambia nada ni vuelve a auditar.
                return Response(status=204)
            child = get_object_or_404(model.objects.filter(convocatoria=obj), pk=pk) if pk else None
            before = detalle(obj)
            if delete:
                eliminar(obj, self.recurso, child)
            else:
                serializer = serializer_type(child, data=request.data, partial=pk is not None, context={"convocatoria": obj})
                serializer.is_valid(raise_exception=True)
                serializer.save(convocatoria=obj)
            # Una opción editada en una convocatoria ya pública se valida antes de
            # confirmar la transacción. Si falla, también se revierte la opción.
            # Eliminar, en cambio, devuelve la convocatoria a revisión pendiente, como cualquier otra edición.
            if self.recurso == "opciones" and not delete and obj.activa and obj.revision == "validada":
                publicar(obj)
            else:
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
        datos = dict(request.data) if hasattr(request.data, "keys") else request.data
        confirmar = False
        if accion == "publicar" and datos:
            # Único campo admitido: la confirmación expresa de publicar sin entidad oferente ecuatoriana.
            if set(datos) != {"confirmar_oferente_no_ecuatoriano"} or datos["confirmar_oferente_no_ecuatoriano"] is not True:
                raise serializers.ValidationError({"detail": "Solo se admite confirmar_oferente_no_ecuatoriano: true."})
            confirmar = True
        elif datos:
            raise serializers.ValidationError({"detail": "Esta acción no acepta campos."})
        with escritura():
            institution_id = get_object_or_404(m.Convocatoria, pk=pk).institucion_id
            if institution_id is not None:
                m.Institucion.objects.select_for_update().get(pk=institution_id)
            obj = get_object_or_404(m.Convocatoria.objects.select_for_update(), pk=pk)
            before = detalle(obj)
            if accion == "publicar": publicar(obj, request.user, confirmar)
            elif accion in ("descartar", "restaurar"):
                if not m.BorradorRastreo.objects.filter(convocatoria=obj).exists() or obj.revision == "validada":
                    raise serializers.ValidationError({"detail": "Solo se descarta o restaura un borrador privado del rastreo."})
                if (accion == "descartar") == descartado(obj):
                    raise serializers.ValidationError({"detail": "El borrador ya está descartado." if accion == "descartar" else "El borrador no está descartado."})
                result = detalle(obj)
                audit(request.user, f"{accion}_borrador", before, result, convocatoria=obj)
                return Response(detalle(obj))
            else:
                if not obj.activa or obj.revision != "validada":
                    raise serializers.ValidationError({"detail": "Solo se puede pausar una convocatoria publicada y activa."})
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
