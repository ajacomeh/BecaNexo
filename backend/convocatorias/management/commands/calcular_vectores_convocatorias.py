"""Rellena o recalcula los vectores semánticos de las convocatorias públicas («Becas similares»). Idempotente."""
import time

from django.core.management.base import BaseCommand

from convocatorias import models as m
from convocatorias.recomendaciones import texto_convocatoria
from convocatorias.semantica import ModeloNoDisponible
from convocatorias.services import publicas
from convocatorias.vectores import VERSION_MODELO, guardar_vector, hash_texto


class Command(BaseCommand):
    help = "Calcula los vectores que faltan o cambiaron (texto o modelo) de las convocatorias públicas."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Solo informa qué calcularía; no escribe.")
        parser.add_argument("--forzar", action="store_true", help="Recalcula todos, aunque estén al día.")

    def handle(self, *args, **options):
        inicio = time.perf_counter()
        resumen = {"calculadas": 0, "al_dia": 0, "fallidas": 0}
        guardados = {v.convocatoria_id: v for v in m.VectorConvocatoria.objects.all()}
        for convocatoria in publicas().order_by("id"):
            if options["dry_run"]:
                actual = guardados.get(convocatoria.pk)
                al_dia = (not options["forzar"] and actual is not None and actual.version_modelo == VERSION_MODELO
                          and actual.hash_texto == hash_texto(texto_convocatoria(convocatoria)))
                resumen["al_dia" if al_dia else "calculadas"] += 1
                if not al_dia:
                    self.stdout.write(f"calcularía #{convocatoria.pk} ({'nuevo' if actual is None else 'cambió'})")
                continue
            try:
                resumen["calculadas" if guardar_vector(convocatoria, forzar=options["forzar"]) == "calculado" else "al_dia"] += 1
            except ModeloNoDisponible as exc:
                resumen["fallidas"] += 1
                self.stderr.write(f"#{convocatoria.pk}: {exc}")
        resumen["segundos"] = round(time.perf_counter() - inicio, 2)
        prefijo = "simulación (sin escribir): " if options["dry_run"] else ""
        self.stdout.write(prefijo + str(resumen))
