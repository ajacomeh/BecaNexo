"""Precarga asistida de propuestas en borradores automáticos; todo HTTP es simulado."""
import uuid
from unittest.mock import patch

from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from convocatorias.comparacion import evaluar_convocatoria
from convocatorias.models import Beneficio, BorradorRastreo, Evento, OpcionEstudio, Requisito
from convocatorias.services import postulables, publicar
from notificaciones.services import avisar_publicacion
from perfiles.models import Pais
from . import tests as base
from .auto_borradores import pending_for_publication
from .precarga import ACCION_PRECARGA, bloqueo_publicacion, estado, precargar
from . import test_auto_borradores as auto_tests

ORIGEN = {'version_id': 1, 'campo': 'requisitos', 'url': 'https://example.org/ficha', 'documento_id': 1}


def requisito(texto, tipo, estado_, valor=None, **extra):
    return {'texto_original': texto, 'tipo_sugerido': tipo, 'valor_sugerido': valor or {}, 'estado': estado_,
            'metodo': extra.pop('metodo', 'regla'), 'puntuacion': None, 'negacion_literal': extra.pop('negacion', False),
            'validado': False, 'procedencia': ORIGEN, **extra}


CANDIDATOS = {
    'requisitos': [
        requisito('Ser ciudadano ecuatoriano.', 'NACIONALIDAD', 'identificada', {'codigos_pais': ['EC']}),
        requisito('Tener la edad indicada en las bases.', 'EDAD', 'sugerida', metodo='onnx'),
        requisito('Contar con experiencia o título afín.', 'OTRO', 'ambigua', metodo='ambigua'),
        requisito('No haber recibido otra beca.', 'NACIONALIDAD', 'ambigua', negacion=True, metodo='negacion_pendiente'),
        requisito('Presentar copia de la cédula.', 'DOCUMENTO', 'identificada', {'documento': 'Copia de la cédula'}),
        requisito('Ser ciudadano ecuatoriano.', 'NACIONALIDAD', 'identificada', {'codigos_pais': ['EC']}),
    ],
    'opciones': [{'nivel': 'grado', 'modalidad': 'presencial', 'destino_original': 'Ecuador', 'validado': False,
                  'procedencia': {'version_id': 1, 'campos': ['estudios.niveles_mencionados']}}],
    'otros_campos': {'beneficios': [
        {'texto_original': 'Cubre el 50 % de la matrícula.', 'concepto_sugerido': 'Matrícula', 'porcentaje': 50.0,
         'monto': None, 'moneda': None, 'tope_original': None, 'tope_monto': None, 'tope_moneda': None,
         'estado': 'identificada', 'procedencia': ORIGEN},
        {'texto_original': 'Apoyo económico según disponibilidad.', 'concepto_sugerido': None, 'porcentaje': None,
         'monto': None, 'moneda': None, 'tope_original': None, 'tope_monto': None, 'tope_moneda': None,
         'estado': 'pendiente', 'procedencia': ORIGEN},
    ]},
}


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class PrecargaTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    capture = auto_tests.AutoDraftTests.capture

    def draft(self):
        Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        publication = self.capture()
        return BorradorRastreo.objects.get(publicacion=publication).convocatoria

    def admin_client(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.actor)
        return client, client.get('/api/auth/csrf/').data['csrfToken']

    def preload(self, offer, key=None):
        offer.refresh_from_db()
        with patch('rastreo.auto_borradores.editable_candidates', return_value=CANDIDATOS):
            return precargar(offer.pk, self.actor.pk, offer.version, key or uuid.uuid4())

    def test_preload_creates_only_confident_inactive_records_with_provenance(self):
        offer = self.draft()
        client, token = self.admin_client()
        path = f'/api/gestion/rastreo/convocatorias/{offer.pk}/precargar/'
        offer.refresh_from_db()
        body = {'version_convocatoria': offer.version, 'clave_accion': str(uuid.uuid4())}
        self.assertIn(APIClient(enforce_csrf_checks=True).post(path, body, format='json').status_code, (401, 403))
        self.assertEqual(client.post(path, body, format='json').status_code, 403)
        applicant = APIClient(enforce_csrf_checks=True)
        applicant.force_login(self.user)
        applicant_token = applicant.get('/api/auth/csrf/').data['csrfToken']
        self.assertEqual(applicant.post(path, body, format='json', HTTP_X_CSRFTOKEN=applicant_token).status_code, 403)
        with patch('rastreo.auto_borradores.editable_candidates', return_value=CANDIDATOS):
            response = client.post(path, body, format='json', HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 201, response.data)
            # La misma clave devuelve el mismo resultado sin crear registros.
            again = client.post(path, body, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data['creados'], response.data['creados'])
        created = {(row['modelo'], row['confianza']) for row in response.data['creados']}
        self.assertEqual(created, {('requisitos', 'alta'), ('beneficios', 'alta'), ('opciones', 'media')})
        self.assertEqual(len(response.data['creados']), 4)
        self.assertEqual(len(response.data['omitidos']), 4)
        omitted = {row['texto'] for row in response.data['omitidos']}
        self.assertIn('No haber recibido otra beca.', omitted)
        self.assertIn('Contar con experiencia o título afín.', omitted)
        self.assertIn('Tener la edad indicada en las bases.', omitted)
        self.assertEqual(Requisito.objects.filter(convocatoria=offer).count(), 2)
        self.assertFalse(Requisito.objects.filter(convocatoria=offer, activo=True).exists())
        self.assertFalse(Requisito.objects.filter(convocatoria=offer, validado=True).exists())
        self.assertEqual(Requisito.objects.get(convocatoria=offer, tipo_requisito__codigo='DOCUMENTO').modo_comprobacion, 'entidad_oferente')
        option = OpcionEstudio.objects.get(convocatoria=offer)
        self.assertFalse(option.activa)
        self.assertEqual(list(option.paises.all()), [])
        self.assertEqual(Beneficio.objects.get(convocatoria=offer).porcentaje, 50)
        event = Evento.objects.get(convocatoria=offer, accion=ACCION_PRECARGA)
        self.assertEqual(event.actor, self.actor)
        self.assertTrue(all(row['procedencia'] and row['huella'] for row in event.cambios['creados']))
        origin = client.get(f'/api/gestion/rastreo/convocatorias/{offer.pk}/origen/').data
        self.assertEqual({row['estado'] for row in origin['precarga']}, {'pendiente'})

    def test_preload_is_idempotent_and_never_overwrites_admin_edits(self):
        offer = self.draft()
        self.preload(offer)
        counts = (Requisito.objects.count(), Beneficio.objects.count(), OpcionEstudio.objects.count())
        document = Requisito.objects.get(convocatoria=offer, tipo_requisito__codigo='DOCUMENTO')
        client, token = self.admin_client()
        edited = client.patch(f'/api/gestion/convocatorias/{offer.pk}/requisitos/{document.pk}/',
                              {'texto_original': 'Texto revisado por administración.'}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(edited.status_code, 200, edited.data)
        changes, created = self.preload(offer)
        self.assertTrue(created)
        self.assertEqual((changes['creados'], changes['omitidos']), ([], []))
        self.assertEqual(counts, (Requisito.objects.count(), Beneficio.objects.count(), OpcionEstudio.objects.count()))
        document.refresh_from_db()
        self.assertEqual(document.texto_original, 'Texto revisado por administración.')

    def test_record_created_by_admin_before_preload_is_not_duplicated(self):
        from convocatorias.models import TipoRequisito
        offer = self.draft()
        client, token = self.admin_client()
        manual = client.post(f'/api/gestion/convocatorias/{offer.pk}/requisitos/', {
            'tipo_requisito': TipoRequisito.objects.get(codigo='NACIONALIDAD').pk,
            'texto_original': 'Ser  ciudadano ECUATORIANO.', 'valor_estructurado': {'codigos_pais': ['EC']},
            'modo_comprobacion': 'dato_declarado', 'validado': True}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(manual.status_code, 201, manual.data)
        changes, _ = self.preload(offer)
        self.assertNotIn('Ser ciudadano ecuatoriano.', {row['texto'] for row in changes['creados']})
        self.assertIn('El borrador ya contiene un registro equivalente; se conserva sin cambios.',
                      {row['motivo'] for row in changes['omitidos'] if row['texto'] == 'Ser ciudadano ecuatoriano.'})
        self.assertEqual(Requisito.objects.filter(convocatoria=offer, tipo_requisito__codigo='NACIONALIDAD').count(), 1)
        self.assertTrue(Requisito.objects.get(pk=manual.data['id']).validado)

    def test_pending_preload_blocks_publication_and_is_ignored_by_comparison_and_notices(self):
        offer = self.draft()
        self.preload(offer)
        offer.refresh_from_db()
        self.assertIn('propuestas precargadas', ' '.join(pending_for_publication(offer, offer.origen_automatico)))
        with self.assertRaises(ValidationError) as raised:
            publicar(offer)
        self.assertIn('propuestas precargadas', str(raised.exception.detail))
        self.assertEqual(evaluar_convocatoria(self.user, offer)['opciones'], [])
        self.assertFalse(postulables().filter(pk=offer.pk).exists())
        self.assertEqual(avisar_publicacion(offer), 0)

    def test_admin_resolves_each_preloaded_record_with_audit(self):
        offer = self.draft()
        self.preload(offer)
        client, token = self.admin_client()
        path = f'/api/gestion/rastreo/convocatorias/{offer.pk}/precarga/resolver/'
        rows = {(row['modelo'], row['texto']): row for row in estado(offer)}
        nationality = rows[('requisitos', 'Ser ciudadano ecuatoriano.')]
        offer.refresh_from_db()
        stale = client.post(path, {'modelo': 'requisitos', 'id': nationality['id'], 'decision': 'aceptar',
                                   'version_convocatoria': offer.version - 1}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(stale.status_code, 400)
        foreign = client.post(path, {'modelo': 'requisitos', 'id': 999999, 'decision': 'aceptar',
                                     'version_convocatoria': offer.version}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(foreign.status_code, 400)
        for (modelo, texto), decision in ((('requisitos', 'Ser ciudadano ecuatoriano.'), 'aceptar'),
                                          (('requisitos', 'Presentar copia de la cédula.'), 'descartar'),
                                          (('opciones', 'grado · presencial · Ecuador'), 'aceptar'),
                                          (('beneficios', 'Cubre el 50 % de la matrícula.'), 'descartar')):
            offer.refresh_from_db()
            response = client.post(path, {'modelo': modelo, 'id': rows[(modelo, texto)]['id'], 'decision': decision,
                                          'version_convocatoria': offer.version}, format='json', HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 201, response.data)
        accepted = Requisito.objects.get(pk=nationality['id'])
        self.assertTrue(accepted.activo and accepted.validado)
        self.assertFalse(Requisito.objects.get(texto_original='Presentar copia de la cédula.').activo)
        self.assertTrue(OpcionEstudio.objects.get(convocatoria=offer).activa)
        self.assertFalse(Beneficio.objects.filter(convocatoria=offer).exists())
        self.assertIsNone(bloqueo_publicacion(offer))
        offer.refresh_from_db()
        repeated = client.post(path, {'modelo': 'requisitos', 'id': nationality['id'], 'decision': 'aceptar',
                                      'version_convocatoria': offer.version}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(repeated.status_code, 200)
        conflict = client.post(path, {'modelo': 'requisitos', 'id': nationality['id'], 'decision': 'descartar',
                                      'version_convocatoria': offer.version}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(conflict.status_code, 400)
        self.assertEqual(Evento.objects.filter(convocatoria=offer, accion='resolver_precarga', actor=self.actor).count(), 4)
        # Un registro descartado no vuelve a precargarse.
        changes, _ = self.preload(offer)
        self.assertEqual(changes['creados'], [])

    def test_preload_is_refused_for_validated_offer_and_version_mismatch(self):
        offer = self.draft()
        offer.refresh_from_db()
        with self.assertRaises(ValidationError):
            precargar(offer.pk, self.actor.pk, offer.version + 1, uuid.uuid4())
        offer.revision = 'validada'
        offer.save(update_fields=['revision'])
        with self.assertRaises(ValidationError):
            precargar(offer.pk, self.actor.pk, offer.version, uuid.uuid4())
        with self.assertRaises(Exception):
            precargar(offer.pk, self.user.pk, offer.version, uuid.uuid4())

    def test_preload_from_synthetic_fiche_keeps_every_record_inactive(self):
        offer = self.draft()
        offer.refresh_from_db()
        changes, created = precargar(offer.pk, self.actor.pk, offer.version, uuid.uuid4())
        self.assertTrue(created)
        self.assertTrue(all(row['confianza'] in ('alta', 'media') for row in changes['creados']))
        self.assertFalse(Requisito.objects.filter(convocatoria=offer, activo=True).exists())
        self.assertFalse(Requisito.objects.filter(convocatoria=offer, validado=True).exists())
        self.assertFalse(OpcionEstudio.objects.filter(convocatoria=offer, activa=True).exists())
        self.assertEqual(len(pending_for_publication(offer, offer.origen_automatico)) > 0, True)
