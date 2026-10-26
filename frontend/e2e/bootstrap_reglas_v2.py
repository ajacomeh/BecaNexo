"""Fixture DEMOSTRACIÓN v2. stdout contiene sesiones: capturar, nunca imprimir."""
import json
import os
import sys
from pathlib import Path
from importlib import import_module
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.conf import settings
from django.db import transaction
from django.contrib.auth import get_user_model, SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from perfiles.models import Pais, Perfil, Formacion
from convocatorias.models import Convocatoria, Institucion, OpcionEstudio, Requisito, TipoRequisito
from convocatorias.services import audit, detalle

assert settings.DATABASES["default"]["NAME"] == "becanexo_db"
with transaction.atomic():
    ec, es = Pais.objects.get(codigo="EC"), Pais.objects.get(codigo="ES")
    admin = get_user_model().objects.get(email="demo-catalogo-administrador@example.com")
    assert admin.rol == "administrador" and admin.is_active and not admin.is_superuser and not admin.is_staff
    user = get_user_model().objects.filter(email="demo-reglas-v2@example.com").first()
    if user is None:
        user = get_user_model().objects.create_user(email="demo-reglas-v2@example.com", nombre="DEMOSTRACIÓN reglas v2", password=None)
        perfil = Perfil.objects.create(usuario=user, nacionalidad=ec, disponible_traslado=False, disponible_extranjero=False)
        Formacion.objects.create(perfil=perfil, nivel="grado", carrera="DEMOSTRACIÓN Software", nombre_titulo="Ing. Software",
            estado_estudios="concluidos", titulo_obtenido=True, promedio=9, escala_min=0, escala_max=10)
    assert user.nombre == "DEMOSTRACIÓN reglas v2" and user.rol == "postulante" and user.is_active and not user.has_usable_password() and not user.is_superuser and not user.is_staff
    assert user.perfil.formaciones.filter(nombre_titulo="Ing. Software", promedio=9).count() == 1, "No sobrescribir fixture modificada."
    conv = Convocatoria.objects.filter(clave_deduplicacion="demostracion-reglas-v2").first()
    if conv is None:
        institucion = Institucion.objects.get(nombre="DEMOSTRACIÓN · Entidad comparación ficticia")
        conv = Convocatoria.objects.create(institucion=institucion, titulo="DEMOSTRACIÓN · Reglas aprobadas v2", clave_deduplicacion="demostracion-reglas-v2",
            descripcion="Oferta ficticia para verificar configuración administrativa y comparación. No admite postulaciones reales.", url_oficial="https://example.org/demostracion-reglas-v2")
        opcion = OpcionEstudio.objects.create(convocatoria=conv, nivel="maestria", modalidad="virtual", programa="DEMOSTRACIÓN · Alternativas Ecuador y España")
        opcion.paises.add(ec, es)
        Requisito.objects.create(convocatoria=conv, tipo_requisito=TipoRequisito.objects.get(codigo="DOCUMENTO"), texto_original="DEMO v2 · Documento externo",
            operador="externo", modo_comprobacion="entidad_oferente", validado=True, valor_estructurado={"documento": "Título según bases ficticias"})
        audit(admin, "demostracion_reglas_v2_crear", None, detalle(conv), convocatoria=conv)
    assert conv.titulo == "DEMOSTRACIÓN · Reglas aprobadas v2"
    opcion = conv.opciones.get(programa="DEMOSTRACIÓN · Alternativas Ecuador y España")
result = {"convocatoria": conv.pk, "opcion": opcion.pk, "espana": es.pk}
for key, account in (("administrador", admin), ("postulante", user)):
    session = import_module(settings.SESSION_ENGINE).SessionStore()
    session[SESSION_KEY] = str(account.pk)
    session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    session[HASH_SESSION_KEY] = account.get_session_auth_hash()
    session.save()
    result[key] = session.session_key
print(json.dumps(result))
