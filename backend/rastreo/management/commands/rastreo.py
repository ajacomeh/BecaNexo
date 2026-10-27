import json
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from rastreo.models import Fuente, Ejecucion
from rastreo.services import configure, run_manual, recover, summary
from rastreo.storage import integrity_report, StorageError


class Command(BaseCommand):
    help = 'Rastreo local de confianza: configurar, activar, desactivar, ejecutar, resumen, recuperar, integridad.'

    def add_arguments(self, parser):
        parser.add_argument('accion', choices=['configurar', 'activar', 'desactivar', 'ejecutar', 'resumen', 'recuperar', 'integridad'])
        parser.add_argument('--actor-id', type=int)
        parser.add_argument('--motivo')
        parser.add_argument('--clave', help='UUID idempotente; obligatorio al ejecutar.')
        parser.add_argument('--fuente-id', type=int)
        parser.add_argument('--ejecucion-id', type=int)

    def handle(self, *args, **options):
        action = options['accion']
        try:
            if action in ['configurar', 'activar', 'desactivar']:
                source, changed = configure(options['actor_id'], options['motivo'],
                    active=None if action == 'configurar' else action == 'activar', key=options['clave'])
                result = {'fuente_id': source.pk, 'activa': source.activa, 'aprobada_publicacion_automatica': False, 'cambio': changed}
            elif action == 'ejecutar':
                if not options['clave'] or not options['fuente_id']:
                    raise ValidationError('--clave UUID y --fuente-id obligatorios.')
                result = summary(run_manual(options['fuente_id'], options['actor_id'], options['clave']))
            elif action == 'resumen':
                result = summary(Ejecucion.objects.get(pk=options['ejecucion_id']))
            elif action == 'recuperar':
                result = {'recuperadas': recover(options['fuente_id'], options['actor_id'], options['motivo'])}
            else:
                result = integrity_report()
        except (ValidationError, ObjectDoesNotExist, ValueError, StorageError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
