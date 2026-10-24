from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.password_validation import validate_password


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        return (email or "").strip().lower()

    def get_by_natural_key(self, email):
        # ModelBackend utiliza este método, también desde el login de Admin.
        return self.get(email__iexact=self.normalize_email(email))

    async def aget_by_natural_key(self, email):
        return await self.aget(email__iexact=self.normalize_email(email))

    def create_user(self, email, nombre, password=None, **extra_fields):
        extra_fields.setdefault("rol", self.model.Rol.POSTULANTE)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        user = self.model(email=self.normalize_email(email), nombre=nombre, **extra_fields)
        user.clean()
        if password is not None:
            validate_password(password, user)
        user.set_password(password)
        # La base de datos arbitra duplicados, incluso ante escrituras concurrentes.
        user.full_clean(validate_unique=False, validate_constraints=False)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, nombre, password=None, **extra_fields):
        expected = {
            "rol": self.model.Rol.ADMINISTRADOR,
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
        }
        for field, value in expected.items():
            extra_fields.setdefault(field, value)
            if extra_fields[field] != value:
                raise ValueError(f"Un superusuario requiere {field}={value}.")
        if not password:
            raise ValueError("El superusuario requiere una contraseña.")
        return self.create_user(email, nombre, password, **extra_fields)
