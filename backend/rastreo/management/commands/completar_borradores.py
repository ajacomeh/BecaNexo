"""Completa borradores automáticos existentes con el llenado automático.

Por defecto es una simulación: ejecuta el llenado dentro de una transacción que se revierte y
muestra qué campos y registros se escribirían. Con --aplicar guarda los cambios.
No contacta con fuentes externas, no publica, no valida ni envía notificaciones.
"""
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from convocatorias.models import BorradorRastreo
from convocatorias.services import errores_publicacion
from rastreo.auto_borradores import latest_version, materially_changed, review_baseline, version_confirmed
from rastreo.llenado import llenar_origen


class _Revertir(Exception):
    pass


class Command(BaseCommand):
    help = 'Completa borradores automáticos con el llenado automático (simulación por defecto).'

    def add_arguments(self, parser):
        parser.add_argument('--convocatoria', type=int, action='append', default=[], help='ID de convocatoria; repetible.')
        parser.add_argument('--aplicar', action='store_true', help='Guarda los cambios; sin esta opción solo simula.')

    def handle(self, *args, **options):
        origenes = BorradorRastreo.objects.select_related('convocatoria', 'publicacion', 'version').order_by('convocatoria_id')
        if options['convocatoria']:
            origenes = origenes.filter(convocatoria_id__in=options['convocatoria'])
        informe = []
        for origen in origenes:
            informe.append(self._uno(origen, options['aplicar']))
        self.stdout.write(json.dumps({'modo': 'aplicar' if options['aplicar'] else 'simulacion', 'borradores': informe},
                                     ensure_ascii=False, indent=2, default=str))

    def _uno(self, origen, aplicar):
        oferta = origen.convocatoria
        item = {'convocatoria_id': oferta.pk, 'publicacion_id': origen.publicacion_id}
        if oferta.revision == 'validada':
            return {**item, 'omitido': 'La convocatoria ya está validada.'}
        actual = latest_version(origen.publicacion)
        if actual and materially_changed(review_baseline(origen, oferta), actual) and not version_confirmed(oferta, actual):
            return {**item, 'omitido': 'Hay una versión posterior con cambios relevantes sin confirmar.'}
        item['pendientes_antes'] = errores_publicacion(oferta, estricto=False)
        try:
            with transaction.atomic():
                resumen = llenar_origen(origen, actual or origen.version, tocar=aplicar)
                item['campos'] = resumen['campos']
                item['creados'] = resumen['creados']
                item['omitidos'] = resumen['omitidos']
                item['error'] = resumen['error']
                oferta.refresh_from_db()
                item['pendientes_despues'] = errores_publicacion(oferta, estricto=False)
                if not aplicar:
                    raise _Revertir()
        except _Revertir:
            pass
        return item
