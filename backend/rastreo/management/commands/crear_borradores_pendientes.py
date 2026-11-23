"""Crea borradores privados automáticos para publicaciones detectadas que aún no tienen uno.

Idempotente: omite publicaciones con borrador o con convocatoria vinculada (incluidos los borradores que el
administrador descartó, que siguen existiendo como descartados). No modifica borradores, publicaciones ni
versiones existentes; cada borrador nuevo se crea con la última versión observada y la misma regla que la
captura (prepare_automatic_draft). Por defecto simula dentro de una transacción revertida; con --aplicar guarda.
No contacta con fuentes externas, no publica ni envía avisos.
"""
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from rastreo.auto_borradores import latest_version, prepare_automatic_draft
from rastreo.models import Publicacion


class _Revertir(Exception):
    pass


class Command(BaseCommand):
    help = 'Crea borradores privados para publicaciones detectadas sin borrador (simulación por defecto).'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true', help='Guarda los borradores; sin esta opción solo simula.')

    def handle(self, *args, **options):
        informe = {'modo': 'aplicar' if options['aplicar'] else 'simulacion', 'creados': [], 'sin_borrador': [], 'omitidas': 0}
        try:
            with transaction.atomic():
                for publication in Publicacion.objects.select_related('fuente').order_by('pk'):
                    if publication.convocatoria_id or hasattr(publication, 'borrador_automatico'):
                        informe['omitidas'] += 1
                        continue
                    version = latest_version(publication)
                    if version is None:
                        informe['sin_borrador'].append({'publicacion_id': publication.pk, 'motivo': 'Sin versión conservada.'})
                        continue
                    origin, created, motivo = prepare_automatic_draft(publication.pk, version.pk)
                    if created:
                        informe['creados'].append({'publicacion_id': publication.pk, 'convocatoria_id': origin.convocatoria_id,
                                                   'oferente_no_ecuatoriano': bool(origin.datos_iniciales.get('oferente_no_ecuatoriano')),
                                                   'oferente_detectado': origin.datos_iniciales.get('oferente_detectado') or None})
                    else:
                        informe['sin_borrador'].append({'publicacion_id': publication.pk, 'motivo': motivo})
                if not options['aplicar']:
                    raise _Revertir()
        except _Revertir:
            pass
        informe['total_creados'] = len(informe['creados'])
        self.stdout.write(json.dumps(informe, ensure_ascii=False, indent=2, default=str))
