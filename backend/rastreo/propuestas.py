"""Snapshots de trabajo administrativos. Nunca escribe en el catálogo ni accede a red."""
import hashlib
import json
from datetime import date
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from convocatorias.serializers import safe_url, ConvocatoriaSerializer
from convocatorias.models import Institucion, Convocatoria
from perfiles.models import Pais
from .models import Publicacion, Version, Observacion, Revision, Propuesta, PropuestaRevision
from .revisiones import vigentes, ConflictoRevision
from .storage import root_path, key_for, verify_file, StorageError


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Cerrado(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({'non_field_errors': ['Objeto o campos no admitidos.']})
        for name, field in self.fields.items():
            if name in data and data[name] is not None:
                if isinstance(field, serializers.CharField) and not isinstance(data[name], str):
                    raise serializers.ValidationError({name: 'Debe ser texto.'})
                if isinstance(field, serializers.IntegerField) and (type(data[name]) is not int):
                    raise serializers.ValidationError({name: 'Debe ser un entero.'})
                if isinstance(field, serializers.IntegerField) and data[name] > 9223372036854775807:
                    raise serializers.ValidationError({name: 'Identificador fuera de rango.'})
                if isinstance(field, serializers.ListField) and isinstance(field.child, serializers.IntegerField):
                    if not isinstance(data[name], list) or any(type(v) is not int or not 0 < v <= 9223372036854775807 for v in data[name]):
                        raise serializers.ValidationError({name: 'Usa una lista de identificadores enteros positivos.'})
        return super().to_internal_value(data)


def text(limit=5000):
    return serializers.CharField(required=False, allow_blank=True, max_length=limit)


class Candidato(Cerrado):
    id = serializers.CharField(max_length=60)
    texto = text()
    nivel = text(60)
    modalidad = text(60)
    destinos = text(500)
    paises = serializers.ListField(child=serializers.CharField(max_length=3), max_length=100, required=False)
    concepto = text(100)
    porcentaje = text(30)
    monto = text(30)
    moneda = text(20)
    tope = text(100)
    ambito = serializers.ChoiceField(choices=['pendiente', 'comun', 'opcion', 'destino'], default='pendiente')
    opcion = text(60)
    destino = text(100)
    tipo = text(60)
    condiciones = text()

    def validate_paises(self, values):
        if len(set(values)) != len(values) or set(values) - set(Pais.objects.filter(codigo__in=values).values_list('codigo', flat=True)):
            raise serializers.ValidationError('Selecciona códigos de país existentes sin repetirlos.')
        return values


class Datos(Cerrado):
    titulo = text(250)
    descripcion = text(15000)
    institucion = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    url_oficial = text(2048)
    apertura_original = text(500)
    cierre_original = text(500)
    cierre_dia = text(10)
    opciones = Candidato(many=True, required=False, max_length=50)
    beneficios = Candidato(many=True, required=False, max_length=50)
    requisitos = Candidato(many=True, required=False, max_length=100)

    validate_url_oficial = staticmethod(safe_url)

    def validate_cierre_dia(self, value):
        if not value:
            return value
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except ValueError:
            raise serializers.ValidationError('Indica un día válido en formato AAAA-MM-DD, sin hora.')
        return value

    def validate(self, data):
        if data.get('cierre_dia') and not (data.get('cierre_original') or '').strip():
            raise serializers.ValidationError({'cierre_original': 'Conserva el texto literal de la fecha revisada.'})
        ids = [item['id'] for kind in ('opciones', 'beneficios', 'requisitos') for item in data.get(kind, [])]
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError('Los identificadores de elementos no pueden repetirse.')
        options = {v['id']: v for v in data.get('opciones', [])}
        for kind in ('beneficios', 'requisitos'):
            for item in data.get(kind, []):
                if item.get('opcion') and item['opcion'] not in options:
                    raise serializers.ValidationError('La opción referenciada no pertenece a la propuesta.')
                if item.get('ambito') == 'comun' and (item.get('opcion') or item.get('destino')):
                    raise serializers.ValidationError('El ámbito común no admite una opción o destino específicos.')
                if item.get('ambito') == 'opcion' and item.get('destino'):
                    raise serializers.ValidationError('Elige ámbito de destino para una condición territorial.')
                if item.get('destino') and item['destino'] not in options.get(item.get('opcion'), {}).get('paises', []):
                    raise serializers.ValidationError('El destino debe estar seleccionado en la opción de esta propuesta.')
        return data


class Referencia(Cerrado):
    campo = serializers.CharField(max_length=100)
    evidencia_id = serializers.IntegerField(min_value=1)
    localizador = serializers.CharField(max_length=2000)
    original = text(15000)
    motivo = serializers.CharField(max_length=5000)


class Entrada(Cerrado):
    clave_accion = serializers.UUIDField()
    version_id = serializers.IntegerField(min_value=1)
    observacion_base_id = serializers.IntegerField(min_value=1)
    revisiones = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=200)
    datos = Datos()
    procedencia = Referencia(many=True, max_length=200)

    def validate_revisiones(self, values):
        if len(set(values)) != len(values):
            raise serializers.ValidationError('No repitas revisiones.')
        return sorted(values)

    def validate(self, data):
        allowed = set(data['datos']) | {f'{kind}.{item["id"]}' for kind in ('opciones', 'beneficios', 'requisitos') for item in data['datos'].get(kind, [])}
        if any(ref['campo'] not in allowed for ref in data['procedencia']):
            raise serializers.ValidationError({'procedencia': 'Indica un campo presente o tipo.identificador de un candidato.'})
        return data


def latest(publication):
    return Observacion.objects.filter(publicacion_id=publication, version__isnull=False).order_by('-observada_en', '-id').first()


def evaluar(version, observation, data, references, review_ids, ignore_convocatoria_id=None):
    blocks, pending = [], []
    def issue(target, code, field, reason, resolution):
        target.append(dict(id=f'{code}:{field}', codigo=code, campo=field, motivo=reason, condicion_resolucion=resolution))
    current = latest(version.publicacion_id)
    if version.manifiesto.get('pendientes'):
        issue(blocks, 'BASES_AUSENTES', 'documentos', 'La versión registra evidencia pendiente de obtención.', 'Resolver la evidencia en una etapa autorizada; guardar o validar no descarga documentos.')
    if not current or current.pk != observation:
        issue(blocks, 'CONTEXTO_OBSOLETO', 'observacion', 'Cambió la última observación exitosa.', 'Actualizar explícitamente el contexto conservando el trabajo.')
    reviews = list(vigentes(version.pk))
    if set(review_ids) != {r.pk for r in reviews}:
        issue(blocks, 'REVISION_CAMBIADA', 'revisiones', 'La selección no coincide con las revisiones vigentes.', 'Consultar y confirmar las revisiones actuales.')
    for dimension in ('extraccion', 'oferente'):
        if not any(r.dimension == dimension and r.decision == 'aprobada' for r in reviews):
            issue(blocks, 'REVISION_PENDIENTE', dimension, f'Falta aprobación de {dimension}.', 'Revisión administrativa de esta versión exacta.')
    evidence = list(version.documentos.select_related('documento'))
    used_evidence = {r['evidencia_id'] for r in references}
    if not evidence:
        issue(blocks, 'SIN_EVIDENCIA', 'documentos', 'No hay documentos asociados.', 'Debe existir evidencia exacta verificable.')
    for relation in evidence:
        if (relation.rol == 'bases_pdf' or relation.pk in used_evidence) and not any(r.dimension == 'documental' and r.evidencia_id == relation.pk and r.decision == 'aprobada' for r in reviews):
            issue(blocks, 'BASES_PENDIENTES', f'evidencia.{relation.pk}', 'Bases o evidencia utilizada sin aprobación documental vigente.', 'Revisar esta relación documental exacta.')
        try:
            doc = relation.documento
            if doc.clave_almacenamiento != key_for(doc.sha256):
                raise StorageError('Clave inválida')
            path = root_path() / doc.clave_almacenamiento
            if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root_path()):
                raise StorageError('Ruta inválida')
            verify_file(path, doc.sha256, doc.tamano_bytes)
        except (StorageError, OSError):
            issue(blocks, 'EVIDENCIA_NO_DISPONIBLE', f'evidencia.{relation.pk}', 'Evidencia ausente o inconsistente.', 'Verificar almacenamiento; no se descargará automáticamente.')
    for field in ('titulo', 'institucion', 'url_oficial'):
        if not data.get(field):
            issue(blocks, 'DATO_NECESARIO', field, 'Dato necesario para el futuro borrador.', 'Completar con evidencia revisada.')
    institution = Institucion.objects.filter(pk=data.get('institucion')).select_related('pais').first()
    if institution and institution.pais.codigo != 'EC':
        issue(blocks, 'OFERENTE_NO_ADMISIBLE', 'institucion', 'El oferente no es ecuatoriano.', 'Identificar un oferente admisible sin inventar convenios.')
    if institution and institution.pais.codigo == 'EC' and data.get('titulo'):
        candidate = ConvocatoriaSerializer(data={k: data[k] for k in ('institucion', 'titulo', 'descripcion', 'url_oficial') if k in data})
        if candidate.is_valid() and Convocatoria.objects.filter(clave_deduplicacion=candidate.validated_data['clave_deduplicacion']).exclude(pk=ignore_convocatoria_id).exists():
            issue(blocks, 'DUPLICADO_CATALOGO', 'titulo', 'Coincide con la identidad de una convocatoria existente.', 'Revisar la coincidencia; no se vincula ni sobrescribe automáticamente.')
    if not data.get('descripcion'):
        issue(pending, 'DESCRIPCION_PENDIENTE', 'descripcion', 'Falta descripción para publicación.', 'Transcribir información respaldada y revisar su procedencia.')
    for field in ('titulo', 'institucion', 'url_oficial'):
        if data.get(field) and not any(r['campo'] == field for r in references):
            issue(blocks, 'PROCEDENCIA_PENDIENTE', field, 'Falta referencia y justificación del valor.', 'Indicar documento exacto, localizador y motivo.')
    for field in ('apertura_original', 'cierre_original'):
        observed = version.datos_extraidos.get(field.removesuffix('_original'))
        has_original = isinstance(observed, dict) and any(observed.get(k) for k in ('original', 'fecha', 'texto_original'))
        if data.get(field) or has_original:
            issue(pending, 'PRECISION_TEMPORAL', field, 'Fecha literal aún no representada como instante verificado.', 'Revisar precisión; no inventar hora. La integración temporal pertenece al siguiente bloque.')
    observed_benefit = version.datos_extraidos.get('beneficio', {})
    if isinstance(observed_benefit, dict) and any(isinstance(v, dict) and 'tope' in str(v.get('tipo', '')).lower() for v in observed_benefit.get('cantidades', [])):
        issue(pending, 'TOPE_FUENTE', 'beneficio_original', 'La fuente contiene un tope: omitirlo del formulario no lo resuelve.', 'Conservar el alcance económico y esperar representación fiel.')
    if not data.get('opciones'):
        issue(pending, 'SIN_OPCIONES', 'opciones', 'No hay opciones confirmadas.', 'Identificar opciones respaldadas, sin inferirlas de menciones.')
    for kind in ('opciones', 'beneficios', 'requisitos'):
        for item in data.get(kind, []):
            field = f'{kind}.{item["id"]}'
            issue(pending, 'CANDIDATO_PENDIENTE', field, 'Candidato de trabajo, no objeto confirmado del catálogo.', 'Revisión y mapeo tipado mediante los contratos del catálogo antes de integrar.')
            if item.get('tope'):
                issue(pending, 'TOPE_NO_REPRESENTADO', field, 'El tope no es un importe fijo.', 'Conservar límite y concepto; esperar representación económica aprobada.')
            if kind != 'opciones' and item.get('ambito', 'pendiente') == 'pendiente':
                issue(pending, 'AMBITO_DESCONOCIDO', field, 'Ámbito todavía desconocido.', 'Identificar alcance explícito; no asumir toda la convocatoria.')
            if kind != 'opciones' and (item.get('ambito') in ('opcion', 'destino') and not item.get('opcion') or item.get('ambito') == 'destino' and not item.get('destino')):
                issue(pending, 'AMBITO_INCOMPLETO', field, 'Falta seleccionar opción o destino.', 'Completar el alcance con referencias de la misma propuesta.')
    return dict(puede_crear=not blocks, bloqueos=blocks, pendientes_publicacion=pending, creacion_habilitada=False)


@transaction.atomic
def guardar(actor_id, publication_id, payload, previous=None):
    actor = get_user_model().objects.select_for_update().get(pk=actor_id)
    if not actor.is_active or actor.rol != 'administrador':
        raise PermissionDenied()
    serial = Entrada(data=payload)
    serial.is_valid(raise_exception=True)
    data = serial.validated_data
    key = str(data.pop('clave_accion'))
    request_hash = digest(dict(data, publicacion_id=publication_id, sustituye_id=previous, actor_id=actor_id))
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 742610))', [key])
    old = Propuesta.objects.filter(clave_accion=key).first()
    if old:
        if old.hash_peticion != request_hash:
            raise ConflictoRevision('La clave ya corresponde a otro contenido.')
        return old, False
    if data['datos'].get('institucion') and not Institucion.objects.filter(pk=data['datos']['institucion']).exists():
        raise serializers.ValidationError({'institucion': 'Entidad inexistente.'})
    publication = Publicacion.objects.select_for_update().get(pk=publication_id)
    from convocatorias.models import BorradorRastreo
    automatic_offer = BorradorRastreo.objects.filter(publicacion=publication).first() if publication.convocatoria_id else None
    if publication.convocatoria_id is not None and (not automatic_offer or automatic_offer.convocatoria_id != publication.convocatoria_id):
        raise ConflictoRevision('La publicación ya está integrada. Su propuesta aplicada permanece inmutable.')
    version = Version.objects.select_for_update().filter(pk=data['version_id'], publicacion=publication).first()
    if not version or not Observacion.objects.filter(pk=data['observacion_base_id'], version=version, publicacion=publication).exists():
        raise serializers.ValidationError('Versión u observación ajena a la publicación.')
    head = Propuesta.objects.filter(publicacion=publication, sucesora__isnull=True).first()
    if (head.pk if head else None) != previous:
        raise ConflictoRevision('Otra persona guardó una revisión. Conserva tu texto y consulta el historial.')
    if not Revision.objects.filter(pk__in=data['revisiones'], version=version).count() == len(data['revisiones']):
        raise serializers.ValidationError('Revisión ajena a la versión.')
    evidence_ids = set(version.documentos.values_list('pk', flat=True))
    for reference in data['procedencia']:
        if reference['evidencia_id'] not in evidence_ids:
            raise serializers.ValidationError('Documento ajeno a la versión.')
    result = evaluar(version, data['observacion_base_id'], data['datos'], data['procedencia'], data['revisiones'],
                     automatic_offer.convocatoria_id if automatic_offer else None)
    obj = Propuesta.objects.create(publicacion=publication, version=version, observacion_base_id=data['observacion_base_id'],
        sustituye_id=previous, actor=actor, clave_accion=key, datos=data['datos'], procedencia=data['procedencia'],
        pendientes=result, hash_peticion=request_hash, hash_propuesta=digest(dict(data, resultado=result)))
    PropuestaRevision.objects.bulk_create([PropuestaRevision(propuesta=obj, revision_id=pk) for pk in data['revisiones']])
    return obj, True


def representar(obj):
    return {**{key: getattr(obj, key) for key in ('id', 'publicacion_id', 'version_id', 'observacion_base_id', 'sustituye_id', 'creada_en', 'datos', 'procedencia', 'pendientes', 'hash_propuesta', 'contrato_version')},
            'autor': {'id': obj.actor_id, 'nombre': obj.actor.nombre},
            'revisiones': list(obj.revisiones.values_list('revision_id', flat=True))}
