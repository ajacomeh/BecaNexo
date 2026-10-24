from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm

from .models import Usuario


class UsuarioCreationForm(BaseUserCreationForm):
    class Meta:
        model = Usuario
        fields = ("email", "nombre", "rol", "is_active", "is_staff", "is_superuser")

    def clean_email(self):
        return Usuario.objects.normalize_email(self.cleaned_data["email"])


class UsuarioChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"
        field_classes = {}

    def clean_email(self):
        return Usuario.objects.normalize_email(self.cleaned_data["email"])
