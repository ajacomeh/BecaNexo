import hashlib
import json
import re
from urllib.parse import urlsplit
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from perfiles.serializers import StrictModelSerializer
from perfiles.models import Pais, Area
from . import models as m
from .reglas import CONTRATOS, validar


def safe_url(value):
    if not value: return value
    try:
        URLValidator(schemes=["http", "https"])(value)
        parts = urlsplit(value)
        if parts.username or parts.password: raise ValueError()
    except (DjangoValidationError, ValueError):
        raise serializers.ValidationError("Usa una URL HTTP/HTTPS sin credenciales.")
    return value


class InstitucionSerializer(StrictModelSerializer):
    class Meta:
        model = m.Institucion
        fields = ("id", "nombre", "sector", "pais", "url_oficial")
        read_only_fields = ("id",)

    def validate_pais(self, value):
        if value.codigo != "EC": raise serializers.ValidationError("La entidad oferente debe ser ecuatoriana.")
        return value

    validate_url_oficial = staticmethod(safe_url)


class ConvocatoriaSerializer(StrictModelSerializer):
    areas = serializers.PrimaryKeyRelatedField(queryset=Area.objects.all(), many=True, required=False)
    estado = serializers.CharField(read_only=True)
    class Meta:
        model = m.Convocatoria
        exclude = ("clave_deduplicacion",)
        read_only_fields = ("id", "revision", "activa", "version", "actualizado_en")

    validate_url_oficial = staticmethod(safe_url)
    validate_url_bases = staticmethod(safe_url)

    def validate(self, attrs):
        v = lambda k: attrs.get(k, getattr(self.instance, k, None))
        if v("institucion").pais.codigo != "EC": raise serializers.ValidationError({"institucion": "Oferente fuera del alcance ecuatoriano."})
        if v("apertura") and v("cierre") and v("apertura") > v("cierre"):
            raise serializers.ValidationError({"cierre": "No puede ser anterior a la apertura."})
        if "areas" in attrs and len(set(attrs["areas"])) != len(attrs["areas"]): raise serializers.ValidationError({"areas": "No repitas áreas."})
        identity = [v("institucion").pk, " ".join(v("titulo").casefold().split()), v("url_oficial") or ""]
        attrs["clave_deduplicacion"] = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        return attrs

    def create(self, data):
        areas = data.pop("areas", [])
        obj = super().create(data)
        for area in areas: m.ConvocatoriaArea.objects.create(convocatoria=obj, area=area)
        return obj

    def update(self, obj, data):
        areas = data.pop("areas", None)
        obj = super().update(obj, data)
        if areas is not None:
            obj.areas.exclude(area__in=areas).delete()
            for area in areas: m.ConvocatoriaArea.objects.get_or_create(convocatoria=obj, area=area)
        return obj

    def to_representation(self, instance):
        # El campo de escritura usa IDs de CAT_AREA, no IDs de la relación.
        data = super().to_representation(instance)
        data["areas"] = list(instance.areas.values_list("area_id", flat=True))
        return data


class OpcionSerializer(StrictModelSerializer):
    paises = serializers.PrimaryKeyRelatedField(queryset=Pais.objects.all(), many=True, required=False)
    class Meta:
        model = m.OpcionEstudio
        exclude = ("convocatoria",)
        read_only_fields = ("id",)
        validators = []
        extra_kwargs = {"cupos": {"min_value": 1}, "duracion_meses": {"min_value": 1}}

    def validate_paises(self, value):
        if len(set(value)) != len(value): raise serializers.ValidationError("No repitas países.")
        return value


class AmbitoSerializer(StrictModelSerializer):
    def validate(self, attrs):
        option = attrs.get("opcion_estudio", getattr(self.instance, "opcion_estudio", None))
        if option and option.convocatoria_id != self.context["convocatoria"].pk:
            raise serializers.ValidationError({"opcion_estudio": "La opción debe pertenecer a esta convocatoria."})
        return attrs


class BeneficioSerializer(AmbitoSerializer):
    class Meta:
        model = m.Beneficio
        exclude = ("convocatoria",)
        read_only_fields = ("id",)
        extra_kwargs = {"porcentaje": {"min_value": 0, "max_value": 100}, "monto": {"min_value": 0}}

    def validate(self, attrs):
        attrs = super().validate(attrs)
        v = lambda k: attrs.get(k, getattr(self.instance, k, None))
        currency = v("moneda")
        if currency is not None and not re.fullmatch(r"[A-Z]{3}", currency): raise serializers.ValidationError({"moneda": "Usa el código monetario de tres letras mayúsculas (por ejemplo USD)."})
        if v("monto") is not None and not currency: raise serializers.ValidationError({"moneda": "Obligatoria cuando existe un monto."})
        return attrs


class RequisitoSerializer(AmbitoSerializer):
    class Meta:
        model = m.Requisito
        exclude = ("convocatoria",)
        read_only_fields = ("id",)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        v = lambda k: attrs.get(k, getattr(self.instance, k, None))
        tipo = v("tipo_requisito").codigo
        if tipo not in CONTRATOS: raise serializers.ValidationError({"tipo_requisito": "Tipo no soportado."})
        # El operador se deriva del contrato, no de código enviado por el cliente.
        operador = attrs.get("operador", CONTRATOS[tipo][1])
        validar(tipo, v("valor_estructurado"), v("fecha_referencia"), v("modo_comprobacion"), operador)
        attrs["operador"] = operador
        return attrs
