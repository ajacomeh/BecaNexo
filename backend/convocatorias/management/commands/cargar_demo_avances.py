import json
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from rest_framework.exceptions import ValidationError
from convocatorias.demo_avances import load


class Command(BaseCommand):
    help = "Vista previa por defecto; --aplicar crea la demostración sin sobrescribir datos."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--vista-previa", action="store_true")
        mode.add_argument("--aplicar", action="store_true")
        parser.add_argument("--actor-id", type=int, help="Administrador activo existente, autor de la carga y publicación.")

    def handle(self, *args, **options):
        try:
            result = load(actor_id=options["actor_id"], preview=not options["aplicar"])
        except (IntegrityError, ValidationError) as exc:
            raise CommandError("La carga no superó integridad o validación. Transacción revertida; revisar el comando en pruebas.") from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
