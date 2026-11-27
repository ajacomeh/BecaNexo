"""Genera avisos internos de «cierre próximo» para becas favoritas (y encola su correo según la regla general).

La tarea BecaNexo-Notificaciones-Gmail lo invoca como máximo una vez por hora. La última línea es un JSON con el resumen.
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from notificaciones.services import generar_avisos_cierre


class Command(BaseCommand):
    help = "Crea avisos de cierre próximo de becas favoritas; idempotente. --dry-run solo informa."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Solo informa qué avisos generaría; no escribe.")
        parser.add_argument("--dias", type=int, help=f"Ventana en días (por defecto AVISOS_CIERRE_DIAS={settings.AVISOS_CIERRE_DIAS}).")

    def handle(self, *args, **options):
        dias = options["dias"]
        if dias is not None and not 0 <= dias <= 60:
            raise CommandError("--dias debe estar entre 0 y 60.")
        resumen = generar_avisos_cierre(dias=dias, dry_run=options["dry_run"])
        detalle = resumen.pop("detalle")
        if options["dry_run"]:
            # Solo identificadores: sin nombres ni correos.
            for usuario, convocatoria, estado, texto in detalle:
                self.stdout.write(f"generaría: usuario {usuario} · convocatoria {convocatoria} · {estado} · {texto}")
            resumen["simulacion"] = True
        resumen["dias"] = settings.AVISOS_CIERRE_DIAS if dias is None else dias
        self.stdout.write(json.dumps(resumen, ensure_ascii=False))
