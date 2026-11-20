"""Aplicación explícita de campos de una propuesta al borrador ya vinculado."""
import json
from datetime import datetime
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from convocatorias.models import BorradorRastreo, Convocatoria, Evento
from convocatorias.serializers import ConvocatoriaSerializer
from convocatorias.services import detalle, touch
from .models import Propuesta, Publicacion
from .propuestas import latest

ALLOWED_FIELDS = frozenset({'titulo', 'descripcion', 'institucion', 'url_oficial',
                            'cierre_dia', 'cierre_original', 'tipo_beca', 'cobertura_tipo',
                            'gastos_no_cubiertos', 'url_bases', 'apertura'})
RELATED_FIELDS = frozenset({'institucion', 'tipo_beca'})


def _current(offer, field):
    return getattr(offer, f'{field}_id' if field in RELATED_FIELDS else field)


def _comparable(field, value):
    # La propuesta guarda el instante como texto ISO; se compara como instante.
    return datetime.fromisoformat(value) if field == 'apertura' and isinstance(value, str) else value


@transaction.atomic
def apply_proposal(proposal_id, actor_id, offer_version, proposal_hash, selected, reason):
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ValidationError({'motivo': 'Explica los campos confirmados (máximo 1000 caracteres).'})
    if not isinstance(selected, list) or not selected or len(selected) != len(set(selected)) or not set(selected) <= ALLOWED_FIELDS:
        raise ValidationError({'campos': 'Selecciona campos generales admitidos, sin repetirlos.'})
    actor = get_user_model().objects.get(pk=actor_id)
    if not actor.is_active or actor.rol != 'administrador':
        raise PermissionDenied()
    proposal = Propuesta.objects.select_related('version', 'publicacion').get(pk=proposal_id)
    publication = Publicacion.objects.select_for_update().get(pk=proposal.publicacion_id)
    origin = BorradorRastreo.objects.filter(publicacion=publication).first()
    if not origin or publication.convocatoria_id != origin.convocatoria_id:
        raise ValidationError('No existe borrador automático vinculado para esta propuesta.')
    offer = Convocatoria.objects.select_for_update().get(pk=origin.convocatoria_id)
    if offer.version != offer_version or offer.revision != 'pendiente' or proposal.hash_propuesta != proposal_hash:
        raise ValidationError('El borrador o la propuesta cambiaron; revisa antes de aplicar.')
    head = Propuesta.objects.filter(publicacion=publication, sucesora__isnull=True).first()
    observed = latest(publication.pk)
    if not head or head.pk != proposal.pk or not observed or observed.pk != proposal.observacion_base_id:
        raise ValidationError('La propuesta no corresponde al contexto vigente.')
    valid_evidence = set(proposal.version.documentos.values_list('pk', flat=True))
    values = {}
    for field in selected:
        value = proposal.datos.get(field)
        if value is None or value == '':
            raise ValidationError({field: 'La propuesta no contiene un valor confirmado para este campo.'})
        if not any(ref.get('campo') == field and ref.get('evidencia_id') in valid_evidence
                   and str(ref.get('motivo', '')).strip() for ref in proposal.procedencia):
            raise ValidationError({field: 'Falta una referencia exacta y justificada de esta versión.'})
        values[field] = value
    if not any(_current(offer, field) != _comparable(field, value) for field, value in values.items()):
        raise ValidationError('Los campos seleccionados ya coinciden con el borrador.')
    before = {field: _current(offer, field) for field in selected}
    # El serializer del catálogo valida cada campo: tipo existente, cobertura admitida,
    # URL segura y apertura no posterior al cierre registrado.
    serializer = ConvocatoriaSerializer(offer, data=values, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    touch(offer)
    after = {field: _current(offer, field) for field in selected}
    changes = json.loads(json.dumps({'propuesta_id': proposal.pk, 'version_fuente_id': proposal.version_id,
                                     'motivo': reason.strip(), 'antes': before, 'despues': after}, cls=DjangoJSONEncoder))
    Evento.objects.create(actor=actor, convocatoria=offer, accion='aplicar_propuesta_borrador',
                          cambios=changes)
    return detalle(offer)
