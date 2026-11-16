import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q, F
from django.utils import timezone


def check(name, condition):
    return models.CheckConstraint(name=name, condition=condition)


class Fuente(models.Model):
    nombre = models.CharField(max_length=160)
    tipo = models.CharField(max_length=12, default='publico')
    adaptador = models.CharField(max_length=100, default='siau')
    url_base = models.TextField(unique=True)
    frecuencia_min = models.PositiveIntegerField(default=1440)
    espera_seg = models.PositiveIntegerField(default=2)
    timeout_seg = models.PositiveIntegerField(default=15)
    activa = models.BooleanField(default=False)
    aprobada_publicacion_automatica = models.BooleanField(default=False)
    politica_acceso = models.JSONField()
    politica_version = models.CharField(max_length=60, default='siau-cerrada/1')
    creada_en = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'CFG_FUENTE'
        constraints = [check('rast_fuente_no_auto', Q(aprobada_publicacion_automatica=False)),
                       check('rast_fuente_limites', Q(frecuencia_min__gt=0, espera_seg__gte=2, timeout_seg__gt=0, timeout_seg__lte=15)),
                       check('rast_fuente_tipo', Q(tipo__in=['publico', 'privado']))]


class Ejecucion(models.Model):
    fuente = models.ForeignKey(Fuente, on_delete=models.PROTECT)
    clave_idempotencia = models.UUIDField(default=uuid.uuid4, unique=True)
    origen = models.CharField(max_length=16, default='manual')
    solicitado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    inicio = models.DateTimeField(default=timezone.now)
    fin = models.DateTimeField(null=True)
    estado = models.CharField(max_length=20, default='en_curso')
    configuracion_snapshot = models.JSONField()
    version_extractor = models.CharField(max_length=80)
    version_normalizador = models.CharField(max_length=60, default='urls-cerradas/1')
    latido_en = models.DateTimeField(null=True)
    publicaciones_observadas = models.PositiveIntegerField(default=0)
    versiones_nuevas = models.PositiveIntegerField(default=0)
    observaciones_sin_cambios = models.PositiveIntegerField(default=0)
    error_resumen = models.TextField(null=True)

    class Meta:
        db_table = 'TRA_EJECUCION_RASTREO'
        constraints = [models.UniqueConstraint(fields=['fuente'], condition=Q(estado='en_curso'), name='rast_una_activa'),
                       check('rast_ejec_actor', Q(origen='manual', solicitado_por__isnull=False) | Q(origen='programada', solicitado_por__isnull=True)),
                       check('rast_ejec_estado', Q(estado='en_curso', fin__isnull=True) | Q(estado__in=['finalizada', 'parcial', 'fallida', 'omitida'], fin__isnull=False)),
                       check('rast_ejec_fechas', Q(fin__isnull=True) | Q(fin__gte=F('inicio'))),
                       check('rast_ejec_contadores', Q(versiones_nuevas__lte=F('publicaciones_observadas'), observaciones_sin_cambios__lte=F('publicaciones_observadas')))]


class Documento(models.Model):
    sha256 = models.CharField(max_length=64, unique=True)
    tamano_bytes = models.PositiveBigIntegerField()
    mime = models.CharField(max_length=100)
    clave_almacenamiento = models.CharField(max_length=180, unique=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'TEC_DOCUMENTO_RASTREO'
        constraints = [check('rast_doc_hash', Q(sha256__regex=r'^[0-9a-f]{64}$')),
                       check('rast_doc_mime', Q(mime__in=['text/html', 'text/plain', 'application/pdf'])),
                       check('rast_doc_tamano', Q(tamano_bytes__lte=8388608))]


class Acceso(models.Model):
    publicacion = models.ForeignKey('Publicacion', null=True, on_delete=models.PROTECT)
    ejecucion = models.ForeignKey(Ejecucion, on_delete=models.PROTECT, related_name='accesos')
    documento = models.ForeignKey(Documento, null=True, on_delete=models.PROTECT)
    secuencia = models.PositiveIntegerField()
    rol = models.CharField(max_length=20)
    metodo = models.CharField(max_length=4, default='GET')
    parametros_publicos = models.JSONField(null=True, blank=True)
    url_original = models.TextField()
    url_normalizada = models.CharField(max_length=2048)
    url_final = models.TextField(null=True)
    admitido_en = models.DateTimeField()
    inicio_peticion_en = models.DateTimeField(null=True)
    fin = models.DateTimeField()
    espera_ms = models.PositiveBigIntegerField(default=0)
    duracion_ms = models.PositiveBigIntegerField(null=True)
    http_status = models.PositiveSmallIntegerField(null=True)
    resultado = models.CharField(max_length=20)
    error_codigo = models.CharField(max_length=60, null=True)
    etag = models.TextField(null=True)
    last_modified = models.TextField(null=True)

    class Meta:
        db_table = 'TRA_ACCESO_RASTREO'
        constraints = [models.UniqueConstraint(fields=['ejecucion', 'secuencia'], name='rast_acceso_secuencia'),
                       check('rast_acceso_metodo', Q(metodo='GET', parametros_publicos__isnull=True) | Q(metodo='POST', parametros_publicos__isnull=False)),
                       check('rast_acceso_seq_positivo', Q(secuencia__gt=0)),
                       check('rast_acceso_rol', Q(rol__in=['robots', 'indice', 'ficha', 'bases'])),
                       check('rast_acceso_http', Q(http_status__isnull=True) | Q(http_status__gte=100, http_status__lte=599)),
                       check('rast_acceso_resultado', Q(resultado__in=['descargado', 'reutilizado'], documento__isnull=False) | Q(resultado__in=['bloqueado', 'error', 'redirigido'], documento__isnull=True)),
                       check('rast_acceso_fechas', Q(fin__gte=F('admitido_en')) & (Q(inicio_peticion_en__isnull=True) | Q(inicio_peticion_en__gte=F('admitido_en'), fin__gte=F('inicio_peticion_en'))))]


class Incidencia(models.Model):
    publicacion = models.ForeignKey('Publicacion', null=True, on_delete=models.PROTECT)
    version = models.ForeignKey('Version', null=True, on_delete=models.PROTECT)
    fuente = models.ForeignKey(Fuente, on_delete=models.PROTECT)
    ejecucion = models.ForeignKey(Ejecucion, null=True, on_delete=models.PROTECT, related_name='incidencias')
    acceso = models.ForeignKey(Acceso, null=True, on_delete=models.PROTECT)
    codigo = models.CharField(max_length=60)
    gravedad = models.CharField(max_length=12, default='error')
    detalle = models.TextField()
    detectada_en = models.DateTimeField(default=timezone.now)
    clave_evento = models.UUIDField(default=uuid.uuid4, unique=True)

    class Meta:
        db_table = 'TRA_INCIDENCIA_RASTREO'
        constraints = [check('rast_incid_gravedad', Q(gravedad__in=['aviso', 'error'])),
                       check('rast_incid_acceso_ejec', Q(acceso__isnull=True) | Q(ejecucion__isnull=False))]


class Revision(models.Model):
    propuesta = models.ForeignKey('Propuesta', null=True, on_delete=models.PROTECT, related_name='integraciones')
    convocatoria = models.ForeignKey('convocatorias.Convocatoria', null=True, on_delete=models.PROTECT, related_name='revisiones_integracion')
    aplicacion = models.ForeignKey('self', null=True, on_delete=models.PROTECT, related_name='resoluciones')
    version = models.ForeignKey('Version', null=True, on_delete=models.PROTECT)
    evidencia = models.ForeignKey('VersionDocumento', null=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    creada_en = models.DateTimeField(default=timezone.now)
    fuente = models.ForeignKey(Fuente, null=True, on_delete=models.PROTECT)
    incidencia = models.ForeignKey(Incidencia, null=True, on_delete=models.PROTECT)
    dimension = models.CharField(max_length=24)
    decision = models.CharField(max_length=24)
    motivo = models.TextField()
    detalle = models.JSONField()
    clave_accion = models.UUIDField(default=uuid.uuid4, unique=True)
    sustituye = models.ForeignKey('self', null=True, on_delete=models.PROTECT)
    # Sello de BD para comprobar auditoría en la misma transacción.
    transaccion_id = models.BigIntegerField(db_default=models.Func(function='txid_current', output_field=models.BigIntegerField()), editable=False)

    class Meta:
        db_table = 'AUD_REVISION_RASTREO'
        constraints = [check('rast_revision_objeto', Q(dimension='configuracion', fuente__isnull=False, incidencia__isnull=True, version__isnull=True, evidencia__isnull=True) | Q(dimension='incidencia', fuente__isnull=True, incidencia__isnull=False, version__isnull=True, evidencia__isnull=True) | Q(dimension__in=['extraccion', 'documental', 'oferente', 'integracion'], fuente__isnull=True, incidencia__isnull=True, version__isnull=False)),
                       check('rast_revision_integracion', Q(dimension='integracion', propuesta__isnull=False, convocatoria__isnull=False) & (Q(decision='aplicada', aplicacion__isnull=True, sustituye__isnull=True) | Q(decision='resuelta', aplicacion__isnull=False)) | (~Q(dimension='integracion') & Q(propuesta__isnull=True, convocatoria__isnull=True, aplicacion__isnull=True))),
                       models.UniqueConstraint(fields=['propuesta'], condition=Q(dimension='integracion', decision='aplicada'), name='rast_integracion_propuesta_unica'),
                       models.UniqueConstraint(fields=['convocatoria'], condition=Q(dimension='integracion', decision='aplicada'), name='rast_integracion_convocatoria_unica'),
                       check('rast_revision_decision', Q(decision__in=['pendiente', 'aprobada', 'rechazada', 'resuelta', 'aplicada'])),
                       check('rast_revision_motivo', Q(motivo__regex=r'\S')),
                       check('rast_revision_editorial', ~Q(dimension__in=['extraccion', 'documental', 'oferente']) | Q(decision__in=['pendiente', 'aprobada', 'rechazada'])),
                       check('rast_revision_evidencia', Q(dimension__in=['documental', 'oferente'], evidencia__isnull=False) | (~Q(dimension__in=['documental', 'oferente']) & Q(evidencia__isnull=True))),
                       models.UniqueConstraint(fields=['sustituye'], condition=Q(version__isnull=False), name='rast_revision_un_sucesor'),
                       models.UniqueConstraint(fields=['version', 'dimension'], condition=Q(sustituye__isnull=True, dimension__in=['extraccion', 'oferente']), name='rast_revision_raiz_dimension'),
                       models.UniqueConstraint(fields=['version', 'evidencia'], condition=Q(sustituye__isnull=True, dimension='documental'), name='rast_revision_raiz_documento')]


class Publicacion(models.Model):
    fuente = models.ForeignKey(Fuente, on_delete=models.PROTECT)
    convocatoria = models.ForeignKey('convocatorias.Convocatoria', null=True, on_delete=models.PROTECT)
    url_original = models.TextField()
    url_normalizada = models.CharField(max_length=2048)
    normalizacion_version = models.CharField(max_length=60)
    primera_deteccion = models.DateTimeField(default=timezone.now)
    ultima_deteccion = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'TRA_PUBLICACION_FUENTE'
        constraints = [models.UniqueConstraint(fields=['fuente', 'url_normalizada'], name='rast_publicacion_identidad'),
                       check('rast_publicacion_fechas', Q(ultima_deteccion__gte=F('primera_deteccion')))]


class CandidatoIndice(models.Model):
    """Referencia factual del índice; no es publicación extraída ni borrador."""
    fuente = models.ForeignKey(Fuente, on_delete=models.PROTECT)
    ultima_ejecucion = models.ForeignKey(Ejecucion, on_delete=models.PROTECT)
    url_normalizada = models.CharField(max_length=2048)
    titulo_publico = models.CharField(max_length=200)
    pagina = models.PositiveSmallIntegerField()
    respuesta_sha256 = models.CharField(max_length=64)
    primera_deteccion = models.DateTimeField(default=timezone.now)
    ultima_deteccion = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'TRA_CANDIDATO_INDICE'
        constraints = [models.UniqueConstraint(fields=['fuente', 'url_normalizada'], name='rast_candidato_indice_url'),
                       check('rast_candidato_indice_fecha', Q(ultima_deteccion__gte=F('primera_deteccion'))),
                       check('rast_candidato_indice_pagina', Q(pagina__gt=0, pagina__lte=12)),
                       check('rast_candidato_indice_hash', Q(respuesta_sha256__regex=r'^[0-9a-f]{64}$'))]


class Version(models.Model):
    publicacion = models.ForeignKey(Publicacion, on_delete=models.PROTECT, related_name='versiones')
    numero = models.PositiveIntegerField()
    creada_en = models.DateTimeField(default=timezone.now)
    version_extractor = models.CharField(max_length=80)
    version_normalizador = models.CharField(max_length=60)
    version_contrato = models.PositiveIntegerField()
    hash_manifiesto = models.CharField(max_length=64)
    hash_contenido_relevante = models.CharField(max_length=64)
    manifiesto = models.JSONField()
    datos_extraidos = models.JSONField()
    texto_extraido = models.TextField(null=True)
    advertencias = models.JSONField()
    estado_extraccion = models.CharField(max_length=20)
    transaccion_id = models.BigIntegerField(db_default=models.Func(function='txid_current', output_field=models.BigIntegerField()), editable=False)

    class Meta:
        db_table = 'TRA_VERSION_PUBLICACION'
        constraints = [models.UniqueConstraint(fields=['publicacion', 'numero'], name='rast_version_numero'),
                       models.UniqueConstraint(fields=['publicacion', 'hash_manifiesto', 'version_extractor', 'version_normalizador', 'version_contrato'], name='rast_version_identidad'),
                       check('rast_version_positivos', Q(numero__gt=0, version_contrato__gt=0)),
                       check('rast_version_hashes', Q(hash_manifiesto__regex=r'^[0-9a-f]{64}$', hash_contenido_relevante__regex=r'^[0-9a-f]{64}$')),
                       check('rast_version_estado', Q(estado_extraccion__in=['completa', 'parcial', 'fallida']))]


class VersionDocumento(models.Model):
    version = models.ForeignKey(Version, on_delete=models.PROTECT, related_name='documentos')
    documento = models.ForeignKey(Documento, on_delete=models.PROTECT)
    rol = models.CharField(max_length=20)
    url_original = models.TextField()
    url_normalizada = models.CharField(max_length=2048)
    localizador = models.TextField(null=True)

    class Meta:
        db_table = 'REL_VERSION_DOCUMENTO'
        constraints = [models.UniqueConstraint(fields=['version', 'rol', 'url_normalizada'], name='rast_version_documento_url'),
                       check('rast_version_documento_rol', Q(rol__in=['ficha_html', 'bases_pdf', 'anexo']))]


class Observacion(models.Model):
    ejecucion = models.ForeignKey(Ejecucion, on_delete=models.PROTECT, related_name='observaciones')
    publicacion = models.ForeignKey(Publicacion, on_delete=models.PROTECT, related_name='observaciones')
    version = models.ForeignKey(Version, null=True, on_delete=models.PROTECT)
    observada_en = models.DateTimeField(default=timezone.now)
    resultado = models.CharField(max_length=24)
    detalle = models.TextField(null=True)

    class Meta:
        db_table = 'TRA_OBSERVACION_RASTREO'
        indexes = [models.Index(fields=['publicacion', 'observada_en'], name='rast_obs_publicacion_fecha')]
        constraints = [models.UniqueConstraint(fields=['ejecucion', 'publicacion'], name='rast_observacion_unica'),
                       check('rast_observacion_resultado', Q(resultado='fallo', version__isnull=True) | Q(resultado__in=['nueva', 'sin_cambios', 'cambio_bytes', 'cambio_relevante'], version__isnull=False))]


class Propuesta(models.Model):
    publicacion = models.ForeignKey(Publicacion, on_delete=models.PROTECT)
    version = models.ForeignKey(Version, on_delete=models.PROTECT)
    observacion_base = models.ForeignKey(Observacion, on_delete=models.PROTECT)
    sustituye = models.OneToOneField('self', null=True, on_delete=models.PROTECT, related_name='sucesora')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    creada_en = models.DateTimeField(default=timezone.now)
    clave_accion = models.UUIDField(unique=True)
    contrato_version = models.PositiveIntegerField(default=1)
    datos = models.JSONField()
    procedencia = models.JSONField()
    pendientes = models.JSONField()
    hash_propuesta = models.CharField(max_length=64)
    hash_peticion = models.CharField(max_length=64)
    transaccion_id = models.BigIntegerField(db_default=models.Func(function='txid_current', output_field=models.BigIntegerField()), editable=False)

    class Meta:
        db_table = 'TRA_PROPUESTA_CAMBIO'
        constraints = [models.UniqueConstraint(fields=['publicacion'], condition=Q(sustituye__isnull=True), name='rast_propuesta_raiz'),
                       check('rast_propuesta_contrato', Q(contrato_version=1)),
                       check('rast_propuesta_hash', Q(hash_propuesta__regex=r'^[0-9a-f]{64}$', hash_peticion__regex=r'^[0-9a-f]{64}$'))]


class PropuestaRevision(models.Model):
    propuesta = models.ForeignKey(Propuesta, on_delete=models.PROTECT, related_name='revisiones')
    revision = models.ForeignKey(Revision, on_delete=models.PROTECT)

    class Meta:
        db_table = 'REL_PROPUESTA_REVISION'
        constraints = [models.UniqueConstraint(fields=['propuesta', 'revision'], name='rast_propuesta_revision_unica')]
