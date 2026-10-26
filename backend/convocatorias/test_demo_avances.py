from io import StringIO
from secrets import token_urlsafe
from unittest.mock import patch
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient
from usuarios.models import Usuario
from perfiles.models import Formacion
from . import models as m
from .demo_avances import load, EMAIL, PREFIX, CASES, MARK, snapshot
from .comparacion import evaluar_convocatoria


class DemoAvancesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        if settings.DATABASES['default']['NAME'] != 'test_becanexo_db':
            raise RuntimeError('Estas pruebas requieren test_becanexo_db.')
        call_command('cargar_catalogos', stdout=StringIO())
        call_command('cargar_catalogos_convocatorias', stdout=StringIO())
        cls.actor = Usuario.objects.create_user(email='actor-fixture@example.com', nombre='Actor sintético', rol='administrador')

    def create(self):
        result = load(self.actor.pk, preview=False)
        self.user = Usuario.objects.get(email=EMAIL)
        self.offers = list(m.Convocatoria.objects.filter(titulo__startswith=PREFIX).order_by('pk'))
        return result

    def test_preview_no_writes_and_command(self):
        with CaptureQueriesContext(connection) as queries:
            call_command('cargar_demo_avances', vista_previa=True, stdout=StringIO())
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertFalse(Usuario.objects.filter(email=EMAIL).exists())
        self.assertEqual(m.Convocatoria.objects.count(), 0)

    def test_all_cases_real_engine_and_external_documents(self):
        self.create()
        self.assertFalse(self.user.has_usable_password())
        self.assertFalse(self.user.is_staff)
        self.assertEqual(self.user.rol, 'postulante')
        for (_, _, expected), offer in zip(CASES, self.offers, strict=True):
            response = evaluar_convocatoria(self.user, offer)
            self.assertEqual([o['resultado'] for o in response['opciones']], expected)
            self.assertTrue(all(o['verificaciones_externas_pendientes'] > 0 for o in response['opciones']))
        self.assertEqual(m.OpcionEstudio.objects.count(), 7)
        self.assertEqual(Formacion.objects.filter(perfil=self.user.perfil).count(), 3)
        self.assertEqual(m.Evento.objects.filter(accion='publicar').count(), 5)

    def test_education_missing_average_not_resolved_by_other_degrees(self):
        self.create()
        education = self.user.perfil.formaciones.get(carrera='Educación')
        self.assertIsNone(education.promedio)
        self.assertIsNone(education.escala_min)
        self.assertIsNone(education.escala_max)
        for offer in [self.offers[2], self.offers[3]]:
            results = evaluar_convocatoria(self.user, offer)['opciones']
            self.assertEqual(results[-1]['resultado'], 'desconocido')
            rules = results[-1]['requisitos']
            self.assertTrue(any(r['tipo'] == 'PROMEDIO' and r['resultado'] == 'desconocido' for r in rules))

    def test_same_formation_group_cannot_mix_tic_and_administration(self):
        self.create()
        option = evaluar_convocatoria(self.user, self.offers[4])['opciones'][0]
        self.assertEqual(option['resultado'], 'no_cumple')
        grouped = [r for r in option['requisitos'] if r['tipo'] in ('FORMACION', 'TITULO_AREA', 'PROMEDIO')]
        self.assertEqual(len(grouped), 3)
        self.assertTrue(all(r['resultado'] == 'no_cumple' for r in grouped))
        self.assertTrue(all('conjuntamente' in r['explicacion'] for r in grouped))

    def test_idempotence_password_and_session_do_not_block_reuse(self):
        self.create()
        count = m.Evento.objects.count()
        # Contraseña exclusiva del test, nunca usada ni creada en desarrollo.
        self.user.set_password(token_urlsafe(32))
        self.user.last_login = timezone.now()
        self.user.save(update_fields=['password', 'last_login'])
        with CaptureQueriesContext(connection) as queries:
            result = load(self.actor.pk, preview=False)
        self.assertEqual(result['estado'], 'reutilizada')
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertEqual(m.Evento.objects.count(), count)
        self.assertEqual(m.Convocatoria.objects.count(), 5)

    def test_collision_account_rejected_without_touching_existing(self):
        account = Usuario.objects.create_user(email=EMAIL, nombre='Cuenta previa que no se debe tocar')
        with self.assertRaises(CommandError):
            load(self.actor.pk, preview=False)
        account.refresh_from_db()
        self.assertEqual(account.nombre, 'Cuenta previa que no se debe tocar')
        self.assertEqual(m.Convocatoria.objects.count(), 0)

    def test_differences_and_additional_children_are_rejected(self):
        self.create()
        m.Beneficio.objects.filter(convocatoria=self.offers[0]).update(detalle='Cambio posterior')
        with self.assertRaisesMessage(CommandError, 'Diferencias'):
            load(self.actor.pk, preview=False)
        self.assertEqual(m.Beneficio.objects.filter(detalle='Cambio posterior').count(), 2)
        self.assertEqual(m.Evento.objects.filter(accion=MARK).count(), 1)

    def test_atomic_rollback_on_publication_error(self):
        with patch('convocatorias.demo_avances.publicar', side_effect=CommandError('Fallo simulado')):
            with self.assertRaises(CommandError):
                load(self.actor.pk, preview=False)
        self.assertFalse(Usuario.objects.filter(email=EMAIL).exists())
        self.assertEqual(m.Convocatoria.objects.count(), 0)
        self.assertEqual(m.Institucion.objects.count(), 0)
        self.assertEqual(m.Evento.objects.count(), 0)

    def test_preserves_previous_records(self):
        # Usa un conjunto anterior completo y cambia sus identificadores de fixture
        # solo en esta base de pruebas, como centinela ajeno a la nueva carga.
        self.create()
        institution = self.offers[0].institucion
        self.user.email = 'previous-fixture@example.com'; self.user.save()
        institution.nombre = 'Institución anterior'; institution.url_oficial = 'https://example.org/previous'; institution.save()
        for offer in self.offers:
            offer.titulo = offer.titulo.replace(PREFIX, 'Anterior ')
            offer.url_oficial = 'https://example.org/previous/' + str(offer.pk)
            offer.save()
        m.Evento.objects.filter(accion=MARK).update(accion='previous_manifest')
        before = snapshot(self.user, self.offers, institution)
        previous_ids = [o.pk for o in self.offers]
        load(self.actor.pk, preview=False)
        self.assertEqual(snapshot(self.user, list(m.Convocatoria.objects.filter(pk__in=previous_ids).order_by('pk')), institution), before)
        self.assertEqual(m.Convocatoria.objects.count(), 10)

    def test_public_api_details_and_authenticated_comparison(self):
        self.create()
        client = APIClient(enforce_csrf_checks=True)
        response = client.get('/api/becas/', {'q': PREFIX})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 5)
        for offer in self.offers:
            with patch('convocatorias.models.timezone.now', return_value=timezone.datetime(2026, 11, 5, 12, tzinfo=timezone.get_fixed_timezone(-300))):
                data = client.get(f'/api/becas/{offer.pk}/').data
                self.assertEqual(data['estado'], 'abierta')
            self.assertTrue(data['descripcion'] and data['url_bases'] and data['beneficios'] and data['requisitos'])
            self.assertTrue(all(o['programa'] and o['paises'] and o['inicio_estudios'] and o['cupos'] for o in data['opciones']))
            self.assertEqual(client.get(f'/api/becas/{offer.pk}/comparacion/').status_code, 403)
        client.force_authenticate(self.user)
        for (_, _, expected), offer in zip(CASES, self.offers, strict=True):
            data = client.get(f'/api/becas/{offer.pk}/comparacion/').data
            self.assertEqual([o['resultado'] for o in data['opciones']], expected)
