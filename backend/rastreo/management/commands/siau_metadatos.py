"""Consulta limitada del índice SIAU; requiere autorización operativa separada."""
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import connection

from rastreo.siau_metadatos import capturar_metadatos
from rastreo.models import CandidatoIndice


class Command(BaseCommand):
    help = 'Captura solo metadatos factuales del índice SIAU, sin fichas ni PDF.'

    def add_arguments(self, parser):
        parser.add_argument('--fuente-id', type=int, required=True)
        parser.add_argument('--actor-id', type=int, required=True)
        parser.add_argument('--clave', required=True, help='UUID idempotente')
        parser.add_argument('--motivo', required=True)

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT current_database()')
                if cursor.fetchone()[0] != 'becanexo_db':
                    raise CommandError('La captura operativa exige la base de desarrollo verificada.')
            key = uuid.UUID(options['clave'])
            execution = capturar_metadatos(options['fuente_id'], options['actor_id'], key, options['motivo'])
        except (ValidationError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f'ejecucion={execution.pk} estado={execution.estado} '
                          f'candidatos={CandidatoIndice.objects.filter(ultima_ejecucion=execution).count()} '
                          'fichas=0 documentos=0 borradores=0')
