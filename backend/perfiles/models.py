from django.conf import settings
from django.db import models
from django.db.models import Q, F
from django.utils import timezone


NIVELES = [(v, n) for v, n in [("bachillerato", "Bachillerato"), ("grado", "Tercer nivel / grado"), ("especializacion", "Especialización"), ("maestria", "Maestría"), ("doctorado", "Doctorado")]]
MODALIDADES = [("presencial", "Presencial"), ("virtual", "Virtual"),
               ("semipresencial", "Semipresencial"), ("hibrida", "Híbrida")]
MCER = [(v, v) for v in ("A1", "A2", "B1", "B2", "C1", "C2")]
ESTADOS = [("en_curso", "En curso"), ("concluidos", "Concluidos")]
DEDICACIONES = [("completa", "Tiempo completo"), ("parcial", "Tiempo parcial"), ("ambas", "Ambas")]


def dominio(campo, choices, nombre, nullable=False):
    condition = Q(**{f"{campo}__in": [v for v, _ in choices]})
    if nullable:
        condition |= Q(**{f"{campo}__isnull": True})
    return models.CheckConstraint(condition=condition, name=nombre)


class Pais(models.Model):
    codigo = models.CharField(max_length=2, unique=True)
    nombre = models.CharField(max_length=100)

    class Meta:
        db_table = "CAT_PAIS"
        ordering = ["nombre", "id"]
        constraints = [models.CheckConstraint(condition=Q(codigo__regex=r"^[A-Z]{2}$"), name="pais_codigo_iso")]


class Idioma(models.Model):
    codigo = models.CharField(max_length=12, unique=True)
    nombre = models.CharField(max_length=80)

    class Meta:
        db_table = "CAT_IDIOMA"
        ordering = ["nombre", "id"]


class Area(models.Model):
    nombre = models.CharField(max_length=140, unique=True)

    class Meta:
        db_table = "CAT_AREA"
        ordering = ["nombre", "id"]


class Perfil(models.Model):
    descripcion = models.TextField(max_length=1500, null=True, blank=True)
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    nacionalidad = models.ForeignKey(Pais, on_delete=models.PROTECT, related_name="nacionales")
    residencia = models.ForeignKey(Pais, on_delete=models.PROTECT, null=True, blank=True, related_name="residentes")
    fecha_nacimiento = models.DateField(null=True, blank=True)
    provincia_residencia = models.TextField(null=True, blank=True)
    ciudad_residencia = models.TextField(null=True, blank=True)
    dedicacion_disponible = models.CharField(max_length=20, choices=DEDICACIONES, null=True, blank=True)
    disponible_traslado = models.BooleanField(null=True, blank=True)
    disponible_extranjero = models.BooleanField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    actualizado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "MAE_PERFIL"
        constraints = [dominio("dedicacion_disponible", DEDICACIONES, "perfil_dedicacion", True),
                       models.CheckConstraint(condition=Q(version__gte=1), name="perfil_version_positiva")]


class Formacion(models.Model):
    perfil = models.ForeignKey(Perfil, on_delete=models.CASCADE, related_name="formaciones")
    nivel = models.CharField(max_length=30, choices=NIVELES)
    carrera = models.CharField(max_length=200)
    institucion = models.CharField(max_length=200, null=True, blank=True)
    titulo_obtenido = models.BooleanField()
    promedio = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    escala_min = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    escala_max = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    estado_estudios = models.CharField(max_length=20, choices=ESTADOS)
    nombre_titulo = models.TextField(null=True, blank=True)
    fecha_finalizacion = models.DateField(null=True, blank=True)
    area = models.ForeignKey(Area, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        db_table = "MAE_FORMACION"
        ordering = ["id"]
        constraints = [
            dominio("nivel", NIVELES, "formacion_nivel"), dominio("estado_estudios", ESTADOS, "formacion_estado"),
            models.CheckConstraint(condition=Q(carrera__regex=r"\S"), name="formacion_carrera"),
            models.CheckConstraint(condition=Q(titulo_obtenido=False) | Q(estado_estudios="concluidos"), name="formacion_titulo_estado"),
            models.CheckConstraint(condition=Q(estado_estudios="concluidos") | Q(fecha_finalizacion__isnull=True), name="formacion_fecha_estado"),
            models.CheckConstraint(condition=(Q(promedio__isnull=True, escala_min__isnull=True, escala_max__isnull=True) |
                Q(promedio__isnull=False, escala_min__isnull=False, escala_max__isnull=False,
                  escala_min__lt=F("escala_max"), promedio__gte=F("escala_min"), promedio__lte=F("escala_max"))), name="formacion_promedio_escala"),
        ]


class Experiencia(models.Model):
    perfil = models.ForeignKey(Perfil, on_delete=models.CASCADE, related_name="experiencias")
    area = models.ForeignKey(Area, on_delete=models.PROTECT, null=True, blank=True)
    cargo = models.TextField(null=True, blank=True)
    descripcion = models.TextField(null=True, blank=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    actual = models.BooleanField()

    class Meta:
        db_table = "MAE_EXPERIENCIA"
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=(Q(actual=True, fecha_fin__isnull=True) |
            Q(actual=False, fecha_fin__isnull=False, fecha_fin__gte=F("fecha_inicio"))), name="experiencia_periodo")]


class PerfilIdioma(models.Model):
    perfil = models.ForeignKey(Perfil, on_delete=models.CASCADE, related_name="idiomas")
    idioma = models.ForeignKey(Idioma, on_delete=models.PROTECT)
    nivel = models.CharField(max_length=2, choices=MCER, null=True, blank=True)

    class Meta:
        db_table = "REL_PERFIL_IDIOMA"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["perfil", "idioma"], name="perfil_idioma_unico"),
                       dominio("nivel", MCER, "perfil_idioma_nivel", True)]


class PerfilArea(models.Model):
    perfil = models.ForeignKey(Perfil, on_delete=models.CASCADE, related_name="areas")
    area = models.ForeignKey(Area, on_delete=models.PROTECT)

    class Meta:
        db_table = "REL_PERFIL_AREA"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["perfil", "area"], name="perfil_area_unica")]


class Preferencia(models.Model):
    perfil = models.ForeignKey(Perfil, on_delete=models.CASCADE, related_name="preferencias")
    nivel = models.CharField(max_length=30, choices=NIVELES)
    modalidad = models.CharField(max_length=20, choices=MODALIDADES)

    class Meta:
        db_table = "CFG_PREFERENCIA"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["perfil", "nivel", "modalidad"], name="perfil_preferencia_unica"),
                       dominio("nivel", NIVELES, "preferencia_nivel"), dominio("modalidad", MODALIDADES, "preferencia_modalidad")]


class PerfilPais(models.Model):
    perfil = models.ForeignKey(Perfil, on_delete=models.CASCADE, related_name="destinos")
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT)

    class Meta:
        db_table = "REL_PERFIL_PAIS"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["perfil", "pais"], name="perfil_pais_unico")]
