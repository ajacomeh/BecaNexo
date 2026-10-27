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
                       check('rast_ejec_sin_publicaciones', Q(publicaciones_observadas=0, versiones_nuevas=0, observaciones_sin_cambios=0))]


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
    ejecucion = models.ForeignKey(Ejecucion, on_delete=models.PROTECT, related_name='accesos')
    documento = models.ForeignKey(Documento, null=True, on_delete=models.PROTECT)
    secuencia = models.PositiveIntegerField()
    rol = models.CharField(max_length=20)
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
                       check('rast_acceso_seq_positivo', Q(secuencia__gt=0)),
                       check('rast_acceso_rol', Q(rol__in=['robots', 'indice', 'ficha', 'bases'])),
                       check('rast_acceso_http', Q(http_status__isnull=True) | Q(http_status__gte=100, http_status__lte=599)),
                       check('rast_acceso_resultado', Q(resultado__in=['descargado', 'reutilizado'], documento__isnull=False) | Q(resultado__in=['bloqueado', 'error', 'redirigido'], documento__isnull=True)),
                       check('rast_acceso_fechas', Q(fin__gte=F('admitido_en')) & (Q(inicio_peticion_en__isnull=True) | Q(inicio_peticion_en__gte=F('admitido_en'), fin__gte=F('inicio_peticion_en'))))]


class Incidencia(models.Model):
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
        constraints = [check('rast_revision_objeto', Q(dimension='configuracion', fuente__isnull=False, incidencia__isnull=True) | Q(dimension='incidencia', fuente__isnull=True, incidencia__isnull=False)),
                       check('rast_revision_decision', Q(decision__in=['pendiente', 'aprobada', 'rechazada', 'resuelta', 'aplicada'])),
                       check('rast_revision_motivo', Q(motivo__regex=r'\S'))]
