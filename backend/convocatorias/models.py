from django.conf import settings
from django.db import models
from django.db.models import Q, F
from django.utils import timezone
from perfiles.models import Pais, Area, NIVELES, MODALIDADES


def dominio(field, values, name, nullable=False):
    condition = Q(**{field + "__in": [v for v, _ in values]})
    if nullable:
        condition |= Q(**{field + "__isnull": True})
    return models.CheckConstraint(condition=condition, name=name)


SECTORES = [("publico", "Público"), ("privado", "Privado")]
REVISIONES = [("pendiente", "Pendiente / borrador"), ("validada", "Validada")]
COBERTURAS = [(x, x.replace("_", " ").capitalize()) for x in ("total", "parcial", "mixta", "no_especificada")]
PERIODOS = [(x, x.capitalize()) for x in ("unico", "mensual", "anual", "otra")]
MODOS = [("dato_declarado", "Dato declarado"), ("entidad_oferente", "Entidad oferente")]


class Institucion(models.Model):
    nombre = models.CharField(max_length=200)
    sector = models.CharField(max_length=12, choices=SECTORES)
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT)
    url_oficial = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "MAE_INSTITUCION"
        ordering = ["nombre", "id"]
        constraints = [dominio("sector", SECTORES, "institucion_sector")]


class TipoBeca(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "CAT_TIPO_BECA"
        ordering = ["nombre"]


class Convocatoria(models.Model):
    institucion = models.ForeignKey(Institucion, on_delete=models.PROTECT, related_name="convocatorias")
    titulo = models.CharField(max_length=250)
    descripcion = models.TextField(blank=True, default="")
    apertura = models.DateTimeField(null=True, blank=True)
    cierre = models.DateTimeField(null=True, blank=True)
    cierre_dia = models.DateField(null=True, blank=True)
    cierre_original = models.TextField(null=True, blank=True)
    url_oficial = models.TextField(blank=True, default="")
    clave_deduplicacion = models.CharField(max_length=64, unique=True)
    revision = models.CharField(max_length=16, choices=REVISIONES, default="pendiente")
    activa = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    actualizado_en = models.DateTimeField(default=timezone.now)
    tipo_beca = models.ForeignKey(TipoBeca, on_delete=models.PROTECT, null=True, blank=True)
    cobertura_tipo = models.CharField(max_length=20, choices=COBERTURAS, null=True, blank=True)
    gastos_no_cubiertos = models.TextField(null=True, blank=True)
    obligaciones_beneficiario = models.TextField(null=True, blank=True)
    fecha_publicacion = models.DateField(null=True, blank=True)
    url_bases = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "MAE_CONVOCATORIA"
        ordering = ["-actualizado_en", "-id"]
        constraints = [
            dominio("revision", REVISIONES, "conv_revision"),
            dominio("cobertura_tipo", COBERTURAS, "conv_cobertura", True),
            models.CheckConstraint(condition=Q(version__gte=1), name="conv_version"),
            models.CheckConstraint(condition=Q(apertura__isnull=True) | Q(cierre__isnull=True) | Q(cierre__gte=F("apertura")), name="conv_fechas"),
            models.CheckConstraint(condition=Q(cierre__isnull=True) | Q(cierre_dia__isnull=True), name="conv_cierre_precision_unica"),
            models.CheckConstraint(condition=Q(cierre_dia__isnull=True) | Q(cierre_original__isnull=False, cierre_original__regex=r"\S"), name="conv_cierre_dia_original"),
        ]

    @property
    def estado(self):
        if not self.activa: return "pausada"
        if self.revision != "validada": return "borrador"
        now = timezone.now()
        if self.cierre and self.cierre <= now: return "cerrada"
        if self.cierre_dia and self.cierre_dia < timezone.localdate(now): return "cerrada"
        if self.apertura and self.apertura > now: return "proxima"
        if self.cierre_dia == timezone.localdate(now): return "cierre_hoy"
        if self.cierre is None and self.cierre_dia is None: return "sin_fecha"
        return "abierta"


class OpcionEstudio(models.Model):
    convocatoria = models.ForeignKey(Convocatoria, on_delete=models.PROTECT, related_name="opciones")
    nivel = models.CharField(max_length=30, choices=NIVELES)
    modalidad = models.CharField(max_length=20, choices=MODALIDADES)
    activa = models.BooleanField(default=True)
    programa = models.TextField(null=True, blank=True)
    institucion_destino = models.TextField(null=True, blank=True)
    inicio_estudios = models.DateField(null=True, blank=True)
    duracion_meses = models.PositiveIntegerField(null=True, blank=True)
    cupos = models.PositiveIntegerField(null=True, blank=True)
    paises = models.ManyToManyField(Pais, through="OpcionPais")

    class Meta:
        db_table = "MAE_OPCION_ESTUDIO"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["convocatoria", "nivel", "modalidad"], name="opcion_identidad"),
                       dominio("nivel", NIVELES, "opcion_nivel"), dominio("modalidad", MODALIDADES, "opcion_modalidad"),
                       models.CheckConstraint(condition=Q(cupos__isnull=True) | Q(cupos__gt=0), name="opcion_cupos"),
                       models.CheckConstraint(condition=Q(duracion_meses__isnull=True) | Q(duracion_meses__gt=0), name="opcion_duracion")]


class OpcionPais(models.Model):
    opcion_estudio = models.ForeignKey(OpcionEstudio, on_delete=models.CASCADE)
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT)

    class Meta:
        db_table = "REL_OPCION_ESTUDIO_PAIS"
        constraints = [models.UniqueConstraint(fields=["opcion_estudio", "pais"], name="opcion_pais_unico")]


class ConvocatoriaArea(models.Model):
    convocatoria = models.ForeignKey(Convocatoria, on_delete=models.CASCADE, related_name="areas")
    area = models.ForeignKey(Area, on_delete=models.PROTECT)

    class Meta:
        db_table = "REL_CONVOCATORIA_AREA"
        constraints = [models.UniqueConstraint(fields=["convocatoria", "area"], name="conv_area_unica")]


class Beneficio(models.Model):
    convocatoria = models.ForeignKey(Convocatoria, on_delete=models.PROTECT, related_name="beneficios")
    opcion_estudio = models.ForeignKey(OpcionEstudio, on_delete=models.PROTECT, null=True, blank=True)
    concepto = models.CharField(max_length=100)
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    monto = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tope_monto = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tope_moneda = models.CharField(max_length=3, null=True, blank=True)
    tope_original = models.TextField(null=True, blank=True)
    moneda = models.CharField(max_length=3, null=True, blank=True)
    periodicidad = models.CharField(max_length=30, choices=PERIODOS, null=True, blank=True)
    detalle = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "MAE_BENEFICIO"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(porcentaje__isnull=True) | Q(porcentaje__gte=0, porcentaje__lte=100), name="beneficio_porcentaje"),
            models.CheckConstraint(condition=Q(monto__isnull=True) | Q(monto__gte=0, moneda__isnull=False), name="beneficio_monto"),
            models.CheckConstraint(condition=Q(tope_monto__isnull=True) | Q(tope_monto__gte=0), name="beneficio_tope_positivo"),
            models.CheckConstraint(condition=Q(tope_monto__isnull=True, tope_moneda__isnull=True) | Q(tope_original__isnull=False, tope_original__regex=r'\S'), name="beneficio_tope_literal"),
            models.CheckConstraint(condition=Q(tope_moneda__isnull=True) | Q(tope_monto__isnull=False, tope_moneda__regex=r'^[A-Z]{3}$'), name="beneficio_tope_moneda"),
            dominio("periodicidad", PERIODOS, "beneficio_periodicidad", True),
        ]


class TipoRequisito(models.Model):
    codigo = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=100)
    esquema_valor = models.JSONField()

    class Meta:
        db_table = "CAT_TIPO_REQUISITO"
        ordering = ["id"]


class Requisito(models.Model):
    relacion_formacion = models.CharField(max_length=20, default="pendiente", choices=[("pendiente", "Relación no definida"), ("independiente", "Independiente"), ("misma_formacion", "Misma formación")])
    grupo_formacion = models.CharField(max_length=64, null=True, blank=True)
    equivalencias = models.JSONField(default=list, blank=True)
    destino = models.ForeignKey(Pais, on_delete=models.PROTECT, null=True, blank=True, related_name="requisitos_destino")
    convocatoria = models.ForeignKey(Convocatoria, on_delete=models.PROTECT, related_name="requisitos")
    texto_original = models.TextField()
    obligatorio = models.BooleanField(default=True)
    operador = models.CharField(max_length=24, null=True, blank=True)
    valor_estructurado = models.JSONField(null=True, blank=True)
    validado = models.BooleanField(default=False)
    opcion_estudio = models.ForeignKey(OpcionEstudio, on_delete=models.PROTECT, null=True, blank=True)
    activo = models.BooleanField(default=True)
    tipo_requisito = models.ForeignKey(TipoRequisito, on_delete=models.PROTECT)
    modo_comprobacion = models.CharField(max_length=30, choices=MODOS)
    documento_exigido = models.TextField(null=True, blank=True)
    detalle_acreditacion = models.TextField(null=True, blank=True)
    referencia_bases = models.TextField(null=True, blank=True)
    fecha_referencia = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "MAE_REQUISITO"
        ordering = ["id"]
        constraints = [dominio("modo_comprobacion", MODOS, "requisito_modo"),
            models.CheckConstraint(condition=Q(destino__isnull=True) | Q(opcion_estudio__isnull=False), name="requisito_destino_opcion"),
            models.CheckConstraint(condition=(Q(relacion_formacion="misma_formacion", grupo_formacion__isnull=False, grupo_formacion__regex=r"\S") |
                Q(relacion_formacion__in=["pendiente", "independiente"], grupo_formacion__isnull=True)), name="requisito_grupo_coherente")]


class Evento(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    convocatoria = models.ForeignKey(Convocatoria, on_delete=models.PROTECT, related_name="eventos", null=True)
    institucion = models.ForeignKey(Institucion, on_delete=models.PROTECT, null=True)
    accion = models.CharField(max_length=60)
    cambios = models.JSONField()
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "AUD_EVENTO"
        ordering = ["-id"]
        constraints = [models.CheckConstraint(
            condition=Q(convocatoria__isnull=False, institucion__isnull=True) | Q(convocatoria__isnull=True, institucion__isnull=False),
            name="evento_un_objeto")]
