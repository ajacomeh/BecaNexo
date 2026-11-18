from django.conf import settings
from django.db import models
from django.utils import timezone

ESTADOS_CORREO = [("pendiente", "Pendiente"), ("enviando", "Envío iniciado"),
                  ("enviado", "Enviado"), ("fallido", "Fallido"), ("omitido", "Omitido")]


class Notificacion(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones")
    convocatoria = models.ForeignKey("convocatorias.Convocatoria", on_delete=models.PROTECT, related_name="notificaciones")
    motivos = models.JSONField(default=list)
    creada_en = models.DateTimeField(default=timezone.now, editable=False)
    leida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "TRA_NOTIFICACION"
        ordering = ["-creada_en", "-id"]
        constraints = [models.UniqueConstraint(fields=["usuario", "convocatoria"], name="notif_usuario_convocatoria_unica")]
        indexes = [models.Index(fields=["usuario", "leida_en", "-creada_en"], name="notif_bandeja_idx")]


class PreferenciaCorreo(models.Model):
    """La ausencia de fila equivale a no haber consentido."""
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preferencia_correo")
    habilitada = models.BooleanField(default=False)
    actualizada_en = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "CFG_PREFERENCIA_CORREO"


class EntregaCorreo(models.Model):
    # TRA_NOTIFICACION ya es única por usuario y convocatoria: esa creación es el evento.
    notificacion = models.OneToOneField(Notificacion, on_delete=models.PROTECT, related_name="entrega_correo")
    estado = models.CharField(max_length=12, choices=ESTADOS_CORREO, default="pendiente")
    intentos = models.PositiveSmallIntegerField(default=0)
    proximo_intento_en = models.DateTimeField(default=timezone.now)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(default=timezone.now)
    enviado_en = models.DateTimeField(null=True, blank=True)
    codigo_error = models.CharField(max_length=60, blank=True, default="")

    class Meta:
        db_table = "TRA_ENTREGA_CORREO"
        indexes = [models.Index(fields=["estado", "proximo_intento_en"], name="correo_cola_idx")]
        constraints = [models.CheckConstraint(
            condition=models.Q(estado__in=[item[0] for item in ESTADOS_CORREO]), name="correo_estado_valido")]
