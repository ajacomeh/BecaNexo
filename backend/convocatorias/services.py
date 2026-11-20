import json
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError
from . import models as m, serializers as s


def publicas():
    return m.Convocatoria.objects.filter(activa=True, revision="validada",
        institucion__pais__codigo="EC").select_related("institucion", "tipo_beca")


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
    if not publico:
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
    if not obj.institucion_id:
        errors.append("Asigna una institución oferente ecuatoriana antes de publicar.")
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
                if codigo in ("ACREDITACION", "DOCUMENTO", "OTRO"): continue
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


@transaction.atomic
def publicar(obj, actor=None):
    """Publica si se cumplen los controles. Con `actor` (el administrador que pulsa «Validar y publicar»)
    valida los requisitos activos pendientes y registra la confirmación en un Evento de auditoría."""
    era_publica = obj.activa and obj.revision == "validada" and (
        bool(obj.institucion_id) and obj.institucion.pais.codigo == "EC")
    errors = errores_publicacion(obj)
    if errors: raise ValidationError({"detail": " ".join(errors)})
    if actor is not None:
        pendientes = list(obj.requisitos.filter(activo=True, validado=False).values_list("pk", flat=True))
        if pendientes:
            m.Requisito.objects.filter(pk__in=pendientes).update(validado=True)
        origen = m.BorradorRastreo.objects.filter(convocatoria=obj).first()
        ahora = timezone.now()
        cambios = {"entidad": {"id": obj.institucion_id, "nombre": obj.institucion.nombre, "pais": obj.institucion.pais.codigo},
                   "fecha": ahora.isoformat(), "texto_confirmacion": TEXTO_CONFIRMACION,
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
