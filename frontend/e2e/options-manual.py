"""Manual browser fixture for option identity. Writes only to test_becanexo_db."""
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

from django.conf import settings

if (settings.DATABASES["default"]["NAME"] != "becanexo_db"
        or settings.DATABASES["default"]["TEST"]["NAME"] != "test_becanexo_db"):
    raise RuntimeError("La configuración no coincide con las bases esperadas; no se inicia el entorno.")
settings.DATABASES["default"]["NAME"] = "test_becanexo_db"
settings.ALLOWED_HOSTS = ["127.0.0.1"]
settings.CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:5174"]
settings.SESSION_COOKIE_SECURE = False
settings.CSRF_COOKIE_SECURE = False

import django
django.setup()

from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder

with connection.cursor() as cursor:
    cursor.execute("SELECT current_database()")
    if cursor.fetchone()[0] != "test_becanexo_db":
        raise RuntimeError("La conexión no corresponde a test_becanexo_db.")
if not MigrationRecorder(connection).migration_qs.filter(
        app="convocatorias", name="0005_remove_opcionestudio_opcion_identidad").exists():
    raise RuntimeError("Falta convocatorias.0005 en test_becanexo_db.")

from convocatorias.models import Convocatoria, Institucion, TipoBeca, TipoRequisito
from convocatorias.serializers import (BeneficioSerializer, ConvocatoriaSerializer,
                                       OpcionSerializer, RequisitoSerializer)
from convocatorias.services import publicar
from perfiles.models import Area, Formacion, Idioma, Pais, Perfil
from usuarios.models import Usuario

MARK = "BLOQUE 15 · ESCENARIO AISLADO · "


def temp_root(value):
    root = Path(value).resolve()
    if (root.parent != Path(tempfile.gettempdir()).resolve()
            or not root.name.startswith("becanexo-options-") or not root.is_dir()):
        raise RuntimeError("Se requiere un directorio temporal propio de este escenario.")
    return root


def save(serializer_class, payload, *, assigned=None, **kwargs):
    serializer = serializer_class(data=payload, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.save(**(assigned or {}))


def seed():
    # Los cargadores de catálogos actualizan nombres existentes; solo se admiten tablas vacías.
    # No se usa flush ni se sobrescriben datos de pruebas previas.
    if any(model.objects.exists() for model in
           (Usuario, Pais, Idioma, Area, Institucion, TipoBeca, TipoRequisito, Convocatoria)):
        raise RuntimeError("La base de pruebas contiene datos; no se modifica ni se vacía.")
    folder = Path(tempfile.mkdtemp(prefix="becanexo-options-"))
    (folder / "storage").mkdir()
    password = secrets.token_urlsafe(24) + "A1!"
    tag = folder.name.removeprefix("becanexo-options-")
    admin_email = f"opciones-admin-{tag}@example.com"
    student_email = f"opciones-postulante-{tag}@example.com"
    with transaction.atomic():
        call_command("cargar_catalogos", verbosity=0)
        call_command("cargar_catalogos_convocatorias", verbosity=0)
        ec = Pais.objects.get(codigo="EC")
        es = Pais.objects.get(codigo="ES")
        admin = Usuario.objects.create_user(admin_email, "Administrador sintético", password,
                                            rol="administrador")
        institution = Institucion.objects.create(nombre=MARK + "Entidad ecuatoriana ficticia",
                                                 sector="privado", pais=ec)
        offer = save(ConvocatoriaSerializer, {
            "institucion": institution.pk, "titulo": MARK + "Programas independientes",
            "descripcion": "Escenario sintético exclusivo de test_becanexo_db. No es una beca real ni admite postulaciones.",
            "url_oficial": "https://example.org/becanexo/bloque-15-ficticio",
        })
        options = []
        for program, destination, institution_name, concept, percent, level in (
            ("Programa ficticio de Analítica", ec, "Instituto ficticio de Quito", "Matrícula", "80.00", "grado"),
            ("Programa ficticio de Investigación", es, "Instituto ficticio de Madrid", "Alojamiento", "50.00", "maestria"),
        ):
            option = save(OpcionSerializer, {
                "nivel": "maestria", "modalidad": "virtual", "activa": True,
                "programa": program, "institucion_destino": institution_name,
                "paises": [destination.pk],
            }, assigned={"convocatoria": offer})
            save(BeneficioSerializer, {"opcion_estudio": option.pk, "concepto": concept,
                                     "porcentaje": percent, "detalle": f"Cobertura ficticia de {concept.lower()}"},
                 context={"convocatoria": offer}, assigned={"convocatoria": offer})
            requirement_type = TipoRequisito.objects.get(codigo="FORMACION")
            save(RequisitoSerializer, {
                "opcion_estudio": option.pk, "tipo_requisito": requirement_type.pk,
                "texto_original": f"Formación {level} concluida para {program} (condición ficticia).",
                "valor_estructurado": {"nivel_minimo": level,
                                       "niveles_admitidos": ["grado", "maestria"] if level == "grado" else ["maestria"],
                                       "estado_exigido": "concluidos", "titulo_obtenido": True},
                "modo_comprobacion": "dato_declarado", "relacion_formacion": "independiente",
                "validado": True, "activo": True, "obligatorio": True,
            }, context={"convocatoria": offer}, assigned={"convocatoria": offer})
            options.append(option)
        publicar(offer)
        student = Usuario.objects.create_user(student_email, "Postulante sintético", password)
        profile = Perfil.objects.create(usuario=student, nacionalidad=ec, residencia=ec)
        Formacion.objects.create(perfil=profile, nivel="grado", carrera="Analítica ficticia",
                                 institucion="Instituto ficticio", titulo_obtenido=True,
                                 estado_estudios="concluidos")
    (folder / "credentials.txt").write_text(
        f"ENTORNO AISLADO: test_becanexo_db\nAdministrador: {admin_email}\n"
        f"Postulante: {student_email}\nContraseña sintética de ambas cuentas: {password}\n",
        encoding="utf-8")
    (folder / "scenario.json").write_text(json.dumps({"offer_id": offer.pk,
        "option_ids": [o.pk for o in options], "admin": admin_email,
        "student": student_email}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"folder": str(folder), "offer_id": offer.pk,
                      "option_ids": [o.pk for o in options], "admin": admin_email,
                      "student": student_email}, ensure_ascii=False))


def serve(folder):
    folder = temp_root(folder)
    scenario = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
    if not Convocatoria.objects.filter(pk=scenario["offer_id"], titulo__startswith=MARK).exists():
        raise RuntimeError("El escenario sintético no está en la base de pruebas.")
    settings.RASTREO_STORAGE_ROOT = str(folder / "storage")
    call_command("runserver", "127.0.0.1:8766", use_reloader=False)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "seed":
        seed()
    elif len(sys.argv) == 3 and sys.argv[1] == "serve":
        serve(sys.argv[2])
    else:
        raise RuntimeError("Uso: options-manual.py seed | serve DIRECTORIO_TEMPORAL")
