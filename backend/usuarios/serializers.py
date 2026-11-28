from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Usuario


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"detail": "Se enviaron campos no permitidos."})
        return super().to_internal_value(data)


class RegistroSerializer(StrictSerializer):
    nombre = serializers.CharField(max_length=180)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        attrs["email"] = Usuario.objects.normalize_email(attrs["email"])
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Las contraseñas no coinciden."})
        user = Usuario(email=attrs["email"], nombre=attrs["nombre"])
        try:
            validate_password(attrs["password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs


class LoginSerializer(StrictSerializer):
    email = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RecuperarSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)


class RestablecerSerializer(StrictSerializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Las contraseñas no coinciden."})
        return attrs


class NombreSerializer(StrictSerializer):
    nombre = serializers.CharField(max_length=Usuario._meta.get_field("nombre").max_length)

    def to_internal_value(self, data):
        # CharField admite números convirtiéndolos a texto; aquí se exige texto.
        if isinstance(data, dict) and "nombre" in data and not isinstance(data["nombre"], str):
            raise serializers.ValidationError({"nombre": ["Debe ser texto."]})
        return super().to_internal_value(data)


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ("id", "email", "nombre", "rol")
