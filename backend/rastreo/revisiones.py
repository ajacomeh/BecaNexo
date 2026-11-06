"""Decisiones humanas sobre evidencia exacta; no integración con catálogo."""
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied
from .models import Revision, Version, VersionDocumento


class ConflictoRevision(APIException):
    status_code = 409
    default_detail = 'La revisión cambió. Consulta el historial antes de confirmar de nuevo.'


class RevisionEntrada(serializers.Serializer):
    dimension = serializers.ChoiceField(choices=['extraccion', 'documental', 'oferente'])
    decision = serializers.ChoiceField(choices=['pendiente', 'aprobada', 'rechazada'])
    motivo = serializers.CharField(max_length=5000, trim_whitespace=True)
    evidencia_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807, allow_null=True)
    sustituye_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807, allow_null=True)
    clave_accion = serializers.UUIDField()
    tipo_oferente = serializers.ChoiceField(choices=['entidad_ecuatoriana', 'convenio', 'no_determinado'], required=False)
    referencia = serializers.CharField(max_length=2000, required=False, trim_whitespace=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({'non_field_errors': ['Solo se admiten los campos del formulario de revisión.']})
        # DRF acepta números como CharField; la justificación debe ser texto real.
        for field in ('motivo', 'referencia'):
            if field in data and not isinstance(data[field], str):
                raise serializers.ValidationError({field: 'Debe ser texto.'})
        return super().to_internal_value(data)

    def validate(self, data):
        dimension = data['dimension']
        if (dimension in ['documental', 'oferente']) != (data['evidencia_id'] is not None):
            raise serializers.ValidationError({'evidencia_id': 'Seleccione evidencia exacta para documentación u oferente; extracción revisa la versión completa.'})
        if dimension == 'oferente':
            if not data.get('tipo_oferente') or not data.get('referencia'):
                raise serializers.ValidationError('Indique tipo de oferente y referencia concreta dentro de la evidencia.')
            if data['decision'] == 'aprobada' and data['tipo_oferente'] != 'entidad_ecuatoriana':
                raise serializers.ValidationError('Solo puede aprobarse una entidad ecuatoriana con evidencia. La representación de convenios sigue pendiente.')
        elif 'tipo_oferente' in data or 'referencia' in data:
            raise serializers.ValidationError('Tipo y referencia de oferente solo corresponden a esa dimensión.')
        return data


def vigentes(version_id):
    replaced = Revision.objects.filter(version_id=version_id, sustituye__isnull=False).values('sustituye_id')
    return Revision.objects.filter(version_id=version_id, dimension__in=['extraccion', 'documental', 'oferente']).exclude(pk__in=replaced)


@transaction.atomic
def registrar(actor_id, version_id, data):
    actor = get_user_model().objects.select_for_update().get(pk=actor_id)
    if not actor.is_active or actor.rol != 'administrador':
        raise PermissionDenied()
    # Serializa reintentos con la misma clave, incluso sobre versiones distintas.
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 742609))', [str(data['clave_accion'])])
    version = Version.objects.select_for_update().get(pk=version_id)
    detail = {k: data[k] for k in ('tipo_oferente', 'referencia') if k in data}
    expected = dict(actor_id=actor.pk, version_id=version.pk, evidencia_id=data['evidencia_id'],
                    dimension=data['dimension'], decision=data['decision'], motivo=data['motivo'],
                    sustituye_id=data['sustituye_id'], detalle=detail)
    old = Revision.objects.filter(clave_accion=data['clave_accion']).first()
    if old:
        if any(getattr(old, key) != value for key, value in expected.items()):
            raise ConflictoRevision('La clave de acción ya corresponde a otro contenido. Consulta el historial.')
        return old, False
    if data['evidencia_id'] is not None and not VersionDocumento.objects.filter(pk=data['evidencia_id'], version=version).exists():
        raise serializers.ValidationError({'evidencia_id': 'La evidencia no pertenece a esta versión.'})
    current = vigentes(version.pk).filter(dimension=data['dimension'])
    if data['dimension'] == 'documental':
        current = current.filter(evidencia_id=data['evidencia_id'])
    previous = current.first()
    if data['sustituye_id'] != (previous.pk if previous else None):
        raise ConflictoRevision()
    if previous and previous.evidencia_id != data['evidencia_id']:
        raise serializers.ValidationError('La rectificación debe conservar la evidencia exacta de la revisión anterior.')
    return Revision.objects.create(**expected, clave_accion=data['clave_accion']), True


def revision_data(row):
    return {**{field: getattr(row, field) for field in ('id', 'version_id', 'evidencia_id', 'creada_en', 'dimension', 'decision', 'motivo', 'sustituye_id', 'detalle')},
            'administrador': {'id': row.actor_id, 'nombre': row.actor.nombre}}
