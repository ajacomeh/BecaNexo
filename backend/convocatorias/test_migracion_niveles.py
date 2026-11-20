"""Migración 0012: amplía el catálogo de niveles de las opciones de estudio. Solo en la base de pruebas."""
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from perfiles.models import NIVELES

NUEVOS = ('tecnico_superior', 'tecnologico_superior', 'maestria_tecnologica')


class MigracionNivelesOpcionesTests(TransactionTestCase):
    antes = [('convocatorias', '0011_alcance_academico')]
    despues = [('convocatorias', '0012_opcion_niveles_tecnicos')]

    def apps(self, target):
        return MigrationExecutor(connection).loader.project_state(target).apps

    def test_amplia_el_catalogo_sin_tocar_los_datos_y_es_reversible(self):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        try:
            MigrationExecutor(connection).migrate(self.antes)
            apps = self.apps(self.antes)
            offer = apps.get_model('convocatorias', 'Convocatoria').objects.create(
                titulo='Migración de niveles', clave_deduplicacion='m' * 64)
            option = apps.get_model('convocatorias', 'OpcionEstudio')
            option.objects.create(convocatoria=offer, nivel='grado', modalidad='presencial')
            option.objects.create(convocatoria=offer, nivel='no_aplica', modalidad='hibrida')
            # Antes de la migración, la base rechaza los niveles nuevos.
            with self.assertRaises(IntegrityError), transaction.atomic():
                option.objects.create(convocatoria=offer, nivel='maestria_tecnologica', modalidad='virtual')

            MigrationExecutor(connection).migrate(self.despues)
            option = self.apps(self.despues).get_model('convocatorias', 'OpcionEstudio')
            for level in NUEVOS:
                option.objects.create(convocatoria_id=offer.pk, nivel=level, modalidad='virtual')
            # Los valores que no pertenecen al catálogo siguen rechazados.
            with self.assertRaises(IntegrityError), transaction.atomic():
                option.objects.create(convocatoria_id=offer.pk, nivel='posgrado', modalidad='virtual')
            self.assertEqual(sorted(option.objects.values_list('nivel', flat=True)),
                             sorted(['grado', 'no_aplica', *NUEVOS]))
            # Los datos anteriores se conservaron sin cambios.
            self.assertEqual(option.objects.filter(nivel__in=['grado', 'no_aplica']).count(), 2)

            # Reversa: con una opción de nivel nuevo la restricción anterior no puede restablecerse; se elimina primero.
            option.objects.filter(nivel__in=NUEVOS).delete()
            MigrationExecutor(connection).migrate(self.antes)
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.apps(self.antes).get_model('convocatorias', 'OpcionEstudio').objects.create(
                    convocatoria_id=offer.pk, nivel='tecnico_superior', modalidad='virtual')
        finally:
            # La base de pruebas debe quedar siempre en el esquema final.
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())


class CatalogoNivelesTests(TestCase):
    def test_solo_las_opciones_de_estudio_admiten_los_niveles_nuevos(self):
        levels = [row['valor'] for row in APIClient().get('/api/becas/catalogos/').data['niveles_opcion']]
        self.assertEqual(levels, ['bachillerato', 'grado', 'especializacion', 'maestria', 'doctorado',
                                  *NUEVOS, 'no_aplica'])
        # Los perfiles y las preferencias de postulantes conservan su catálogo.
        self.assertFalse(set(NUEVOS) & {value for value, _label in NIVELES})
