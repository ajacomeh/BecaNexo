import json
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.db.models import Q
from django.utils import timezone
from rastreo.models import Fuente, Ejecucion, Publicacion, Version, VersionDocumento, Observacion
from rastreo.observaciones import differences
from rastreo.services import configure, enable_discovery, enable_national_discovery, revert_national_discovery, set_paginated_discovery, set_frequency, run_manual, run_candidate, run_scheduled, next_due, recover, summary, register_portal, register_generic_portal, verify_generic_access, set_portal_active
from rastreo.storage import integrity_report, StorageError


class Command(BaseCommand):
    help = 'Rastreo local de confianza: configurar, activar, desactivar, ejecutar, resumen, recuperar, integridad.'

    def add_arguments(self, parser):
        parser.add_argument('accion', choices=['configurar', 'activar', 'desactivar', 'registrar-portal', 'registrar-portal-generico', 'verificar-portal-generico', 'activar-portal', 'desactivar-portal', 'habilitar-descubrimiento', 'habilitar-nacionales', 'revertir-nacionales', 'habilitar-paginacion', 'revertir-paginacion', 'configurar-frecuencia', 'ejecutar', 'procesar-candidato', 'programado', 'estado-programacion', 'resumen', 'recuperar', 'integridad', 'publicaciones', 'versiones', 'documentos', 'observaciones', 'diferencias'])
        parser.add_argument('--actor-id', type=int)
        parser.add_argument('--motivo')
        parser.add_argument('--clave', help='UUID idempotente; obligatorio al ejecutar.')
        parser.add_argument('--fuente-id', type=int)
        parser.add_argument('--candidato-id', type=int)
        parser.add_argument('--ejecucion-id', type=int)
        parser.add_argument('--publicacion-id', type=int)
        parser.add_argument('--version-id', type=int)
        parser.add_argument('--otra-version-id', type=int)
        parser.add_argument('--frecuencia-min', type=int)
        parser.add_argument('--portal', choices=['utpl', 'ups'])
        parser.add_argument('--nombre')
        parser.add_argument('--indice')
        parser.add_argument('--host')
        parser.add_argument('--max-paginas', type=int, default=8)
        parser.add_argument('--max-profundidad', type=int, default=2)
        parser.add_argument('--max-fichas', type=int, default=8)
        parser.add_argument('--acceso-verificado', action='store_true', help='Solo tras verificar condiciones públicas y robots.txt; queda auditado en el motivo.')

    def handle(self, *args, **options):
        action = options['accion']
        try:
            if action == 'registrar-portal':
                source, changed = register_portal(options['actor_id'], options['portal'], options['motivo'], options['clave'])
                result = {'fuente_id': source.pk, 'activa': source.activa, 'politica_version': source.politica_version, 'cambio': changed}
            elif action == 'registrar-portal-generico':
                source, changed = register_generic_portal(options['actor_id'], options['nombre'], options['indice'],
                    options['host'], options['motivo'], max_pages=options['max_paginas'],
                    max_depth=options['max_profundidad'], max_cards=options['max_fichas'],
                    access_verified=options['acceso_verificado'], key=options['clave'])
                result = {'fuente_id': source.pk, 'activa': False, 'politica_version': source.politica_version, 'cambio': changed}
            elif action == 'verificar-portal-generico':
                source, changed = verify_generic_access(options['fuente_id'], options['actor_id'], options['motivo'], options['clave'])
                result = {'fuente_id': source.pk, 'activa': source.activa, 'acceso_verificado': source.politica_acceso['acceso_verificado'], 'cambio': changed}
            elif action in ('activar-portal', 'desactivar-portal'):
                source, changed = set_portal_active(options['fuente_id'], options['actor_id'], options['motivo'], action == 'activar-portal', options['clave'])
                result = {'fuente_id': source.pk, 'activa': source.activa, 'politica_version': source.politica_version, 'cambio': changed}
            elif action in ['configurar', 'activar', 'desactivar']:
                source, changed = configure(options['actor_id'], options['motivo'],
                    active=None if action == 'configurar' else action == 'activar', key=options['clave'])
                result = {'fuente_id': source.pk, 'activa': source.activa, 'aprobada_publicacion_automatica': False, 'cambio': changed}
            elif action == 'habilitar-descubrimiento':
                source, changed = enable_discovery(options['actor_id'], options['motivo'], options['clave'])
                result = {'fuente_id': source.pk, 'politica_version': source.politica_version, 'cambio': changed}
            elif action == 'habilitar-nacionales':
                source, changed = enable_national_discovery(options['actor_id'], options['motivo'], options['clave'])
                result = {'fuente_id': source.pk, 'politica_version': source.politica_version, 'cambio': changed}
            elif action == 'revertir-nacionales':
                source, changed = revert_national_discovery(options['actor_id'], options['motivo'], options['clave'])
                result = {'fuente_id': source.pk, 'politica_version': source.politica_version, 'cambio': changed}
            elif action in ('habilitar-paginacion', 'revertir-paginacion'):
                source, changed = set_paginated_discovery(options['actor_id'], options['motivo'],
                                                          action == 'habilitar-paginacion', options['clave'])
                result = {'fuente_id': source.pk, 'politica_version': source.politica_version, 'cambio': changed}
            elif action == 'configurar-frecuencia':
                source, changed = set_frequency(options['fuente_id'], options['actor_id'], options['motivo'], options['frecuencia_min'], options['clave'])
                result = {'fuente_id': source.pk, 'frecuencia_min': source.frecuencia_min, 'cambio': changed}
            elif action == 'ejecutar':
                if not options['clave'] or not options['fuente_id']:
                    raise ValidationError('--clave UUID y --fuente-id obligatorios.')
                result = summary(run_manual(options['fuente_id'], options['actor_id'], options['clave']))
            elif action == 'procesar-candidato':
                if not options['candidato_id'] or not options['actor_id'] or not options['clave'] or not options['motivo']:
                    raise ValidationError('--candidato-id, --actor-id, --clave UUID y --motivo obligatorios.')
                result = summary(run_candidate(options['candidato_id'], options['actor_id'], options['clave'], options['motivo']))
            elif action == 'programado':
                if options['actor_id'] or options['clave']:
                    raise ValidationError('La ejecución programada no admite actor ni clave manual.')
                sources = Fuente.objects.filter(Q(adaptador='siau') | Q(adaptador__startswith='portal_ec:'), activa=True).order_by('id')
                if options['fuente_id']:
                    sources = sources.filter(pk=options['fuente_id'])
                result = []
                for source in sources:
                    due = next_due(source)
                    if due and due > timezone.now():
                        result.append({'fuente_id': source.pk, 'estado': 'no_corresponde_aun', 'proxima_ejecucion': due})
                    else:
                        result.append(summary(run_scheduled(source.pk)))
            elif action == 'estado-programacion':
                if not options['fuente_id'] or options['actor_id'] or options['clave']:
                    raise ValidationError('Indica solo --fuente-id para consultar la programación.')
                source = Fuente.objects.get(pk=options['fuente_id'])
                last = Ejecucion.objects.filter(fuente=source).exclude(estado='omitida').order_by('-inicio').first()
                with connection.cursor() as cursor:
                    cursor.execute('SELECT current_database()')
                    database = cursor.fetchone()[0]
                result = {'base': database, 'fuente_id': source.pk, 'activa': source.activa,
                          'politica_version': source.politica_version, 'frecuencia_min': source.frecuencia_min,
                          'aprobada_publicacion_automatica': source.aprobada_publicacion_automatica,
                          'ejecuciones_en_curso': Ejecucion.objects.filter(fuente=source, estado='en_curso').count(),
                          'ultima_ejecucion': {'id': last.pk, 'estado': last.estado, 'inicio': last.inicio} if last else None,
                          'proxima_ejecucion': next_due(source)}
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
