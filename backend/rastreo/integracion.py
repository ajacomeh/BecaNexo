"""Creación humana y atómica de un borrador desde evidencia revisada."""
import re
from decimal import Decimal, InvalidOperation
import ipaddress
from urllib.parse import urlsplit
from django.contrib.auth import get_user_model
from django.db import connection, transaction, IntegrityError
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from convocatorias import models as catalogo
from convocatorias import serializers as catalogo_serializers
from convocatorias.services import audit, detalle
from perfiles.models import Pais
from .models import Propuesta, Publicacion, Revision
from .propuestas import Cerrado, digest, evaluar
from .revisiones import ConflictoRevision, vigentes


MATERIALES = {'PRECISION_TEMPORAL', 'TOPE_FUENTE', 'TOPE_NO_REPRESENTADO',
              'AMBITO_DESCONOCIDO', 'AMBITO_INCOMPLETO', 'CANDIDATO_PENDIENTE',
              'SIN_OPCIONES', 'DESCRIPCION_PENDIENTE'}
NO_REPRESENTABLES = {'PRECISION_TEMPORAL', 'TOPE_FUENTE', 'TOPE_NO_REPRESENTADO'}


class Elegido(Cerrado):
    id = serializers.CharField(max_length=60)
    datos = serializers.DictField()
    motivo = serializers.CharField(max_length=2000)


class CrearEntrada(Cerrado):
    clave_accion = serializers.UUIDField()
    hash_propuesta = serializers.CharField(max_length=64)
    observacion_base_id = serializers.IntegerField(min_value=1)
    revisiones = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=200)
    motivo_institucion = serializers.CharField(max_length=2000)
    motivo_bases_ausentes = serializers.CharField(max_length=2000, required=False)
    confirmados = serializers.ListField(child=serializers.CharField(max_length=60), max_length=200)
    opciones = Elegido(many=True, required=False, max_length=50)
    beneficios = Elegido(many=True, required=False, max_length=50)
    requisitos = Elegido(many=True, required=False, max_length=100)

    def validate_revisiones(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError('No repitas revisiones.')
        return values


class ResolverEntrada(Cerrado):
    clave_accion = serializers.UUIDField()
    pendiente_id = serializers.CharField(max_length=160)
    evidencia_id = serializers.IntegerField(min_value=1)
    motivo = serializers.CharField(max_length=5000)
    version_convocatoria = serializers.IntegerField(min_value=1)
    hash_convocatoria = serializers.CharField(max_length=64)


def _candidatos(propuesta):
    return {tipo: {x['id']: x for x in propuesta.datos.get(tipo, [])}
            for tipo in ('opciones', 'beneficios', 'requisitos')}


def _validar_seleccion(propuesta, data):
    candidates = _candidatos(propuesta)
    all_ids = {x for group in candidates.values() for x in group}
    selected = {kind: {row['id']: row['datos'] for row in data.get(kind, [])}
                for kind in candidates}
    if len(all_ids) != sum(len(g) for g in candidates.values()):
        raise serializers.ValidationError('La propuesta contiene identificadores repetidos.')
    if len(data['confirmados']) != len(set(data['confirmados'])) or set(data['confirmados']) != all_ids:
        raise serializers.ValidationError({'confirmados': 'Confirma todos los candidatos, incluidos los que permanecerán pendientes.'})
    for kind in candidates:
        if len(selected[kind]) != len(data.get(kind, [])) or set(selected[kind]) - set(candidates[kind]):
            raise serializers.ValidationError({kind: 'Selección duplicada o ajena a la propuesta.'})
    return candidates, selected


def _mapeo(kind, candidate, values, option_rows, offer):
    """Los campos elegidos deben estar respaldados por el candidato, y pasan por el serializer vigente."""
    if not isinstance(values, dict):
        raise serializers.ValidationError({kind: 'Se requieren datos tipados.'})
    values = dict(values)
    if kind == 'opciones':
        expected = {'nivel': candidate.get('nivel'), 'modalidad': candidate.get('modalidad'),
                    'programa': candidate.get('texto') or None}
        for field, value in expected.items():
            if values.get(field) != value:
                raise serializers.ValidationError({kind: f'{field} debe corresponder a la propuesta; guarda una sucesora para cambiarlo.'})
        actual = set(Pais.objects.filter(pk__in=values.get('paises', [])).values_list('codigo', flat=True))
        if actual != set(candidate.get('paises', [])) or len(values.get('paises', [])) != len(actual):
            raise serializers.ValidationError({kind: 'Los países deben corresponder exactamente a los seleccionados en la propuesta.'})
        cls = catalogo_serializers.OpcionSerializer
    elif kind == 'beneficios':
        if not candidate.get('concepto') or values.get('concepto') != candidate['concepto']:
            raise serializers.ValidationError({kind: 'El concepto debe proceder de la propuesta.'})
        if candidate.get('tope'):
            raise serializers.ValidationError({kind: 'Un tope no puede convertirse en importe fijo. Deja este candidato pendiente.'})
        for literal, field in (('porcentaje', 'porcentaje'), ('monto', 'monto')):
            source = (candidate.get(literal) or '').strip()
            if source:
                cleaned = re.fullmatch(r'([0-9]+(?:[.,][0-9]{1,2})?)\s*%?' if literal == 'porcentaje' else r'([0-9]+(?:[.,][0-9]{1,2})?)', source)
                if not cleaned:
                    raise serializers.ValidationError({kind: f'{literal} literal ambiguo; conserva el candidato pendiente.'})
                try:
                    if Decimal(str(values.get(field))) != Decimal(cleaned.group(1).replace(',', '.')):
                        raise serializers.ValidationError({kind: f'{literal} no corresponde al literal.'})
                except (InvalidOperation, TypeError):
                    raise serializers.ValidationError({kind: f'{literal} debe ser un número válido.'})
            elif values.get(field) is not None:
                raise serializers.ValidationError({kind: f'{literal} no figura en el candidato.'})
        if values.get('moneda') != (candidate.get('moneda') or None):
            raise serializers.ValidationError({kind: 'La moneda debe constar explícitamente en la propuesta.'})
        if values.get('periodicidad'):
            raise serializers.ValidationError({kind: 'La periodicidad no consta en el candidato; déjala pendiente.'})
        for fragment in (candidate.get('texto'), candidate.get('condiciones')):
            if fragment and fragment not in (values.get('detalle') or ''):
                raise serializers.ValidationError({kind: 'Conserva descripción y condiciones originales en el detalle.'})
        cls = catalogo_serializers.BeneficioSerializer
    else:
        if not candidate.get('texto') or values.get('texto_original') != candidate['texto']:
            raise serializers.ValidationError({kind: 'El texto original debe conservarse íntegro.'})
        tipo = catalogo.TipoRequisito.objects.filter(pk=values.get('tipo_requisito')).first()
        if not tipo or tipo.codigo != candidate.get('tipo'):
            raise serializers.ValidationError({kind: 'El tipo debe corresponder a la transcripción revisada.'})
        if values.get('validado') is True:
            raise serializers.ValidationError({kind: 'La integración nunca valida automáticamente requisitos.'})
        if candidate.get('condiciones') and candidate['condiciones'] not in (values.get('detalle_acreditacion') or '') + (values.get('documento_exigido') or '') + values.get('texto_original', '') + str(values.get('valor_estructurado') or ''):
            raise serializers.ValidationError({kind: 'Conserva las condiciones documentadas del candidato.'})
        cls = catalogo_serializers.RequisitoSerializer
    scope = candidate.get('ambito', 'pendiente')
    if kind != 'opciones':
        if scope == 'pendiente':
            raise serializers.ValidationError({kind: 'El ámbito está pendiente; no se presume común.'})
        local = candidate.get('opcion')
        resolved = option_rows.get(local)
        if values.get('opcion_estudio') == local and resolved:
            values['opcion_estudio'] = resolved.pk
        if values.get('destino') == candidate.get('destino') and candidate.get('destino'):
            country_id = Pais.objects.filter(codigo=candidate['destino']).values_list('pk', flat=True).first()
            values['destino'] = country_id
        expected_id = resolved.pk if resolved else None
        if scope == 'comun' and (values.get('opcion_estudio') or values.get('destino')):
            raise serializers.ValidationError({kind: 'El ámbito común no admite opción ni destino.'})
        if scope in ('opcion', 'destino') and (not resolved or values.get('opcion_estudio') != expected_id):
            raise serializers.ValidationError({kind: 'Primero selecciona y crea la opción de esta propuesta.'})
        if scope == 'opcion' and values.get('destino'):
            raise serializers.ValidationError({kind: 'El destino no corresponde al ámbito de opción.'})
        if scope == 'destino':
            country = Pais.objects.filter(pk=values.get('destino')).first()
            if not country or country.codigo != candidate.get('destino') or not resolved.paises.filter(pk=country.pk).exists():
                raise serializers.ValidationError({kind: 'El destino debe pertenecer a la opción seleccionada.'})
    serializer = cls(data=values, context={'convocatoria': offer})
    serializer.is_valid(raise_exception=True)
    return serializer


def _estado(propuesta, ignore_convocatoria_id=None):
    reviews = list(propuesta.revisiones.values_list('revision_id', flat=True))
    return evaluar(propuesta.version, propuesta.observacion_base_id, propuesta.datos, propuesta.procedencia, reviews, ignore_convocatoria_id)


@transaction.atomic
def crear_borrador(actor_id, proposal_id, payload):
    serial = CrearEntrada(data=payload)
    serial.is_valid(raise_exception=True)
    data = serial.validated_data
    key = str(data['clave_accion'])
    action_hash = digest({k: v for k, v in data.items() if k != 'clave_accion'})
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        # Seguridad del servicio: el ejecutor de pruebas comprueba su propia BD antes de escribir.
        cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 742611))', [key])
    actor = get_user_model().objects.select_for_update().get(pk=actor_id)
    if not actor.is_active or actor.rol != 'administrador':
        raise PermissionDenied()
    existing = Revision.objects.filter(clave_accion=key, dimension='integracion', decision='aplicada').first()
    if existing:
        if existing.propuesta_id != proposal_id or existing.actor_id != actor_id or existing.detalle.get('hash_confirmacion') != action_hash:
            raise ConflictoRevision('La clave ya corresponde a otra confirmación.')
        return existing, False
    proposal = Propuesta.objects.select_related('version').get(pk=proposal_id)
    pub = Publicacion.objects.select_for_update().get(pk=proposal.publicacion_id)
    if pub.convocatoria_id or Propuesta.objects.filter(sustituye=proposal).exists():
        raise ConflictoRevision('La publicación ya está vinculada o la propuesta fue sustituida.')
    if proposal.hash_propuesta != data['hash_propuesta'] or proposal.observacion_base_id != data['observacion_base_id']:
        raise ConflictoRevision('El snapshot o la observación ya no coincide con la confirmación.')
    if set(proposal.revisiones.values_list('revision_id', flat=True)) != set(data['revisiones']):
        raise ConflictoRevision('Las revisiones confirmadas ya no corresponden al snapshot.')
    result = _estado(proposal)
    if any(x['codigo'] in ('CONTEXTO_OBSOLETO', 'REVISION_CAMBIADA') for x in result['bloqueos']):
        raise ConflictoRevision('Cambió la observación o una revisión. Conserva tu propuesta y actualiza el contexto.')
    if result['bloqueos']:
        raise serializers.ValidationError({'bloqueos': result['bloqueos']})
    institution = catalogo.Institucion.objects.select_for_update().select_related('pais').filter(pk=proposal.datos['institucion']).first()
    if not institution:
        raise serializers.ValidationError({'institucion': 'La entidad seleccionada ya no existe.'})
    if institution.pais.codigo != 'EC':
        raise serializers.ValidationError('La entidad oferente debe ser ecuatoriana.')
    source_review = next((r for r in vigentes(proposal.version_id) if r.dimension == 'oferente' and r.decision == 'aprobada'), None)
    if not source_review or source_review.detalle.get('tipo_oferente') != 'entidad_ecuatoriana':
        raise serializers.ValidationError('Falta revisión vigente del oferente ecuatoriano exacto.')
    if not data['motivo_institucion'].strip() or not any(x['campo'] == 'institucion' and x['evidencia_id'] == source_review.evidencia_id for x in proposal.procedencia):
        raise serializers.ValidationError({'motivo_institucion': 'Justifica la correspondencia con la evidencia exacta de oferente.'})
    host = (urlsplit(proposal.datos['url_oficial']).hostname or '').lower().rstrip('.')
    try:
        ip = ipaddress.ip_address(host)
        public_host = ip.is_global
    except ValueError:
        public_host = '.' in host and not host.endswith(('.local', '.internal', '.localhost', '.test'))
    if not public_host:
        raise serializers.ValidationError({'url_oficial': 'El enlace oficial debe apuntar a un sitio público; confirma el destino en la evidencia.'})
    candidates, selected = _validar_seleccion(proposal, data)
    for kind in candidates:
        for item in data.get(kind, []):
            if not item['motivo'].strip() or not any(ref['campo'] == f"{kind}.{item['id']}" for ref in proposal.procedencia):
                raise serializers.ValidationError({kind: 'Cada elemento seleccionado requiere motivo y evidencia exacta en la propuesta.'})
    omitted = [f'{kind}.{item}' for kind, rows in candidates.items() for item in rows if item not in selected[kind]]
    if proposal.version.manifiesto.get('pendientes'):
        raise serializers.ValidationError('La versión registra documentos aún no disponibles.')
    if not proposal.version.documentos.filter(rol='bases_pdf').exists() and not data.get('motivo_bases_ausentes', '').strip():
        raise serializers.ValidationError({'motivo_bases_ausentes': 'Documenta la ausencia real de bases identificadas.'})
    # El serializer canónico vuelve a calcular identidad y validaciones; nunca se confía en una clave del cliente.
    base = catalogo_serializers.ConvocatoriaSerializer(data={k: proposal.datos[k] for k in ('institucion', 'titulo', 'descripcion', 'url_oficial', 'cierre_original') if k in proposal.datos})
    base.is_valid(raise_exception=True)
    title = proposal.datos['titulo']
    if catalogo.Convocatoria.objects.filter(institucion=institution, titulo__iexact=title).exists():
        raise ConflictoRevision('Existe una convocatoria de la misma entidad y título; revisa el posible duplicado.')
    if catalogo.Convocatoria.objects.filter(url_oficial=proposal.datos['url_oficial']).exists():
        raise ConflictoRevision('El enlace oficial ya pertenece a otra convocatoria.')
    try:
        offer = base.save(revision='pendiente', activa=False)
    except IntegrityError as exc:
        if getattr(exc.__cause__, 'sqlstate', None) == '23505':
            raise ConflictoRevision('Posible duplicado concurrente de catálogo.') from exc
        raise
    option_rows = {}
    for item in data.get('opciones', []):
        candidate = candidates['opciones'][item['id']]
        serializer = _mapeo('opciones', candidate, item['datos'], option_rows, offer)
        option_rows[item['id']] = serializer.save(convocatoria=offer)
    for kind in ('beneficios', 'requisitos'):
        for item in data.get(kind, []):
            candidate = candidates[kind][item['id']]
            serializer = _mapeo(kind, candidate, item['datos'], option_rows, offer)
            serializer.save(convocatoria=offer, **({'validado': False} if kind == 'requisitos' else {}))
    # La confirmación conserva los candidatos omitidos y todos los pendientes originales; no desaparecen al crear.
    pending = [x for x in result['pendientes_publicacion'] if not (
        x['codigo'] == 'CANDIDATO_PENDIENTE' and x['campo'].split('.', 1)[0] in selected
        and x['campo'].split('.', 1)[1] in selected[x['campo'].split('.', 1)[0]])]
    detail = {'hash_confirmacion': action_hash, 'hash_propuesta': proposal.hash_propuesta,
              'observacion_base_id': proposal.observacion_base_id,
              'revisiones': sorted(data['revisiones']), 'pendientes': pending,
              'omitidos': omitted, 'seleccionados': {k: [{'id': row['id'], 'motivo': row['motivo']} for row in data.get(k, [])] for k in selected},
              'motivo_institucion': data['motivo_institucion'],
              'motivo_bases_ausentes': data.get('motivo_bases_ausentes', ''),
              'version_convocatoria': offer.version}
    applied = Revision.objects.create(actor=actor, version=proposal.version, propuesta=proposal,
        convocatoria=offer, dimension='integracion', decision='aplicada', motivo='Creación confirmada de borrador',
        detalle=detail, clave_accion=key)
    pub.convocatoria = offer
    pub.save(update_fields=['convocatoria'])
    audit(actor, 'rastreo_borrador_crear', None, {'convocatoria': detalle(offer),
        'procedencia': {'publicacion_id': pub.pk, 'version_id': proposal.version_id,
                       'observacion_id': proposal.observacion_base_id, 'propuesta_id': proposal.pk,
                       'revision_integracion_id': applied.pk}}, convocatoria=offer)
    return applied, True


def representar_aplicacion(row):
    return {'convocatoria_id': row.convocatoria_id, 'propuesta_id': row.propuesta_id,
            'revision_integracion_id': row.pk, 'revision': row.convocatoria.revision,
            'publica': row.convocatoria.activa and row.convocatoria.revision == 'validada' and row.convocatoria.institucion.pais.codigo == 'EC',
            'pendientes': row.detalle.get('pendientes', []),
            'omitidos': row.detalle.get('omitidos', [])}


def _aplicacion(offer):
    return Revision.objects.filter(convocatoria=offer, dimension='integracion', decision='aplicada').select_related('propuesta__version').first()


def estado_publicacion_integrada(offer):
    """Devuelve bloqueos actuales; las convocatorias manuales conservan su contrato."""
    applied = _aplicacion(offer)
    if not applied:
        return None
    proposal = applied.propuesta
    result = _estado(proposal, offer.pk)
    blockers = list(result['bloqueos'])
    if blockers:
        return {'aplicacion_id': applied.pk, 'bloqueos': blockers, 'pendientes': applied.detalle['pendientes']}
    current_hash = digest(detalle(offer))
    replaced = Revision.objects.filter(aplicacion=applied, sustituye__isnull=False).values('sustituye_id')
    resolutions = Revision.objects.filter(aplicacion=applied, dimension='integracion', decision='resuelta').exclude(pk__in=replaced)
    resolved = {r.detalle.get('pendiente_id') for r in resolutions if r.detalle.get('hash_convocatoria') == current_hash and r.detalle.get('version_convocatoria') == offer.version}
    pending = [x for x in applied.detalle['pendientes'] if x['codigo'] in MATERIALES and x['id'] not in resolved]
    return {'aplicacion_id': applied.pk, 'bloqueos': [], 'pendientes': pending}


def _comprobacion_pendiente(item, offer, proposal):
    code, field = item['codigo'], item['campo']
    if code in NO_REPRESENTABLES:
        raise serializers.ValidationError({'pendiente_id': 'El modelo aún no representa fielmente este dato; permanece bloqueado.'})
    if code == 'DESCRIPCION_PENDIENTE':
        return bool(offer.descripcion.strip())
    if code == 'SIN_OPCIONES':
        return offer.opciones.exists()
    if code in ('CANDIDATO_PENDIENTE', 'AMBITO_DESCONOCIDO', 'AMBITO_INCOMPLETO'):
        kind, candidate_id = field.split('.', 1)
        candidate = _candidatos(proposal).get(kind, {}).get(candidate_id)
        if not candidate:
            return False
        if kind == 'opciones':
            rows = offer.opciones.filter(programa=candidate.get('texto'), nivel=candidate.get('nivel'), modalidad=candidate.get('modalidad'))
            return any(set(row.paises.values_list('codigo', flat=True)) == set(candidate.get('paises', [])) for row in rows)
        scope = candidate.get('ambito', 'pendiente')
        if scope == 'pendiente':
            return False
        option = None
        if scope in ('opcion', 'destino'):
            target = _candidatos(proposal).get('opciones', {}).get(candidate.get('opcion'))
            if not target:
                return False
            option = next((row for row in offer.opciones.filter(
                programa=target.get('texto'), nivel=target.get('nivel'), modalidad=target.get('modalidad'))
                if set(row.paises.values_list('codigo', flat=True)) == set(target.get('paises', []))), None)
            if not option:
                return False
        if kind == 'beneficios':
            if scope == 'destino':
                return False  # MAE_BENEFICIO has no destination column.
            return offer.beneficios.filter(concepto=candidate.get('concepto'), opcion_estudio=option).exists()
        if kind == 'requisitos':
            rows = offer.requisitos.filter(texto_original=candidate.get('texto'), validado=True, opcion_estudio=option)
            return rows.filter(destino__codigo=candidate.get('destino')).exists() if scope == 'destino' else rows.filter(destino__isnull=True).exists()
    return False


@transaction.atomic
def resolver_pendiente(actor_id, offer_id, payload):
    serial = ResolverEntrada(data=payload)
    serial.is_valid(raise_exception=True)
    data = serial.validated_data
    actor = get_user_model().objects.select_for_update().get(pk=actor_id)
    if not actor.is_active or actor.rol != 'administrador':
        raise PermissionDenied()
    key = str(data['clave_accion'])
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 742612))', [key])
    old = Revision.objects.filter(clave_accion=key, dimension='integracion', decision='resuelta').first()
    request_hash = digest(dict({k: v for k, v in data.items() if k != 'clave_accion'}, actor_id=actor_id, offer_id=offer_id))
    if old:
        if old.detalle.get('hash_peticion') != request_hash or old.actor_id != actor_id or old.convocatoria_id != offer_id:
            raise ConflictoRevision('La clave ya corresponde a otra resolución.')
        return old, False
    offer = catalogo.Convocatoria.objects.select_for_update().get(pk=offer_id)
    applied = _aplicacion(offer)
    if not applied:
        raise serializers.ValidationError('La convocatoria no procede de una integración.')
    if offer.version != data['version_convocatoria'] or digest(detalle(offer)) != data['hash_convocatoria']:
        raise ConflictoRevision('La convocatoria cambió; revisa los datos antes de resolver.')
    issue = next((x for x in applied.detalle['pendientes'] if x['id'] == data['pendiente_id']), None)
    if not issue or issue['codigo'] not in MATERIALES:
        raise serializers.ValidationError({'pendiente_id': 'No es un pendiente material de esta aplicación.'})
    if not _comprobacion_pendiente(issue, offer, applied.propuesta):
        raise serializers.ValidationError({'pendiente_id': 'Los datos canónicos aún no acreditan la resolución.'})
    evidence = applied.propuesta.version.documentos.filter(pk=data['evidencia_id']).first()
    if not evidence or not any(r.dimension == 'documental' and r.evidencia_id == evidence.pk and r.decision == 'aprobada' for r in vigentes(applied.version_id)):
        raise serializers.ValidationError({'evidencia_id': 'Se necesita evidencia exacta revisada de la versión aplicada.'})
    if '.' in issue['campo'] and issue['campo'].split('.', 1)[0] in ('opciones', 'beneficios', 'requisitos') and not any(
        ref['campo'] == issue['campo'] and ref['evidencia_id'] == evidence.pk
        for ref in applied.propuesta.procedencia
    ):
        raise serializers.ValidationError({'evidencia_id': 'La evidencia debe corresponder al candidato pendiente exacto.'})
    previous = Revision.objects.filter(aplicacion=applied, dimension='integracion', decision='resuelta', detalle__pendiente_id=issue['id']).order_by('-id').first()
    if previous and previous.detalle.get('hash_convocatoria') == data['hash_convocatoria'] and previous.detalle.get('version_convocatoria') == offer.version:
        raise ConflictoRevision('Este pendiente ya tiene una resolución vigente para los datos actuales.')
    detail = {'pendiente_id': issue['id'], 'evidencia_id': evidence.pk,
              'version_convocatoria': offer.version, 'hash_convocatoria': data['hash_convocatoria'],
              'hash_peticion': request_hash, 'motivo': data['motivo']}
    return Revision.objects.create(actor=actor, version=applied.version, propuesta=applied.propuesta,
        convocatoria=offer, aplicacion=applied, dimension='integracion', decision='resuelta',
        motivo=data['motivo'], detalle=detail, sustituye=previous, clave_accion=key), True
