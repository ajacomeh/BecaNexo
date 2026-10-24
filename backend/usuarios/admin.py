from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import UsuarioChangeForm, UsuarioCreationForm
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    list_display = ("email", "nombre", "rol", "is_active", "is_staff")
    list_filter = ("rol", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "nombre")
    ordering = ("email",)
    readonly_fields = ("last_login", "creado_en")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos de negocio", {"fields": ("nombre", "rol", "is_active")}),
        ("Permisos de Django", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Fechas", {"fields": ("last_login", "creado_en")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": (
            "email", "nombre", "password1", "password2", "rol", "is_active", "is_staff", "is_superuser",
        )}),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if not request.user.is_superuser:
            return (*fields, "rol", "is_staff", "is_superuser", "groups", "user_permissions")
        return fields

    # Gestionar cuentas permite cambiar contraseñas y privilegios: se reserva
    # a superusuarios, incluso si un staff recibe permisos de este modelo.
    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)
