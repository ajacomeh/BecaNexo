from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower, Trim
from django.utils import timezone

from .managers import UsuarioManager


class Usuario(AbstractBaseUser, PermissionsMixin):
    class Rol(models.TextChoices):
        POSTULANTE = "postulante", "Postulante"
        ADMINISTRADOR = "administrador", "Administrador"

    email = models.EmailField("correo electrónico", max_length=254, unique=True)
    password = models.CharField("contraseña", max_length=128, db_column="password_hash")
    nombre = models.CharField("nombre visible", max_length=180)
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.POSTULANTE)
    is_active = models.BooleanField("activo", default=True, db_column="activo")
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    is_staff = models.BooleanField("acceso al administrador de Django", default=False)

    objects = UsuarioManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombre"]

    class Meta:
        db_table = "MAE_USUARIO"
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        constraints = [
            models.UniqueConstraint(Lower(Trim("email")), name="usuario_email_ci_unique"),
            models.CheckConstraint(condition=models.Q(rol__in=["postulante", "administrador"]), name="usuario_rol_valido"),
            models.CheckConstraint(condition=models.Q(email__regex=r"\S"), name="usuario_email_no_vacio"),
            models.CheckConstraint(condition=models.Q(nombre__regex=r"\S"), name="usuario_nombre_no_vacio"),
        ]

    def clean(self):
        super().clean()
        self.email = type(self).objects.normalize_email(self.email)
        self.nombre = (self.nombre or "").strip()
        errors = {}
        if not self.email:
            errors["email"] = "El correo es obligatorio."
        if not self.nombre:
            errors["nombre"] = "El nombre es obligatorio."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.email = type(self).objects.normalize_email(self.email)
        self.nombre = (self.nombre or "").strip()
        return super().save(*args, **kwargs)

    def get_full_name(self):
        return self.nombre

    def get_short_name(self):
        return self.nombre
