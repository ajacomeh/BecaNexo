from django.core.management.base import BaseCommand
from django.db import transaction
from convocatorias.models import TipoBeca, TipoRequisito
from convocatorias.reglas import CONTRATOS, esquema


class Command(BaseCommand):
    help = "Carga idempotente de clasificaciones y contratos vigentes; no crea ni reinterpreta ofertas."

    @transaction.atomic
    def handle(self, *args, **options):
        # Clasificaciones ilustradas en el diseño. No son una taxonomía legal ni se infieren del título.
        for nombre in ("Mérito académico", "Investigación"):
            TipoBeca.objects.get_or_create(nombre=nombre)
        for codigo, (nombre, _, _) in CONTRATOS.items():
            TipoRequisito.objects.update_or_create(codigo=codigo, defaults={"nombre": nombre, "esquema_valor": esquema(codigo)})
        self.stdout.write(self.style.SUCCESS("Catálogos de convocatorias preparados; no se crearon ofertas."))
