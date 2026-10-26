"""Datos sintéticos cerrados para la revisión de noviembre de 2026.

No es un importador general. Nunca actualiza datos existentes. La huella de
AUD_EVENTO permite detectar cambios sin guardar contraseñas ni sesiones.
"""
import hashlib
import json
from pathlib import Path

from django.core.management.base import CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Q
from usuarios.models import Usuario
from perfiles import models as p, serializers as ps
from . import models as m, serializers as s
from .comparacion import evaluar_convocatoria
from .reglas import esquema
from .services import audit, detalle, publicar

PREFIX = "DEMOSTRACIÓN · REVISIÓN DE AVANCES · "
EMAIL = "revision-avances@example.com"
NAME = "DEMOSTRACIÓN · Persona sintética de revisión"
INSTITUTION = PREFIX + "Fundación Horizonte Ficticio Ecuador"
BASE = "https://example.org/becanexo/revision-avances/"
MARK = "demo_avances_manifest_v1"
AREAS = ["Tecnologías de la información y la comunicación", "Administración de empresas y derecho", "Educación"]
CASES = [("A", "Coincidencia declarada", ["cumple"]),
         ("B", "Inglés C1 requerido", ["no_cumple"]),
         ("C", "Promedio de educación pendiente", ["desconocido"]),
         ("D", "Tres alternativas de estudio", ["cumple", "no_cumple", "desconocido"]),
         ("E", "Área TIC y promedio en la misma formación", ["no_cumple"])]
CODES = ["NACIONALIDAD", "EDAD", "IDIOMA", "FORMACION", "TITULO_AREA", "PROMEDIO", "RESIDENCIA", "DEDICACION", "ACREDITACION"]


def digest(value):
    return hashlib.sha256(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def dependencies():
    try:
        countries = {code: p.Pais.objects.get(codigo=code) for code in ("EC", "ES")}
        areas = [p.Area.objects.get(nombre=name) for name in AREAS]
        language = p.Idioma.objects.get(codigo="en")
        kind = m.TipoBeca.objects.get(nombre="Mérito académico")
        rules = {code: m.TipoRequisito.objects.get(codigo=code) for code in CODES}
    except (p.Pais.DoesNotExist, p.Area.DoesNotExist, p.Idioma.DoesNotExist, m.TipoBeca.DoesNotExist, m.TipoRequisito.DoesNotExist):
        raise CommandError("Faltan catálogos previos. No se crean ni actualizan automáticamente.") from None
    if any(rule.esquema_valor != esquema(code) for code, rule in rules.items()):
        raise CommandError("Los contratos de requisitos no coinciden con la versión vigente.")
    return countries, areas, language, kind, rules


def save(serializer, data, context=None, **assigned):
    instance = serializer(data=data, context=context or {})
    instance.is_valid(raise_exception=True)
    obj = instance.save(**assigned)
    return obj


def snapshot(user, offers, institution):
    # Exclusiones deliberadas: password y last_login cambian al habilitar/usar la
    # cuenta. Favoritos y sesiones son actividad normal, no forman el fixture.
    fields = ["id", "email", "nombre", "rol", "is_active", "is_staff", "is_superuser"]
    profile = p.Perfil.objects.get(usuario=user)
    children = {}
    for model in (p.Formacion, p.PerfilIdioma, p.PerfilArea, p.PerfilPais, p.Preferencia, p.Experiencia):
        children[model._meta.db_table] = list(model.objects.filter(perfil=profile).order_by("pk").values())
    data = []
    for offer in offers:
        row = detalle(offer)
        row.pop("estado")  # El paso del tiempo no es una modificación del fixture.
        row["clave_deduplicacion"] = offer.clave_deduplicacion
        data.append(row)
    countries, areas, language, kind, rules = dependencies()
    return digest({"usuario": Usuario.objects.filter(pk=user.pk).values(*fields).get(),
                   "grupos": list(user.groups.order_by("pk").values_list("pk", flat=True)),
                   "permisos": list(user.user_permissions.order_by("pk").values_list("pk", flat=True)),
                   "perfil": p.Perfil.objects.filter(pk=profile.pk).values().get(), "hijos": children,
                   "convocatorias": data, "institucion": s.InstitucionSerializer(institution).data,
                   "catalogos": {"paises": [(c.pk, c.codigo, c.nombre) for c in countries.values()],
                                 "areas": [(a.pk, a.nombre) for a in areas], "idioma": (language.pk, language.codigo, language.nombre),
                                 "tipo": (kind.pk, kind.nombre, kind.descripcion),
                                 "reglas": [(r.pk, r.codigo, r.esquema_valor) for r in rules.values()]}})


def verify(user, offers):
    results = []
    for (letter, _, expected), offer in zip(CASES, offers, strict=True):
        evaluation = evaluar_convocatoria(user, offer)
        actual = [o["resultado"] for o in evaluation["opciones"]]
        if actual != expected:
            raise CommandError(f"Escenario {letter}: el comparador no devuelve los resultados previstos. No se altera el motor.")
        if any(not o["verificaciones_externas_pendientes"] for o in evaluation["opciones"]):
            raise CommandError("Falta la comprobación documental externa prevista.")
        results.append({"escenario": letter, "id": offer.pk, "titulo": offer.titulo, "resultados": actual})
    return results


def existing():
    markers = list(m.Evento.objects.filter(accion=MARK))
    users = list(Usuario.objects.filter(email__iexact=EMAIL))
    offers = list(m.Convocatoria.objects.filter(Q(titulo__startswith=PREFIX) | Q(url_oficial__startswith=BASE)).order_by("id"))
    institutions = list(m.Institucion.objects.filter(Q(nombre=INSTITUTION) | Q(url_oficial=BASE)))
    if not any((markers, users, offers, institutions)):
        return None
    if len(markers) != 1 or len(users) != 1 or len(offers) != 5 or len(institutions) != 1:
        raise CommandError("Colisión o carga parcial de la demostración. No se sobrescribe ni completa automáticamente.")
    mark = markers[0]
    expected = mark.cambios.get("despues", {})
    source = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if expected.get("fuente") != source:
        raise CommandError("La definición de la demostración cambió. No se reemplazan registros previos.")
    try:
        same = expected.get("huella") == snapshot(users[0], offers, institutions[0])
    except p.Perfil.DoesNotExist:
        same = False
    if not same:
        raise CommandError("Diferencias en los datos de la demostración. No se sobrescribió ningún registro.")
    return verify(users[0], offers)


@transaction.atomic
def load(actor_id=None, preview=True):
    if connection.vendor != "postgresql":
        raise CommandError("Esta demostración se valida con PostgreSQL.")
    if not preview:
        # Serializa dos cargas concurrentes de este mismo conjunto, no otras operaciones.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [2605261105])
    deps = dependencies()
    previous = existing()
    if previous is not None:
        return {"estado": "reutilizada", "cuenta": EMAIL, "escenarios": previous}
    if preview:
        return {"estado": "vista_previa_sin_escrituras", "cuenta": EMAIL,
                "plan": "1 cuenta sin contraseña, 1 perfil, 3 formaciones, 1 idioma, 1 oferente, 5 convocatorias, 7 opciones; auditoría y relaciones asociadas.",
                "escenarios": [{"escenario": a, "titulo": PREFIX + a + " · " + b, "resultados_esperados": c} for a, b, c in CASES]}
    actor = Usuario.objects.filter(pk=actor_id, is_active=True, rol="administrador").first()
    if not actor:
        raise CommandError("La carga requiere --actor-id de un administrador activo existente; no se crean administradores.")
    countries, areas, language, kind, rules = deps
    ec, es = countries["EC"], countries["ES"]
    user = Usuario.objects.create_user(email=EMAIL, nombre=NAME, password=None)
    profile = save(ps.PerfilSerializer, dict(nacionalidad=ec.pk, residencia=ec.pk, fecha_nacimiento="1996-06-15",
        provincia_residencia="Pichincha", ciudad_residencia="Quito", dedicacion_disponible="ambas",
        disponible_traslado=True, disponible_extranjero=True), usuario=user)
    for area, title, grade, year in zip(areas, ["Ingeniería de Software", "Administración de Empresas", "Educación"], [7, 9, None], [2018, 2021, 2024], strict=True):
        save(ps.FormacionSerializer, dict(nivel="grado", carrera=title, nombre_titulo=title,
            institucion="DEMOSTRACIÓN · Instituto Superior Ficticio de Revisión", titulo_obtenido=True,
            estado_estudios="concluidos", fecha_finalizacion=f"{year}-07-01", area=area.pk,
            promedio=grade, escala_min=0 if grade is not None else None, escala_max=10 if grade is not None else None), perfil=profile)
    save(ps.IdiomaSerializer, dict(idioma=language.pk, nivel="B2"), perfil=profile)
    for area in areas:
        save(ps.AreaSerializer, dict(area=area.pk), perfil=profile)
    for country in (ec, es):
        save(ps.DestinoSerializer, dict(pais=country.pk), perfil=profile)
    save(ps.PreferenciaSerializer, dict(nivel="maestria", modalidad="virtual"), perfil=profile)
    institution = save(s.InstitucionSerializer, dict(nombre=INSTITUTION, sector="privado", pais=ec.pk, url_oficial=BASE))
    audit(actor, "demo_avances_oferente", None, s.InstitucionSerializer(institution).data, institucion=institution)
    offers = []
    for letter, title, expected in CASES:
        offer = save(s.ConvocatoriaSerializer, dict(institucion=institution.pk, tipo_beca=kind.pk,
            titulo=PREFIX + letter + " · " + title,
            descripcion=f"Oferta completamente ficticia para la revisión de avances de BecaNexo. Escenario {letter}: {title}. "
                "No es una beca real ni admite postulaciones. Bases y enlaces de example.org son ilustrativos y no se consultan externamente. "
                "Las condiciones se describen por opción; la entidad ficticia verificaría los documentos fuera de BecaNexo.",
            apertura="2026-10-20T09:00:00-05:00", fecha_publicacion="2026-10-19", cierre="2026-11-30T23:59:00-05:00",
            cierre_original="30 de noviembre de 2026, 23:59, Ecuador continental (fecha ficticia).",
            url_oficial=BASE + letter.lower(), url_bases=BASE + letter.lower() + "/bases-ficticias",
            cobertura_tipo="parcial", gastos_no_cubiertos="DEMOSTRACIÓN: transporte, alojamiento, seguros y saldo de matrícula no cubiertos.",
            obligaciones_beneficiario="DEMOSTRACIÓN: mantener matrícula y presentar informe académico semestral a la entidad ficticia.",
            areas=[a.pk for a in areas] if letter == "D" else [areas[2 if letter == "C" else 0].pk]))
        context = {"convocatoria": offer}
        def requirement(code, values, text, option=None, group=None):
            return save(s.RequisitoSerializer, dict(tipo_requisito=rules[code].pk, texto_original=text,
                valor_estructurado=values, validado=True, obligatorio=True, activo=True,
                modo_comprobacion="entidad_oferente" if code == "ACREDITACION" else "dato_declarado",
                opcion_estudio=option.pk if option else None,
                relacion_formacion="misma_formacion" if group else "independiente" if code in ("FORMACION", "TITULO_AREA", "PROMEDIO") else "pendiente",
                grupo_formacion=group, fecha_referencia="2026-11-05" if code == "EDAD" else None,
                documento_exigido="Certificación académica y de idioma, solo en la plataforma externa ficticia." if code == "ACREDITACION" else None,
                detalle_acreditacion="La entidad oferente verifica validez; BecaNexo no recibe certificados." if code == "ACREDITACION" else None,
                referencia_bases=f"Bases expresamente ficticias {letter}, sección {code}. {BASE}{letter.lower()}/bases-ficticias"), context, convocatoria=offer)
        requirement("NACIONALIDAD", {"codigos_pais": ["EC"]}, "Ciudadanía ecuatoriana declarada.")
        requirement("EDAD", {"minimo": 18, "maximo": 40}, "Entre 18 y 40 años cumplidos al 5 de noviembre de 2026.")
        requirement("RESIDENCIA", {"codigos_pais": ["EC"], "provincias": ["Pichincha"], "ciudades": ["Quito"]}, "Residencia declarada en Quito, Pichincha, Ecuador.")
        requirement("DEDICACION", {"valores_admitidos": ["parcial"]}, "Disponibilidad para estudios a tiempo parcial.")
        requirement("ACREDITACION", {"certificados_admitidos": "Certificado de idioma y expediente emitidos por entidades ficticias para este ejemplo; no son certificados válidos.", "vigencia": "La revisión documental corresponde a la entidad oferente."}, "Certificaciones externas pendientes: las coincidencias declaradas no acreditan documentos.")
        save(s.BeneficioSerializer, dict(concepto="Materiales de estudio", monto="120.00", moneda="USD", periodicidad="unico",
            detalle="Apoyo ficticio único para materiales; no incluye matrícula ni gastos de manutención."), context, convocatoria=offer)
        for index, result in enumerate(expected):
            mode = ["virtual", "presencial", "semipresencial"][index]
            area = areas[2] if result == "desconocido" else areas[0]
            option = save(s.OpcionSerializer, dict(nivel="maestria", modalidad=mode, activa=True,
                programa=f"DEMOSTRACIÓN {letter}{index + 1} · Maestría ficticia en {area.nombre}",
                institucion_destino="DEMOSTRACIÓN · Centro Universitario Ficticio de Estudios Aplicados",
                inicio_estudios="2027-03-01", duracion_meses=18, cupos=12,
                paises=[ec.pk, es.pk] if letter == "D" and index == 0 else [ec.pk]), context, convocatoria=offer)
            save(s.BeneficioSerializer, dict(opcion_estudio=option.pk, concepto="Matrícula", porcentaje=[80, 60, 50][index],
                detalle=f"Cobertura ficticia exclusiva de matrícula de la opción {letter}{index + 1}; no cubre todos los gastos."), context, convocatoria=offer)
            requirement("IDIOMA", {"codigo_idioma": "en", "nivel_minimo": "C1" if letter == "B" or (letter == "D" and index == 1) else "B2"}, "Inglés declarado según el nivel indicado; certificación por entidad oferente.", option)
            group = f"academico_{letter}_{index}"
            requirement("FORMACION", {"niveles_admitidos": ["grado"], "estado_exigido": "concluidos", "titulo_obtenido": True}, "Grado concluido con título; condiciones académicas sobre una misma formación.", option, group)
            if result == "desconocido" or letter == "E":
                required_area = areas[2] if result == "desconocido" else areas[0]
                requirement("TITULO_AREA", {"areas_admitidas": [required_area.pk]}, f"Área admitida explícita: {required_area.nombre}.", option, group)
                requirement("PROMEDIO", {"minimo": 8, "escala_min": 0, "escala_max": 10}, "Promedio mínimo 8/10 en la misma formación del área exigida; escala 0–10 según bases ficticias.", option, group)
        audit(actor, "demo_avances_crear", None, detalle(offer), convocatoria=offer)
        before = detalle(offer)
        publicar(offer)
        audit(actor, "publicar", before, detalle(offer), convocatoria=offer)
        offers.append(offer)
    results = verify(user, offers)  # Error => rollback de toda la carga, no datos a medias.
    audit(actor, MARK, None, {"fuente": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                            "huella": snapshot(user, offers, institution)}, convocatoria=offers[0])
    return {"estado": "creada", "cuenta": EMAIL, "escenarios": results}
