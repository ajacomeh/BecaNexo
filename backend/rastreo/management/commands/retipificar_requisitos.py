"""Retipifica requisitos de borradores automáticos con el extractor vigente (simulación por defecto).

Solo modifica requisitos que creó el llenado automático, que el administrador no editó (la huella de
contenido del libro coincide), que no están validados, en convocatorias que no están publicadas.
Para todo lo demás (publicadas, manuales, editados o validados) solo informa de lo que cambiaría.
Con --aplicar exige --actor-id (administrador) y registra un Evento de auditoría por convocatoria.
No contacta con fuentes externas, no publica, no valida ni envía notificaciones.
"""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from convocatorias.models import BorradorRastreo, Convocatoria
from convocatorias.services import audit, detalle, touch
from rastreo.llenado import contenido_de_requisito
from rastreo.tipificacion import aplicar, propuesta


class _Revertir(Exception):
    pass


class Command(BaseCommand):
    help = 'Retipifica requisitos creados por el llenado automático (simulación por defecto).'

    def add_arguments(self, parser):
        parser.add_argument('--convocatoria', type=int, action='append', default=[], required=True, help='ID de convocatoria; repetible.')
        parser.add_argument('--aplicar', action='store_true', help='Guarda los cambios; sin esta opción solo simula.')
        parser.add_argument('--actor-id', type=int, help='Administrador que firma la auditoría (obligatorio con --aplicar).')

    def handle(self, *args, **options):
        actor = None
        if options['aplicar']:
            if not options['actor_id']:
                raise CommandError('--actor-id es obligatorio con --aplicar.')
            actor = get_user_model().objects.filter(pk=options['actor_id'], rol='administrador', is_active=True).first()
            if actor is None:
                raise CommandError('El actor debe ser un administrador activo.')
        informe = []
        for pk in sorted(set(options['convocatoria'])):
            oferta = Convocatoria.objects.filter(pk=pk).first()
            if oferta is None:
                informe.append({'convocatoria_id': pk, 'omitido': 'No existe.'})
                continue
            try:
                with transaction.atomic():
                    informe.append(self._una(oferta, actor))
                    if not options['aplicar']:
                        raise _Revertir()
            except _Revertir:
                pass
        self.stdout.write(json.dumps({'modo': 'aplicar' if options['aplicar'] else 'simulacion', 'convocatorias': informe},
                                     ensure_ascii=False, indent=2, default=str))

    def _una(self, oferta, actor):
        origen = BorradorRastreo.objects.filter(convocatoria=oferta).first()
        libro = dict((origen.datos_iniciales or {}).get('llenado_automatico') or {}) if origen else {}
        entradas = {r['id']: r for r in libro.get('registros', []) if r['modelo'] == 'requisitos'}
        publicada = oferta.revision == 'validada'
        antes = detalle(oferta)
        cambiados, solo_informe = [], []
        for requisito in oferta.requisitos.select_related('tipo_requisito').order_by('pk'):
            cambio = propuesta(requisito)
            if not cambio:
                continue
            fila = {'id': requisito.pk, 'texto': requisito.texto_original[:160], 'de': requisito.tipo_requisito.codigo,
                    'a': cambio['codigo'], 'valor': cambio['valor']}
            entrada = entradas.get(requisito.pk)
            motivo = ('Convocatoria publicada: solo informe.' if publicada
                      else 'Requisito creado o tipificado a mano: solo informe.' if entrada is None
                      else 'El administrador lo editó después del llenado: solo informe.' if entrada.get('contenido') != contenido_de_requisito(requisito)
                      else 'Requisito validado: solo informe.' if requisito.validado else None)
            if motivo:
                solo_informe.append({**fila, 'motivo': motivo})
                continue
            error = aplicar(requisito, cambio, oferta)
            if error:
                solo_informe.append({**fila, 'motivo': error})
                continue
            requisito.refresh_from_db()
            entrada['contenido'] = contenido_de_requisito(requisito)
            entrada.setdefault('retipificaciones', []).append({'de': fila['de'], 'a': fila['a'], 'fecha': timezone.now().isoformat(),
                                                               'metodo': cambio['metodo']})
            cambiados.append(fila)
        if cambiados:
            origen.datos_iniciales = {**origen.datos_iniciales, 'llenado_automatico': libro}
            origen.save(update_fields=['datos_iniciales'])
            oferta.refresh_from_db()
            touch(oferta)
            if actor is not None:
                audit(actor, 'requisitos_retipificar', antes, detalle(oferta), convocatoria=oferta)
        return {'convocatoria_id': oferta.pk, 'publicada': publicada, 'cambiados': cambiados, 'solo_informe': solo_informe}
