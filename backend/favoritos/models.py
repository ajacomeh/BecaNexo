from django.conf import settings
from django.db import models
from django.utils import timezone


class Favorito(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    convocatoria = models.ForeignKey("convocatorias.Convocatoria", on_delete=models.PROTECT)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "REL_FAVORITO"
        ordering = ["-creado_en", "-id"]
        constraints = [models.UniqueConstraint(fields=["usuario", "convocatoria"], name="favorito_usuario_conv_unico")]
