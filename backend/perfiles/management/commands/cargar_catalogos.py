import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from perfiles.models import Pais, Idioma, Area


IDIOMAS = [
    ("es", "Español"), ("en", "Inglés"), ("fr", "Francés"), ("de", "Alemán"),
    ("pt", "Portugués"), ("it", "Italiano"), ("zh", "Chino"), ("ja", "Japonés"),
    ("ko", "Coreano"), ("ar", "Árabe"), ("qu", "Quechua"), ("jiv", "Shuar"),
]
AREAS = [
    "Programas y certificaciones genéricos", "Educación", "Artes y humanidades",
    "Ciencias sociales, periodismo e información", "Administración de empresas y derecho",
    "Ciencias naturales, matemáticas y estadística", "Tecnologías de la información y la comunicación",
    "Ingeniería, industria y construcción", "Agricultura, silvicultura, pesca y veterinaria",
    "Salud y bienestar", "Servicios",
]


class Command(BaseCommand):
    help = "Carga catálogos iniciales idempotentes, sin borrar registros existentes."

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(__file__).resolve().parents[2] / "data" / "paises.json"
        for row in json.loads(path.read_text(encoding="utf-8")):
            Pais.objects.update_or_create(codigo=row["codigo"], defaults={"nombre": row["nombre"]})
        for codigo, nombre in IDIOMAS:
            Idioma.objects.update_or_create(codigo=codigo, defaults={"nombre": nombre})
        for nombre in AREAS:
            Area.objects.get_or_create(nombre=nombre)
        self.stdout.write(self.style.SUCCESS("Carga completada: 249 países/territorios, 12 idiomas y 11 áreas base. Sin borrados."))
