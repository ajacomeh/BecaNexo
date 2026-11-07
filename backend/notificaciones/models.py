from django.conf import settings
from django.db import models
from django.utils import timezone


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
