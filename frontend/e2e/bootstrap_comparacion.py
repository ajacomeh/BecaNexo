"""Fixture local idempotente. Capturar stdout en memoria: contiene una sesión, no imprimirla."""
import json
import os
from datetime import date, datetime, timezone
from importlib import import_module
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.conf import settings
from django.db import transaction
from django.contrib.auth import get_user_model, SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from perfiles.models import Pais, Idioma, Perfil, PerfilIdioma
from convocatorias.models import Institucion, Convocatoria, OpcionEstudio, Requisito, TipoRequisito, Beneficio
from convocatorias.reglas import CONTRATOS
from convocatorias.services import publicar, audit, detalle
from convocatorias.comparacion import evaluar_convocatoria

assert settings.DATABASES["default"]["NAME"] == "becanexo_db", "Fixture exclusiva de desarrollo local."
with transaction.atomic():
    ec = Pais.objects.get(codigo="EC")
    en = Idioma.objects.get(codigo="en")
    admin = get_user_model().objects.get(email="demo-catalogo-administrador@example.com")
    assert admin.rol == "administrador" and admin.is_active and not admin.is_superuser and not admin.is_staff
    user = get_user_model().objects.filter(email="demo-comparacion@example.com").first()
    if user is None:
        user = get_user_model().objects.create_user(email="demo-comparacion@example.com", nombre="DEMOSTRACIÓN comparación", password=None)
        perfil = Perfil.objects.create(usuario=user, nacionalidad=ec)
        PerfilIdioma.objects.create(perfil=perfil, idioma=en, nivel="B2")
    assert user.nombre == "DEMOSTRACIÓN comparación" and user.rol == "postulante" and user.is_active
    assert not user.has_usable_password() and not user.is_superuser and not user.is_staff
    perfil = Perfil.objects.get(usuario=user)
    assert perfil.nacionalidad_id == ec.pk and perfil.fecha_nacimiento is None
    assert PerfilIdioma.objects.get(perfil=perfil, idioma=en).nivel == "B2", "Fixture cambiada; no se sobrescribe."
    key = "demo-comparacion-requisitos-v1"
    conv = Convocatoria.objects.filter(clave_deduplicacion=key).first()
    if conv is None:
        institucion, _ = Institucion.objects.get_or_create(nombre="DEMOSTRACIÓN · Entidad comparación ficticia", defaults={"pais": ec, "sector": "publico"})
        assert institucion.pais_id == ec.pk
        conv = Convocatoria.objects.create(institucion=institucion, titulo="DEMOSTRACIÓN · Comparación de requisitos",
            descripcion="Oferta ficticia para probar comparación explicable. No admite postulaciones reales.",
            url_oficial="https://example.org/demostracion-comparacion", clave_deduplicacion=key,
            cierre=datetime(2027, 11, 3, tzinfo=timezone.utc))
        a = OpcionEstudio.objects.create(convocatoria=conv, nivel="maestria", modalidad="virtual", programa="DEMOSTRACIÓN A · Inglés B2")
        b = OpcionEstudio.objects.create(convocatoria=conv, nivel="maestria", modalidad="presencial", programa="DEMOSTRACIÓN B · Inglés C1")
        c = OpcionEstudio.objects.create(convocatoria=conv, nivel="grado", modalidad="virtual", programa="DEMOSTRACIÓN C · Edad máxima")
        for opcion in (a, b, c): opcion.paises.add(ec)
        Beneficio.objects.create(convocatoria=conv, concepto="Matrícula", detalle="Beneficio ficticio para demostración; sin monto publicado.")
        def regla(code, value, **extra):
            Requisito.objects.create(convocatoria=conv, tipo_requisito=TipoRequisito.objects.get(codigo=code),
                texto_original=f"DEMOSTRACIÓN · Condición {code}", valor_estructurado=value,
                operador=CONTRATOS[code][1], validado=True,
                modo_comprobacion="entidad_oferente" if code == "ACREDITACION" else "dato_declarado", **extra)
        regla("NACIONALIDAD", {"codigos_pais": ["EC"]})
        regla("ACREDITACION", {"certificados_admitidos": "Certificado de idioma según las bases ficticias"})
        regla("IDIOMA", {"codigo_idioma": "en", "nivel_minimo": "B2"}, opcion_estudio=a)
        regla("IDIOMA", {"codigo_idioma": "en", "nivel_minimo": "C1"}, opcion_estudio=b)
        regla("EDAD", {"maximo": 35}, fecha_referencia=date(2027, 11, 3), opcion_estudio=c)
        publicar(conv)
        audit(admin, "demostracion_comparacion_crear", None, detalle(conv), convocatoria=conv)
    assert conv.titulo == "DEMOSTRACIÓN · Comparación de requisitos" and conv.revision == "validada" and conv.activa
    antigua = conv.opciones.filter(programa="DEMOSTRACIÓN C · Edad pendiente", nivel="grado", modalidad="virtual").first()
    if antigua:
        antes = {"opcion": antigua.pk, "programa": antigua.programa}
        antigua.programa = "DEMOSTRACIÓN C · Edad máxima"
        antigua.save(update_fields=["programa"])
        audit(admin, "demostracion_renombrar_opcion", antes, {"opcion": antigua.pk, "programa": antigua.programa}, convocatoria=conv)
    assert [o["resultado"] for o in evaluar_convocatoria(user, conv)["opciones"]] == ["cumple", "no_cumple", "desconocido"], "Fixture cambiada; revisar sin sobrescribir."

session = import_module(settings.SESSION_ENGINE).SessionStore()
session[SESSION_KEY] = str(user.pk)
session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
session[HASH_SESSION_KEY] = user.get_session_auth_hash()
session.save()
print(json.dumps({"session": session.session_key, "convocatoria": conv.pk}))
