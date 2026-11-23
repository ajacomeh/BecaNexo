import json
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError
from . import models as m, serializers as s
from .reglas import EXTERNOS


def publicas():
    # Sin entidad del catálogo solo hay borradores del rastreo publicados con confirmación expresa del administrador.
    return m.Convocatoria.objects.filter(activa=True, revision="validada").filter(
        Q(institucion__pais__codigo="EC") | Q(institucion__isnull=True)).select_related("institucion", "tipo_beca")


ACCIONES_DESCARTE = ("descartar_borrador", "restaurar_borrador")


def descartado(obj):
    """Un borrador del rastreo está descartado si su último evento de descarte o restauración es un descarte."""
    ultimo = m.Evento.objects.filter(convocatoria=obj, accion__in=ACCIONES_DESCARTE).order_by("-id").values_list("accion", flat=True).first()
    return ultimo == "descartar_borrador"


ACCION_OFERENTE_ELIMINADO = "oferente_eliminado"


def entidad_eliminada(obj):
    """Nombre de la entidad oferente eliminada que dejó a este borrador sin entidad; None si no aplica."""
    if obj.institucion_id:
        return None
    cambios = m.Evento.objects.filter(convocatoria=obj, accion=ACCION_OFERENTE_ELIMINADO).order_by("-id").values_list("cambios", flat=True).first()
    return ((cambios or {}).get("entidad_eliminada") or {}).get("nombre") if cambios else None


def oferente_sin_entidad(obj):
    """Para un borrador sin entidad del catálogo: (marca de oferente no ecuatoriano, nombre detectado).
    Un borrador manual cuya entidad se eliminó queda como «Oferente por confirmar» (sin nombre)."""
    if obj.institucion_id:
        return None
    origin = m.BorradorRastreo.objects.filter(convocatoria=obj).first()
    if not origin:
        return {"no_ecuatoriano": False, "nombre": None} if entidad_eliminada(obj) else None
    from rastreo.auto_borradores import oferente_externo
    no_ec, nombre = oferente_externo(origin)
    return {"no_ecuatoriano": no_ec, "nombre": nombre or None}


def aviso_oferente(obj):
    """Mensaje que exige la confirmación expresa al publicar sin entidad oferente ecuatoriana; None si no aplica."""
    if obj.institucion_id:
        return None
    externo = oferente_sin_entidad(obj) or {"no_ecuatoriano": False, "nombre": None}
    if externo["no_ecuatoriano"]:
        return "Esta beca no corresponde a una entidad oferente ecuatoriana" + (f" (oferente detectado: {externo['nombre']})" if externo["nombre"] else "")
    return "Esta beca no tiene una entidad oferente ecuatoriana asignada"


def postulables():
    """Solo oportunidades con plazo confirmado y vigente; el histórico sigue consultable."""
    now = timezone.now()
    today = timezone.localdate(now)
    return publicas().filter(Q(apertura__isnull=True) | Q(apertura__lte=now)).filter(
        Q(cierre__gt=now) | Q(cierre_dia__gte=today)
    )


def detalle(obj, publico=False, con_diagnostico=False):
    data = dict(s.ConvocatoriaSerializer(obj).data)
    data["institucion"] = s.InstitucionSerializer(obj.institucion).data if obj.institucion_id else None
    # Oferente detectado en la ficha cuando no hay entidad del catálogo (texto; nunca se registra como entidad).
    data["oferente_externo"] = oferente_sin_entidad(obj)
    if not publico:
        data["descartado"] = descartado(obj)
        data["aviso_oferente"] = aviso_oferente(obj)
        origin = m.BorradorRastreo.objects.filter(convocatoria=obj).select_related("publicacion__fuente", "version").first()
        data["origen_automatico"] = {"publicacion_id": origin.publicacion_id, "version_id": origin.version_id} if origin else None
        if con_diagnostico:
            data["diagnostico"] = diagnostico(obj)
    data["tipo_beca_nombre"] = obj.tipo_beca.nombre if obj.tipo_beca else None
    opciones = obj.opciones.filter(activa=True) if publico else obj.opciones.all()
    data["opciones"] = s.OpcionSerializer(opciones, many=True).data
    beneficios = obj.beneficios.all()
    requisitos = obj.requisitos.all()
    if publico:
        from django.db.models import Q
        beneficios = beneficios.filter(Q(opcion_estudio__isnull=True) | Q(opcion_estudio__activa=True))
        requisitos = requisitos.filter(activo=True).filter(Q(opcion_estudio__isnull=True) | Q(opcion_estudio__activa=True))
    data["beneficios"] = s.BeneficioSerializer(beneficios, many=True).data
    data["requisitos"] = s.RequisitoSerializer(requisitos, many=True).data
    if publico:
        for key in ("revision", "activa", "version"): data.pop(key, None)
        for opcion in data["opciones"]:
            opcion.pop("activa", None)
        for requisito in data["requisitos"]:
            for key in ("validado", "activo"):
                requisito.pop(key, None)
    return data


def audit(actor, accion, antes, despues, convocatoria=None, institucion=None):
    # Instantáneas de negocio, sin datos de cuentas ni cabeceras de sesión.
    cambios = json.loads(json.dumps({"origen": "manual", "antes": antes, "despues": despues}, cls=DjangoJSONEncoder))
    m.Evento.objects.create(actor=actor, accion=accion, convocatoria=convocatoria, institucion=institucion, cambios=cambios)


def touch(obj):
    obj.version += 1
    obj.actualizado_en = timezone.now()
    obj.revision = "pendiente"
    obj.save(update_fields=["version", "actualizado_en", "revision"])


def diagnostico(obj):
    """Lo que falta para publicar, con los mismos controles de publicar(), sin escribir nada."""
    if obj.revision == "validada":
        return {"pendientes_publicacion": [], "faltan": 0}
    pendientes = errores_publicacion(obj, estricto=False)
    return {"pendientes_publicacion": pendientes, "faltan": len(pendientes)}


def errores_publicacion(obj, estricto=True):
    """Controles de publicación. Con estricto=True un requisito inválido lanza su error, como siempre."""
    errors = []
    from rastreo.integracion import estado_publicacion_integrada
    origen = estado_publicacion_integrada(obj)
    if origen and (origen['bloqueos'] or origen['pendientes']):
        errors.append('La convocatoria integrada conserva revisiones de origen o pendientes materiales sin resolver. Consulta su procedencia antes de publicar.')
    auto_origin = m.BorradorRastreo.objects.filter(convocatoria=obj).select_related('publicacion', 'version').first()
    if auto_origin:
        from rastreo.auto_borradores import pending_for_publication
        errors.extend(pending_for_publication(obj, auto_origin))
    if obj.institucion_id and obj.institucion.pais.codigo != "EC":
        errors.append("El oferente identificado debe ser ecuatoriano.")
    # La falta de entidad oferente ecuatoriana ya no bloquea: publicar() exige la confirmación expresa del administrador.
    if not obj.institucion_id and not auto_origin and not entidad_eliminada(obj):
        errors.append("Asigna una institución oferente ecuatoriana antes de publicar.")
    if auto_origin and descartado(obj):
        errors.append("El borrador está descartado; restáuralo antes de publicar.")
    if not obj.titulo.strip() or not obj.descripcion.strip() or not obj.url_oficial:
        errors.append("Completa título, descripción y enlace oficial.")
    opciones = list(obj.opciones.filter(activa=True))
    if not opciones: errors.append("Añade al menos una opción activa.")
    # Los destinos desconocidos no se inventan: se permiten listas vacías y se muestran como no especificados.
    requisitos = list(obj.requisitos.filter(activo=True).select_related("tipo_requisito"))
    # Los requisitos activos sin validar no bloquean: publicar() los valida a nombre de quien publica.
    # Validar nuevamente reglas aunque se hayan insertado fuera de esta API.
    for r in requisitos:
        serializer = s.RequisitoSerializer(r, data=s.RequisitoSerializer(r).data, context={"convocatoria": obj})
        payload = dict(serializer.initial_data); payload.pop("id")
        serializer = s.RequisitoSerializer(r, data=payload, context={"convocatoria": obj})
        if estricto:
            serializer.is_valid(raise_exception=True)
        elif not serializer.is_valid():
            errors.append(f"Corrige el requisito «{r.texto_original[:80]}»: no cumple su contrato.")
    for opcion in opciones:
        for destino in list(opcion.paises.all()) or [None]:
            reglas = [r for r in requisitos if r.opcion_estudio_id in (None, opcion.pk) and
                      (r.destino_id is None or (destino and r.destino_id == destino.pk))]
            seen = set()
            for r in reglas:
                codigo = r.tipo_requisito.codigo
                if codigo in EXTERNOS: continue
                # Varias condiciones académicas sin relación definida ya dan «desconocido» en la comparación
                # (no se mezclan títulos distintos); no hace falta bloquear la publicación por ello.
                if codigo in ("FORMACION", "TITULO_AREA", "PROMEDIO") and r.relacion_formacion == "pendiente": continue
                discriminante = (r.valor_estructurado or {}).get("codigo_idioma") if codigo == "IDIOMA" else (r.valor_estructurado or {}).get("area") if codigo == "EXPERIENCIA" else None
                if codigo in ("FORMACION", "TITULO_AREA", "PROMEDIO"):
                    discriminante = r.grupo_formacion if r.relacion_formacion == "misma_formacion" else r.pk if r.relacion_formacion == "independiente" else None
                key = (codigo, discriminante)
                if key in seen: errors.append(f"Unifica las condiciones {codigo} comunes y de la opción {opcion.pk} antes de publicar.")
                seen.add(key)
        beneficios = [b for b in obj.beneficios.all() if b.opcion_estudio_id in (None, opcion.pk)]
        conceptos = set()
        for b in beneficios:
            key = " ".join(b.concepto.casefold().split())
            if key in conceptos: errors.append(f"Resuelve el beneficio superpuesto '{b.concepto}' en la opción {opcion.pk}; registra el resultado por opción.")
            conceptos.add(key)
    return list(dict.fromkeys(errors))


TEXTO_CONFIRMACION = ("Al publicar confirmas que la beca es ofrecida o coofrecida por la entidad ecuatoriana indicada "
                      "y que la información coincide con las bases oficiales.")


TEXTO_CONFIRMACION_SIN_ENTIDAD = ("Publicar bajo mi responsabilidad: confirmo que la beca no corresponde a una entidad oferente "
                                  "ecuatoriana registrada y que la información coincide con las bases oficiales.")


@transaction.atomic
def publicar(obj, actor=None, confirmar_oferente=False):
    """Publica si se cumplen los controles. Con `actor` (el administrador que pulsa «Validar y publicar»)
    valida los requisitos activos pendientes y registra la confirmación en un Evento de auditoría.
    Sin entidad oferente ecuatoriana, la primera publicación exige `confirmar_oferente` («Publicar bajo mi responsabilidad»)."""
    era_publica = obj.activa and obj.revision == "validada" and (
        not obj.institucion_id or obj.institucion.pais.codigo == "EC")
    errors = errores_publicacion(obj)
    if errors: raise ValidationError({"detail": " ".join(errors)})
    aviso = aviso_oferente(obj)
    if aviso and not era_publica and not confirmar_oferente:
        raise ValidationError({"detail": f"{aviso}. Confirma «Publicar bajo mi responsabilidad» para continuar.",
                               "requiere_confirmacion_oferente": True})
    if actor is not None:
        pendientes = list(obj.requisitos.filter(activo=True, validado=False).values_list("pk", flat=True))
        if pendientes:
            m.Requisito.objects.filter(pk__in=pendientes).update(validado=True)
        origen = m.BorradorRastreo.objects.filter(convocatoria=obj).first()
        ahora = timezone.now()
        externo = oferente_sin_entidad(obj)
        cambios = {"entidad": {"id": obj.institucion_id, "nombre": obj.institucion.nombre, "pais": obj.institucion.pais.codigo} if obj.institucion_id else None,
                   "oferente_detectado": externo, "confirmacion_sin_entidad": bool(aviso),
                   "fecha": ahora.isoformat(), "texto_confirmacion": TEXTO_CONFIRMACION_SIN_ENTIDAD if aviso else TEXTO_CONFIRMACION,
                   "requisitos_validados": pendientes, "oferta_version": obj.version + 1,
                   "version_ficha_id": origen.version_id if origen else None}
        m.Evento.objects.create(actor=actor, accion="confirmar_publicacion", convocatoria=obj,
                                cambios=json.loads(json.dumps(cambios, cls=DjangoJSONEncoder)), creado_en=ahora)
    obj.revision = "validada"
    obj.activa = True
    obj.version += 1
    obj.actualizado_en = timezone.now()
    obj.save()
    if not era_publica:
        from notificaciones.services import avisar_publicacion
        avisar_publicacion(obj)


# --- Eliminación de entidades oferentes ---------------------------------------------------------------
# Una convocatoria está o estuvo en el catálogo público si hoy está validada (abierta, próxima, cierra hoy, sin fecha,
# cerrada o pausada tras publicarse) o si alguna vez se confirmó su publicación (editar el oferente o la oferta la devuelve
# a «pendiente», pero ya fue pública). El resto son borradores privados: pendientes de revisión o descartados.
def en_catalogo():
    return Q(revision="validada") | Exists(m.Evento.objects.filter(convocatoria=OuterRef("pk"), accion="confirmar_publicacion"))


def _conteo(publicas_):
    filas = (m.Convocatoria.objects.filter(institucion=OuterRef("pk")).filter(en_catalogo() if publicas_ else ~en_catalogo())
             .order_by().values("institucion").annotate(n=Count("id")).values("n"))
    return Coalesce(Subquery(filas, output_field=IntegerField()), Value(0))


def con_contadores(qs):
    """Anota convocatorias_publicas y borradores_privados por entidad, sin consultas N+1."""
    return qs.annotate(convocatorias_publicas=_conteo(True), borradores_privados=_conteo(False))


def muestra_publicas(obj, limite=5):
    """Hasta `limite` convocatorias de la entidad que están o estuvieron en el catálogo público (para explicar el bloqueo)."""
    return list(m.Convocatoria.objects.filter(institucion=obj).filter(en_catalogo()).order_by("titulo", "id").values("id", "titulo")[:limite])


class EntidadConConvocatoriasPublicas(Exception):
    def __init__(self, n, muestra=()):
        self.n = n
        self.muestra = list(muestra)
        plural = "convocatoria" if n == 1 else "convocatorias"
        super().__init__(f"No se puede eliminar: la entidad tiene {n} {plural} en el catálogo público. "
                         "Despublica o reasigna esas convocatorias antes.")


def eliminar_institucion(obj, actor):
    """Elimina la entidad; el llamador abre la transacción atómica y bloquea `obj` con select_for_update.

    - Con convocatorias en el catálogo público: se bloquea (EntidadConConvocatoriasPublicas).
    - Sus borradores privados no se borran: quedan sin entidad, vuelven a revisión pendiente y se marcan como
      «Oferente por confirmar»; publicarlos exige «Publicar bajo mi responsabilidad».
    - El historial de AUD_EVENTO de la entidad se conserva: pierde el vínculo y guarda `institucion_eliminada`.
    """
    convocatorias = list(m.Convocatoria.objects.select_for_update().filter(institucion=obj).order_by("id"))
    publicas_ = m.Convocatoria.objects.filter(pk__in=[c.pk for c in convocatorias]).filter(en_catalogo()).count()
    if publicas_:
        raise EntidadConConvocatoriasPublicas(publicas_, muestra_publicas(obj))
    entidad = {"id": obj.pk, "nombre": obj.nombre, "sector": obj.sector, "pais": obj.pais.codigo, "url_oficial": obj.url_oficial}
    for conv in convocatorias:
        antes = detalle(conv)
        conv.institucion = None
        conv.save(update_fields=["institucion"])
        touch(conv)
        cambios = {"origen": "manual", "antes": antes, "despues": detalle(conv), "entidad_eliminada": entidad}
        m.Evento.objects.create(actor=actor, accion=ACCION_OFERENTE_ELIMINADO, convocatoria=conv,
                                cambios=json.loads(json.dumps(cambios, cls=DjangoJSONEncoder)))
    historicos = list(m.Evento.objects.select_for_update().filter(institucion=obj))
    for evento in historicos:
        evento.cambios = {**(evento.cambios or {}), "institucion_eliminada": entidad}
        evento.institucion = None
        evento.save(update_fields=["cambios", "institucion"])
    resumen = {"borradores_desvinculados": len(convocatorias)}
    m.Evento.objects.create(actor=actor, accion="eliminar_institucion", convocatoria=None, institucion=None, cambios=json.loads(json.dumps(
        {"origen": "manual", "institucion_eliminada": entidad, **resumen, "convocatorias_desvinculadas": [c.pk for c in convocatorias],
         "eventos_historicos_conservados": len(historicos)}, cls=DjangoJSONEncoder)))
    obj.delete()
    return resumen
