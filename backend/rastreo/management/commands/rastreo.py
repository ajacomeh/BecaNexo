import json
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from rastreo.models import Fuente, Ejecucion, Publicacion, Version, VersionDocumento, Observacion
from rastreo.observaciones import differences
from rastreo.services import configure, enable_discovery, set_frequency, run_manual, run_scheduled, next_due, recover, summary
from rastreo.storage import integrity_report, StorageError


class Command(BaseCommand):
    help = 'Rastreo local de confianza: configurar, activar, desactivar, ejecutar, resumen, recuperar, integridad.'

    def add_arguments(self, parser):
        parser.add_argument('accion', choices=['configurar', 'activar', 'desactivar', 'habilitar-descubrimiento', 'configurar-frecuencia', 'ejecutar', 'programado', 'resumen', 'recuperar', 'integridad', 'publicaciones', 'versiones', 'documentos', 'observaciones', 'diferencias'])
        parser.add_argument('--actor-id', type=int)
        parser.add_argument('--motivo')
        parser.add_argument('--clave', help='UUID idempotente; obligatorio al ejecutar.')
        parser.add_argument('--fuente-id', type=int)
        parser.add_argument('--ejecucion-id', type=int)
        parser.add_argument('--publicacion-id', type=int)
        parser.add_argument('--version-id', type=int)
        parser.add_argument('--otra-version-id', type=int)
        parser.add_argument('--frecuencia-min', type=int)

    def handle(self, *args, **options):
        action = options['accion']
        try:
            if action in ['configurar', 'activar', 'desactivar']:
                source, changed = configure(options['actor_id'], options['motivo'],
                    active=None if action == 'configurar' else action == 'activar', key=options['clave'])
                result = {'fuente_id': source.pk, 'activa': source.activa, 'aprobada_publicacion_automatica': False, 'cambio': changed}
            elif action == 'habilitar-descubrimiento':
                source, changed = enable_discovery(options['actor_id'], options['motivo'], options['clave'])
                result = {'fuente_id': source.pk, 'politica_version': source.politica_version, 'cambio': changed}
            elif action == 'configurar-frecuencia':
                source, changed = set_frequency(options['fuente_id'], options['actor_id'], options['motivo'], options['frecuencia_min'], options['clave'])
                result = {'fuente_id': source.pk, 'frecuencia_min': source.frecuencia_min, 'cambio': changed}
            elif action == 'ejecutar':
                if not options['clave'] or not options['fuente_id']:
                    raise ValidationError('--clave UUID y --fuente-id obligatorios.')
                result = summary(run_manual(options['fuente_id'], options['actor_id'], options['clave']))
            elif action == 'programado':
                if options['actor_id'] or options['clave']:
                    raise ValidationError('La ejecución programada no admite actor ni clave manual.')
                sources = Fuente.objects.filter(adaptador='siau', activa=True).order_by('id')
                if options['fuente_id']:
                    sources = sources.filter(pk=options['fuente_id'])
                result = []
                for source in sources:
                    due = next_due(source)
                    if due and due > timezone.now():
                        result.append({'fuente_id': source.pk, 'estado': 'no_corresponde_aun', 'proxima_ejecucion': due})
                    else:
                        result.append(summary(run_scheduled(source.pk)))
            elif action == 'resumen':
                result = summary(Ejecucion.objects.get(pk=options['ejecucion_id']))
            elif action == 'recuperar':
                result = {'recuperadas': recover(options['fuente_id'], options['actor_id'], options['motivo'])}
            elif action == 'publicaciones':
                if not options['fuente_id']:
                    raise ValidationError('--fuente-id obligatorio.')
                Fuente.objects.get(pk=options['fuente_id'])
                result = list(Publicacion.objects.filter(fuente_id=options['fuente_id']).order_by('id').values())
            elif action == 'versiones':
                publication = Publicacion.objects.get(pk=options['publicacion_id'])
                result = list(publication.versiones.order_by('numero').values('id', 'numero', 'creada_en', 'version_extractor', 'version_normalizador', 'version_contrato', 'hash_manifiesto', 'hash_contenido_relevante', 'estado_extraccion', 'advertencias', 'manifiesto'))
            elif action == 'documentos':
                version = Version.objects.get(pk=options['version_id'])
                result = list(VersionDocumento.objects.filter(version=version).order_by('id').values('id', 'rol', 'url_original', 'url_normalizada', 'documento_id', 'documento__sha256', 'documento__mime', 'documento__tamano_bytes', 'documento__clave_almacenamiento'))
            elif action == 'observaciones':
                execution = Ejecucion.objects.get(pk=options['ejecucion_id'])
                result = list(Observacion.objects.filter(ejecucion=execution).order_by('id').values())
            elif action == 'diferencias':
                result = differences(Version.objects.get(pk=options['version_id']), Version.objects.get(pk=options['otra_version_id']))
            else:
                result = integrity_report()
        except (ValidationError, ObjectDoesNotExist, ValueError, StorageError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, cls=DjangoJSONEncoder))
