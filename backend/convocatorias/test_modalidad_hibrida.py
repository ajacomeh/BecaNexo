from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from perfiles.models import MODALIDADES, Pais, Perfil, Preferencia
from .comparacion import evaluar_convocatoria
from .models import Beneficio, Convocatoria, Evento, Institucion, OpcionEstudio
from .recomendaciones import preferencias_coincidentes, recomendar, texto_convocatoria, texto_perfil
from .semantica import vector
from rastreo.auto_borradores import editable_candidates
from notificaciones.models import Notificacion


class ModalidadHibridaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        cls.user = get_user_model().objects.create_user(email='hibrida@example.org', nombre='Prueba')
        cls.admin = get_user_model().objects.create_user(
            email='admin-hibrida@example.org', nombre='Administrador de prueba', rol='administrador')
        cls.ec = ec
        cls.perfil = Perfil.objects.create(usuario=cls.user, nacionalidad=ec)
        institution = Institucion.objects.create(nombre='Institución de prueba', sector='privado', pais=ec)
        for modality in ('hibrida', 'presencial'):
            offer = Convocatoria.objects.create(
                institucion=institution, titulo=f'Oportunidad {modality}', descripcion='Estudios de tecnología',
                url_oficial='https://example.org/oferta', cierre=timezone.now() + timedelta(days=30),
                revision='validada', clave_deduplicacion=f'prueba-modalidad-{modality}')
            option = OpcionEstudio.objects.create(convocatoria=offer, nivel='grado', modalidad=modality,
                                                   programa='Tecnología')
            option.paises.add(ec)
            if modality == 'hibrida':
                cls.hybrid = offer
            else:
                cls.legacy = offer

    def setUp(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_fusion_db')

    def test_catalogo_detalle_y_filtro_distinguen_hibrida_de_presencial(self):
        self.assertEqual(dict(MODALIDADES)['hibrida'], 'Híbrida')
        client = APIClient()
        hybrid = client.get('/api/becas/?modalidad=hibrida')
        self.assertEqual(hybrid.status_code, 200)
        hybrid_ids = [row['id'] for row in hybrid.data['results']]
        presencial_ids = [row['id'] for row in client.get('/api/becas/?modalidad=presencial').data['results']]
        self.assertIn(self.hybrid.pk, hybrid_ids)
        self.assertNotIn(self.legacy.pk, hybrid_ids)
        self.assertIn(self.legacy.pk, presencial_ids)
        self.assertNotIn(self.hybrid.pk, presencial_ids)
        self.assertEqual(client.get(f'/api/becas/{self.hybrid.pk}/').data['opciones'][0]['modalidad'], 'hibrida')
        self.assertEqual(client.get('/api/becas/?modalidad=semipresencial').data['count'], 0)

    def test_preferencias_y_comparacion_no_asumen_equivalencia(self):
        self.assertEqual(evaluar_convocatoria(self.user, self.hybrid)['opciones'][0]['preferencia_modalidad'],
                         'desconocido')
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        token = client.get('/api/auth/csrf/').data['csrfToken']
        for modality in ('presencial', 'hibrida'):
            response = client.post('/api/perfil/preferencias/', {'nivel': 'grado', 'modalidad': modality},
                                   format='json', HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 201)
        self.assertEqual(set(self.perfil.preferencias.values_list('modalidad', flat=True)),
                         {'presencial', 'hibrida'})
        self.assertEqual(evaluar_convocatoria(self.user, self.hybrid)['opciones'][0]['preferencia_modalidad'],
                         'coincide')
        self.assertEqual(evaluar_convocatoria(self.user, self.legacy)['opciones'][0]['preferencia_modalidad'],
                         'coincide')
        self.perfil.preferencias.filter(modalidad='hibrida').delete()
        compared = evaluar_convocatoria(self.user, self.hybrid)['opciones'][0]
        self.assertEqual(compared['preferencia_modalidad'], 'no_coincide')
        self.assertEqual(compared['resultado'], 'desconocido')
        self.assertNotIn('modalidad', preferencias_coincidentes(self.perfil, self.hybrid)['coincidencias'])

    def test_editor_administrativo_guarda_opcion_hibrida_sin_convertir_la_existente(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        token = client.get('/api/auth/csrf/').data['csrfToken']
        prior_version = self.legacy.version
        prior_notices = Notificacion.objects.count()
        response = client.post(
            f'/api/gestion/convocatorias/{self.legacy.pk}/opciones/',
            {'nivel': 'grado', 'modalidad': 'hibrida', 'programa': 'Programa híbrido',
             'paises': [self.ec.pk]}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['modalidad'], 'hibrida')
        self.assertEqual(set(self.legacy.opciones.values_list('modalidad', flat=True)),
                         {'presencial', 'hibrida'})
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.revision, 'validada')
        self.assertEqual(self.legacy.version, prior_version + 1)
        self.assertEqual(APIClient().get(f'/api/becas/{self.legacy.pk}/').status_code, 200)
        self.assertEqual(Notificacion.objects.count(), prior_notices)
        self.assertTrue(Evento.objects.filter(convocatoria=self.legacy, actor=self.admin,
                                              accion='opciones_crear').exists())

    def test_opcion_nueva_se_revierte_si_la_validacion_editorial_falla(self):
        Beneficio.objects.create(convocatoria=self.legacy, concepto='Matrícula')
        Beneficio.objects.create(convocatoria=self.legacy, concepto='Matrícula')
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        token = client.get('/api/auth/csrf/').data['csrfToken']
        prior_version = self.legacy.version
        response = client.post(
            f'/api/gestion/convocatorias/{self.legacy.pk}/opciones/',
            {'nivel': 'grado', 'modalidad': 'hibrida', 'programa': 'Programa nuevo',
             'paises': [self.ec.pk]}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 400)
        self.legacy.refresh_from_db()
        self.assertEqual((self.legacy.revision, self.legacy.version), ('validada', prior_version))
        self.assertEqual(self.legacy.opciones.count(), 1)

    def test_tres_programas_hibridos_conservan_catalogo_filtro_y_comparacion(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        token = client.get('/api/auth/csrf/').data['csrfToken']
        programs = ('Tecnología Superior en Agroecología',
                    'Tecnología Superior en Procesamiento de Lácteos',
                    'Tecnología Superior en Turismo Rural')
        for name in programs:
            response = client.post(
                f'/api/gestion/convocatorias/{self.legacy.pk}/opciones/',
                {'nivel': 'grado', 'modalidad': 'hibrida', 'programa': name,
                 'institucion_destino': 'Universidad del Azuay', 'paises': [self.ec.pk]},
                format='json', HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 201)
        self.legacy.refresh_from_db()
        self.assertEqual((self.legacy.revision, self.legacy.version), ('validada', 4))
        self.assertEqual(set(self.legacy.opciones.values_list('programa', flat=True)),
                         {'Tecnología', *programs})
        self.assertEqual(client.get(f'/api/becas/{self.legacy.pk}/').status_code, 200)
        hybrid = client.get('/api/becas/?modalidad=hibrida').data['results']
        self.assertIn(self.legacy.pk, [row['id'] for row in hybrid])
        Preferencia.objects.create(perfil=self.perfil, nivel='grado', modalidad='hibrida')
        compared = evaluar_convocatoria(self.user, self.legacy)['opciones']
        self.assertEqual([row['preferencia_modalidad'] for row in compared].count('coincide'), 3)
        self.assertEqual([row['preferencia_modalidad'] for row in compared].count('no_coincide'), 1)
        self.assertIn('híbrida', texto_convocatoria(self.legacy))

    def test_onnx_y_recomendacion_usan_el_valor_exacto(self):
        Preferencia.objects.create(perfil=self.perfil, nivel='grado', modalidad='hibrida')
        profile_text, _ = texto_perfil(self.perfil)
        self.assertIn('híbrida', profile_text)
        self.assertIn('híbrida', texto_convocatoria(self.hybrid))
        self.assertNotIn('híbrida', texto_convocatoria(self.legacy))
        with patch('convocatorias.recomendaciones.vector', return_value=(1.0, 0.0)), \
             patch('convocatorias.recomendaciones.vector_convocatoria', return_value=(1.0, 0.0)):
            result = {row['convocatoria']['id']: row for row in recomendar(self.user)}
        self.assertIn('modalidad', result[self.hybrid.pk]['preferencias']['coincidencias'])
        self.assertNotIn('modalidad', result[self.legacy.pk]['preferencias']['coincidencias'])
        self.assertEqual(result[self.hybrid.pk]['afinidad']['estado'], 'calculada')
        if not (Path(settings.SEMANTIC_MODEL_DIR) / 'onnx' / 'model_quint8_avx2.onnx').is_file():
            self.skipTest('Modelo ONNX local opcional no instalado')
        self.assertEqual(len(vector('Beca de tecnología en modalidad híbrida')), 384)

    def test_evidencia_hibrida_prepara_candidato_sin_validarlo(self):
        # Sin ficha HTML ni PDF archivados: editable_candidates consulta la relación de documentos de la versión.
        documents = MagicMock()
        documents.filter.return_value.select_related.return_value.first.return_value = None
        version = SimpleNamespace(pk=91, documentos=documents, datos_extraidos={
            'estudios': {'niveles_mencionados': ['Grado'],
                         'modalidad': {'texto_original': 'Híbrida'},
                         'destino': {'texto_original': 'Ecuador'}}})
        with patch('rastreo.estructura_semantica.interpretar_requisitos', return_value=[]), \
             patch('rastreo.estructura_semantica.candidatos_adicionales', return_value={}):
            options = editable_candidates(version)['opciones']
        self.assertEqual([(o['nivel'], o['modalidad'], o['validado']) for o in options],
                         [('grado', 'hibrida', False)])
        # Dos modalidades enumeradas en el mismo valor dan una opción por modalidad (criterio de la fase 3.2).
        version.datos_extraidos['estudios']['modalidad']['texto_original'] = 'Presencial e híbrida'
        with patch('rastreo.estructura_semantica.interpretar_requisitos', return_value=[]), \
             patch('rastreo.estructura_semantica.candidatos_adicionales', return_value={}):
            options = editable_candidates(version)['opciones']
        self.assertEqual([(o['nivel'], o['modalidad'], o['validado']) for o in options],
                         [('grado', 'presencial', False), ('grado', 'hibrida', False)])
