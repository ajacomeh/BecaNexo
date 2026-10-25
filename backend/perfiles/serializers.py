from django.utils import timezone
from rest_framework import serializers
from . import models as m


class StrictModelSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        allowed = {key for key, field in self.fields.items() if not field.read_only}
        if isinstance(data, dict) and set(data) - allowed:
            raise serializers.ValidationError({key: ["Campo no permitido."] for key in set(data) - allowed})
        # Vacíos opcionales se conservan como desconocidos, nunca como falsos/ceros.
        if isinstance(data, dict):
            data = {key: None if isinstance(value, str) and not value.strip() and self.fields[key].allow_null else value for key, value in data.items()}
        return super().to_internal_value(data)


class PerfilSerializer(StrictModelSerializer):
    class Meta:
        model = m.Perfil
        fields = ("id", "nacionalidad", "residencia", "fecha_nacimiento", "provincia_residencia", "ciudad_residencia",
                  "dedicacion_disponible", "disponible_traslado", "disponible_extranjero", "version", "actualizado_en")
        read_only_fields = ("id", "version", "actualizado_en")
        extra_kwargs = {"nacionalidad": {"required": False}}

    def validate_nacionalidad(self, value):
        if value.codigo != "EC":
            raise serializers.ValidationError("El alcance del sistema es para ciudadanos ecuatorianos.")
        return value

    def validate_fecha_nacimiento(self, value):
        if value and value > timezone.localdate():
            raise serializers.ValidationError("La fecha de nacimiento no puede ser futura.")
        return value


class FormacionSerializer(StrictModelSerializer):
    class Meta:
        model = m.Formacion
        fields = ("id", "nivel", "carrera", "institucion", "titulo_obtenido", "promedio", "escala_min", "escala_max",
                  "estado_estudios", "nombre_titulo", "fecha_finalizacion", "area")
        read_only_fields = ("id",)

    def validate(self, attrs):
        def value(key):
            return attrs.get(key, getattr(self.instance, key, None))
        errors = {}
        if value("titulo_obtenido") and value("estado_estudios") != "concluidos":
            errors["titulo_obtenido"] = "Un título obtenido requiere estudios concluidos."
        fecha = value("fecha_finalizacion")
        if fecha and (fecha > timezone.localdate() or value("estado_estudios") == "en_curso"):
            errors["fecha_finalizacion"] = "Declara una fecha no futura solo para estudios concluidos."
        promedio, minimo, maximo = (value(key) for key in ("promedio", "escala_min", "escala_max"))
        if any(v is not None for v in (promedio, minimo, maximo)):
            if any(v is None for v in (promedio, minimo, maximo)):
                for key in ("promedio", "escala_min", "escala_max"):
                    if value(key) is None: errors[key] = "Promedio y escala deben declararse juntos."
            elif minimo >= maximo:
                errors["escala_max"] = "El máximo debe ser mayor que el mínimo."
            elif not minimo <= promedio <= maximo:
                errors["promedio"] = "El promedio debe encontrarse dentro de la escala."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class ExperienciaSerializer(StrictModelSerializer):
    class Meta:
        model = m.Experiencia
        fields = ("id", "area", "cargo", "descripcion", "fecha_inicio", "fecha_fin", "actual")
        read_only_fields = ("id",)

    def validate(self, attrs):
        def value(key): return attrs.get(key, getattr(self.instance, key, None))
        inicio, fin, actual = value("fecha_inicio"), value("fecha_fin"), value("actual")
        errors = {}
        if inicio and inicio > timezone.localdate(): errors["fecha_inicio"] = "El inicio no puede ser futuro."
        if actual and fin: errors["fecha_fin"] = "Una experiencia actual no lleva fecha final."
        if actual is False and not fin: errors["fecha_fin"] = "Indica la fecha final de la experiencia."
        if fin and (fin > timezone.localdate() or (inicio and fin < inicio)):
            errors["fecha_fin"] = "La fecha final debe estar entre el inicio y hoy."
        if errors: raise serializers.ValidationError(errors)
        return attrs


class IdiomaSerializer(StrictModelSerializer):
    class Meta:
        model = m.PerfilIdioma
        fields = ("id", "idioma", "nivel")
        read_only_fields = ("id",)
        validators = []  # La clave compuesta incluye el perfil que asigna el servidor.


class AreaSerializer(StrictModelSerializer):
    class Meta:
        model = m.PerfilArea
        fields = ("id", "area")
        read_only_fields = ("id",)
        validators = []


class PreferenciaSerializer(StrictModelSerializer):
    class Meta:
        model = m.Preferencia
        fields = ("id", "nivel", "modalidad")
        read_only_fields = ("id",)
        validators = []


class DestinoSerializer(StrictModelSerializer):
    class Meta:
        model = m.PerfilPais
        fields = ("id", "pais")
        read_only_fields = ("id",)
        validators = []
