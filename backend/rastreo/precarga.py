"""Precarga asistida de propuestas del rastreo en un borrador automático.

La acción la inicia un administrador. Crea opciones, beneficios y requisitos inactivos
y sin validar, solo para candidatos de confianza alta o media que superan los
serializers del catálogo. La procedencia y la confianza quedan en AUD_EVENTO a nombre
del administrador. Nunca modifica registros existentes ni recrea lo ya precargado.
"""
import hashlib
import json
import unicodedata
import uuid

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from convocatorias import serializers as catalogo_serializers
from convocatorias.models import Beneficio, BorradorRastreo, Convocatoria, Evento, OpcionEstudio, Requisito, TipoRequisito
from convocatorias.services import touch

ACCION_PRECARGA = 'precargar_propuestas'
ACCION_RESOLUCION = 'resolver_precarga'
MODELOS = {'opciones': OpcionEstudio, 'beneficios': Beneficio, 'requisitos': Requisito}
EXTERNOS = ('ACREDITACION', 'DOCUMENTO', 'OTRO')


def _normal(value):
    text = unicodedata.normalize('NFD', str(value or '').casefold())
    return ' '.join(''.join(c for c in text if unicodedata.category(c) != 'Mn').split())


def _huella(modelo, contenido):
    raw = json.dumps({'modelo': modelo, **contenido}, ensure_ascii=False, sort_keys=True, cls=DjangoJSONEncoder)
    return hashlib.sha256(raw.encode()).hexdigest()


def _actor(actor_id):
    actor = get_user_model().objects.filter(pk=actor_id).first()
    if not actor or not actor.is_active or actor.rol != 'administrador':
        raise PermissionDenied()
    return actor


def _origen(offer):
    origin = BorradorRastreo.objects.filter(convocatoria=offer).select_related('publicacion', 'version').first()
    if not origin:
        raise ValidationError('La convocatoria no procede de un borrador automático del rastreo.')
    return origin


def _version_evidencia(origin, offer):
    from .auto_borradores import latest_version, materially_changed, review_baseline, version_confirmed
    current = latest_version(origin.publicacion)
    if current and materially_changed(review_baseline(origin, offer), current) and not version_confirmed(offer, current):
        raise ValidationError('Hay una versión nueva de la fuente sin revisar. Confírmala antes de precargar propuestas.')
    return current or origin.version


def _candidatos(version):
    """Traduce los candidatos editables a registros del catálogo con su confianza."""
    from .auto_borradores import editable_candidates
    found = editable_candidates(version)
    tipos = {row.codigo: row for row in TipoRequisito.objects.all()}
    filas = []
    for item in found.get('requisitos', []):
        texto = (item.get('texto_original') or '').strip()
        codigo = item.get('tipo_sugerido')
        procedencia = {**(item.get('procedencia') or {}), 'metodo': item.get('metodo'), 'puntuacion': item.get('puntuacion')}
        base = {'modelo': 'requisitos', 'texto': texto, 'procedencia': procedencia,
                'huella': _huella('requisitos', {'texto': _normal(texto), 'tipo': codigo})}
        if item.get('negacion_literal') or item.get('estado') == 'ambigua' or not codigo or codigo == 'OTRO':
            filas.append({**base, 'omitido': 'Interpretación ambigua o con negación; queda para revisión manual.'})
            continue
        confianza = 'alta' if item.get('estado') == 'identificada' else 'media'
        tipo = tipos.get(codigo)
        if not tipo:
            filas.append({**base, 'omitido': f'Tipo de requisito {codigo} no registrado en el catálogo.'})
            continue
        datos = {'tipo_requisito': tipo.pk, 'texto_original': texto, 'valor_estructurado': item.get('valor_sugerido') or {},
                 'modo_comprobacion': 'entidad_oferente' if codigo in EXTERNOS else 'dato_declarado',
                 'obligatorio': True, 'validado': False, 'activo': False}
        filas.append({**base, 'confianza': confianza, 'datos': datos})
    for item in (found.get('otros_campos') or {}).get('beneficios', []):
        texto = (item.get('texto_original') or '').strip()
        concepto = (item.get('concepto_sugerido') or '').strip()
        base = {'modelo': 'beneficios', 'texto': texto, 'procedencia': item.get('procedencia') or {},
                'huella': _huella('beneficios', {'texto': _normal(texto), 'concepto': _normal(concepto)})}
        if item.get('estado') != 'identificada' or not concepto:
            filas.append({**base, 'omitido': 'Beneficio sin concepto o cuantía identificados con claridad.'})
            continue
        datos = {'concepto': concepto[:100], 'porcentaje': item.get('porcentaje'), 'monto': item.get('monto'),
                 'moneda': item.get('moneda'), 'tope_original': item.get('tope_original'),
                 'tope_monto': item.get('tope_monto'), 'tope_moneda': item.get('tope_moneda'), 'detalle': texto or None}
        filas.append({**base, 'confianza': 'alta', 'datos': datos})
    for item in found.get('opciones', []):
        texto = f"{item.get('nivel')} · {item.get('modalidad')} · {item.get('destino_original') or ''}".strip(' ·')
        procedencia = {**(item.get('procedencia') or {}), 'destino_original': item.get('destino_original')}
        base = {'modelo': 'opciones', 'texto': texto, 'procedencia': procedencia,
                'huella': _huella('opciones', {'nivel': item.get('nivel'), 'modalidad': item.get('modalidad'),
                                               'destino': _normal(item.get('destino_original'))})}
        # El destino literal no se convierte en países: queda en la procedencia para revisar.
        datos = {'nivel': item.get('nivel'), 'modalidad': item.get('modalidad'), 'activa': False, 'paises': []}
        filas.append({**base, 'confianza': 'media', 'datos': datos})
    return filas


def _eventos(offer):
    return list(Evento.objects.filter(convocatoria=offer, accion__in=(ACCION_PRECARGA, ACCION_RESOLUCION)).order_by('id'))


def _ya_existe(offer, fila):
    datos = fila['datos']
    if fila['modelo'] == 'requisitos':
        return any(_normal(row) == _normal(datos['texto_original'])
                   for row in offer.requisitos.values_list('texto_original', flat=True))
    if fila['modelo'] == 'beneficios':
        return any(_normal(c) == _normal(datos['concepto']) and (_normal(d) == _normal(datos['detalle']) or not datos['detalle'])
                   for c, d in offer.beneficios.values_list('concepto', 'detalle'))
    return offer.opciones.filter(nivel=datos['nivel'], modalidad=datos['modalidad']).exists()


def estado(offer):
    """Registros precargados con su estado: pendiente, aceptado o descartado."""
    rows, decisions = [], {}
    for event in _eventos(offer):
        if event.accion == ACCION_PRECARGA:
            rows.extend(event.cambios.get('creados', []))
        else:
            decisions[(event.cambios['modelo'], event.cambios['id'])] = event.cambios['decision']
    result = []
    for row in rows:
        model = MODELOS[row['modelo']]
        record = model.objects.filter(pk=row['id'], convocatoria=offer).first()
        decision = decisions.get((row['modelo'], row['id']))
        if decision:
            state = 'aceptado' if decision == 'aceptar' else 'descartado'
        elif record is None:
            state = 'descartado'
        elif row['modelo'] == 'requisitos' and record.activo and record.validado:
            state = 'aceptado'
        elif row['modelo'] == 'opciones' and record.activa:
            state = 'aceptado'
        else:
            state = 'pendiente'
        result.append({**row, 'estado': state, 'existe': record is not None})
    return result


def pendientes(offer):
    return [row for row in estado(offer) if row['estado'] == 'pendiente']


def bloqueo_publicacion(offer):
    count = len(pendientes(offer))
    if not count:
        return None
    return (f'Revisa {count} {"propuesta precargada" if count == 1 else "propuestas precargadas"} '
            '(acepta o descarta cada una) antes de publicar.')


@transaction.atomic
def precargar(offer_id, actor_id, offer_version, key):
    actor = _actor(actor_id)
    try:
        key = str(uuid.UUID(str(key)))
    except ValueError:
        raise ValidationError({'clave_accion': 'Clave de acción inválida.'}) from None
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 742620))', [key])
    previous = Evento.objects.filter(accion=ACCION_PRECARGA, cambios__clave_accion=key).first()
    if previous:
        if previous.convocatoria_id != offer_id or previous.actor_id != actor.pk:
            raise ValidationError('La clave ya corresponde a otra precarga.')
        return previous.cambios, False
    offer = Convocatoria.objects.select_for_update().get(pk=offer_id)
    origin = _origen(offer)
    if offer.version != offer_version:
        raise ValidationError('El borrador cambió; recarga el editor antes de precargar.')
    if offer.revision != 'pendiente':
        raise ValidationError('Solo se precarga en un borrador pendiente de revisión, nunca en una convocatoria publicada.')
    version = _version_evidencia(origin, offer)
    previas = {row['huella'] for event in _eventos(offer) if event.accion == ACCION_PRECARGA
               for row in event.cambios.get('creados', []) + event.cambios.get('omitidos', [])}
    creados, omitidos = [], []
    for fila in _candidatos(version):
        resumen = {'modelo': fila['modelo'], 'huella': fila['huella'], 'texto': fila['texto'][:500],
                   'procedencia': fila['procedencia']}
        if fila['huella'] in previas:
            continue
        previas.add(fila['huella'])
        if 'omitido' in fila:
            omitidos.append({**resumen, 'motivo': fila['omitido']})
            continue
        if _ya_existe(offer, fila):
            omitidos.append({**resumen, 'motivo': 'El borrador ya contiene un registro equivalente; se conserva sin cambios.'})
            continue
        serializer_type = {'opciones': catalogo_serializers.OpcionSerializer,
                           'beneficios': catalogo_serializers.BeneficioSerializer,
                           'requisitos': catalogo_serializers.RequisitoSerializer}[fila['modelo']]
        serializer = serializer_type(data=fila['datos'], context={'convocatoria': offer})
        if not serializer.is_valid():
            omitidos.append({**resumen, 'motivo': 'Valores incompletos para el contrato del catálogo; requiere captura manual.'})
            continue
        record = serializer.save(convocatoria=offer)
        creados.append({**resumen, 'id': record.pk, 'confianza': fila['confianza']})
    changes = {'clave_accion': key, 'version_fuente_id': version.pk, 'publicacion_id': origin.publicacion_id,
               'creados': creados, 'omitidos': omitidos}
    if creados:
        touch(offer)
    changes = json.loads(json.dumps(changes, cls=DjangoJSONEncoder))
    Evento.objects.create(actor=actor, convocatoria=offer, accion=ACCION_PRECARGA, cambios=changes)
    return changes, True


class _Resolucion(serializers.Serializer):
    modelo = serializers.ChoiceField(choices=sorted(MODELOS))
    id = serializers.IntegerField(min_value=1)
    decision = serializers.ChoiceField(choices=['aceptar', 'descartar'])
    version_convocatoria = serializers.IntegerField(min_value=1)


@transaction.atomic
def resolver(offer_id, actor_id, payload):
    actor = _actor(actor_id)
    data = _Resolucion(data=payload)
    data.is_valid(raise_exception=True)
    data = data.validated_data
    offer = Convocatoria.objects.select_for_update().get(pk=offer_id)
    _origen(offer)
    row = next((item for item in estado(offer) if item['modelo'] == data['modelo'] and item['id'] == data['id']), None)
    if not row:
        raise ValidationError('El registro no procede de una precarga de este borrador.')
    if row['estado'] != 'pendiente':
        expected = 'aceptado' if data['decision'] == 'aceptar' else 'descartado'
        if row['estado'] == expected:
            return row, False
        raise ValidationError('El registro ya tiene otra decisión registrada.')
    if offer.version != data['version_convocatoria']:
        raise ValidationError('El borrador cambió; recarga el editor antes de decidir.')
    model = MODELOS[data['modelo']]
    record = model.objects.select_for_update().get(pk=data['id'], convocatoria=offer)
    if data['decision'] == 'aceptar':
        if data['modelo'] == 'requisitos':
            # Aceptar equivale a revisar la transcripción; el contenido se conserva tal cual.
            serializer = catalogo_serializers.RequisitoSerializer(record, data={'activo': True, 'validado': True},
                                                                  partial=True, context={'convocatoria': offer})
            serializer.is_valid(raise_exception=True)
            serializer.save()
        elif data['modelo'] == 'opciones':
            record.activa = True
            record.save(update_fields=['activa'])
    elif data['modelo'] == 'beneficios':
        record.delete()
    touch(offer)
    Evento.objects.create(actor=actor, convocatoria=offer, accion=ACCION_RESOLUCION,
                          cambios={'modelo': data['modelo'], 'id': data['id'], 'decision': data['decision'],
                                   'huella': row['huella']})
    return {**row, 'estado': 'aceptado' if data['decision'] == 'aceptar' else 'descartado'}, True
