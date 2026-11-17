"""Pruebas aisladas del borrador automático; todo HTTP es simulado."""
import uuid
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from convocatorias.models import BorradorRastreo, Convocatoria, Evento, Institucion, OpcionEstudio, Requisito, TipoRequisito
from convocatorias.services import publicar, publicas
from convocatorias.serializers import ConvocatoriaSerializer
from convocatorias.siau_red import INDEX, NATIONAL_INDEX
from perfiles.models import Pais
from notificaciones.models import Notificacion
from . import tests as base
from .auto_borradores import _candidate, _institution, classify_candidate, editable_candidates, pending_for_publication, latest_version, reevaluate_stored
from .models import Incidencia, Publicacion, Version
from .propuestas import guardar
from .services import enable_discovery, enable_national_discovery, run_manual, summary
from .test_periodico import NATIONAL_PAGE, national_index, national_ficha


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class AutoDraftTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake

    def test_literal_offerer_with_acronym_and_inclusive_citizenship(self):
        ec, _ = Pais.objects.get_or_create(codigo="EC", defaults={"nombre": "Ecuador"})
        Institucion.objects.create(nombre="Fundación Instituto Ecuatoriano de Estudios Occidente (OCCITEC)",
                                    sector="privado", pais=ec)
        publication = self.capture(offerer=False, citizenship=False)
        version = latest_version(publication)
        version.datos_extraidos['titulo']['texto_original'] = (
            'Oferta de Becas Nacionales para Educación Continua otorgadas por '
            'Fundación Instituto Ecuatoriano de Estudios Occidente')
        version.datos_extraidos['descripcion']['texto_original'] = (
            'Ciudadanos/as ecuatorianos/as docentes de instituciones de Imbabura.')
        version.datos_extraidos['requisitos']['texto_original'] = 'Ser ciudadano/a ecuatoriano/a.'
        result = classify_candidate(publication, version)
        self.assertEqual(result['estado'], 'apta')
        self.assertEqual(result['oferente'], 'verificado_ec')
        self.assertEqual(result['elegibilidad'], 'confirmada')

    def test_non_national_siau_needs_ecuadorian_offerer_evidence(self):
        publication = self.capture()
        version = latest_version(publication)
        version.datos_extraidos['titulo']['texto_original'] = 'Becas OEA AUWCL'
        version.datos_extraidos['oferentes'] = [
            {'nombre': 'Universidad extranjera', 'rol': 'oferente', 'pais_codigo': 'US',
             'pais_verificado': True, 'evidencia': 'Universidad extranjera ofrece la beca.'}]
        self.assertEqual(classify_candidate(publication, version)['estado'], 'fuera_alcance')
        version.datos_extraidos['oferentes'] = []
        self.assertEqual(classify_candidate(publication, version)['estado'], 'pendiente')
        version.datos_extraidos['oferentes'] = [
            {'nombre': 'Entidad ecuatoriana sintética', 'rol': 'cooferente', 'pais_codigo': 'EC',
             'pais_verificado': True, 'evidencia': 'Entidad ecuatoriana coofrece la beca.'}]
        self.assertEqual(classify_candidate(publication, version)['estado'], 'apta')

    def capture(self, html=None, citizenship=True, offerer=True, offerers=None):
        source = self.source() if not hasattr(self, 'source_id') else None
        if source:
            enable_discovery(self.actor.pk, 'Índice sintético')
            enable_national_discovery(self.actor.pk, 'Ficha sintética')
            self.source_id = source.pk

        def network(url):
            if url == INDEX:
                return 200, {'content-type': 'text/html'}, b'<html></html>'
            if url == NATIONAL_INDEX:
                return 200, {'content-type': 'text/html'}, national_index()
            if url == NATIONAL_PAGE:
                ficha = html or national_ficha()
                if citizenship:
                    ficha = ficha.replace(b'<ol>', b'<ol><li>Personas ecuatorianas.</li>')
                return 200, {'content-type': 'text/html'}, ficha
            return self.fake(url)

        from . import services as rastreo_services
        original_extract = rastreo_services.extract_html
        def synthetic_extract(page):
            data = original_extract(page)
            if offerer:
                data['oferentes'] = offerers if offerers is not None else [
                    {'nombre': 'Universidad ecuatoriana sintética', 'rol': 'oferente',
                     'pais_codigo': 'EC', 'pais_verificado': True, 'evidencia': 'La universidad ofrece esta beca.'}]
            else:
                data['descripcion']['texto_original'] += '\nUniversidad ecuatoriana sintética ofrece esta beca.'
            return data
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network), patch(
                'rastreo.services.extract_html', side_effect=synthetic_extract):
            run = run_manual(self.source_id, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertIn(run.estado, ('finalizada', 'parcial'))
        return Publicacion.objects.get(url_normalizada=NATIONAL_PAGE)

    def test_creates_private_draft_without_assigning_institution_and_keeps_identity(self):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        publication = self.capture()
        offer = publication.convocatoria
        origin = BorradorRastreo.objects.get(publicacion=publication)
        self.assertEqual(origin.convocatoria_id, offer.pk)
        self.assertIsNone(offer.institucion_id)
        self.assertEqual(offer.estado, 'borrador')
        self.assertEqual(publicas().filter(pk=offer.pk).count(), 0)
        self.assertTrue(origin.version.documentos.filter(rol='ficha_html').exists())
        self.assertEqual(Evento.objects.filter(convocatoria=offer).count(), 0)
        self.assertEqual(Notificacion.objects.filter(convocatoria=offer).count(), 0)
        self.assertTrue(origin.datos_iniciales['url_publicacion'])
        self.assertFalse(origin.datos_iniciales['entidad_sugerida'])
        self.assertEqual(Convocatoria.objects.count(), 1)
        self.assertEqual(summary(publication.observaciones.order_by('-id').first().ejecucion)['convocatorias_creadas'], 1)
        original_key = offer.clave_deduplicacion

        # Repetir y recibir una versión nueva no sobreescribe ediciones humanas.
        offer.titulo = 'Título revisado por administrador'
        offer.save(update_fields=['titulo'])
        self.capture()
        self.assertEqual(summary(publication.observaciones.order_by('-id').first().ejecucion)['convocatorias_creadas'], 0)
        # El fixture ya tiene el título nacional, por lo que cambiar descripción crea nueva versión.
        changed_html = national_ficha().replace(b'2026', b'2030')
        self.capture(changed_html)
        publication.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(publication.versiones.count(), 2)
        self.assertEqual(BorradorRastreo.objects.count(), 1)
        self.assertEqual(offer.titulo, 'Título revisado por administrador')
        self.assertEqual(offer.clave_deduplicacion, original_key)

    def test_recognized_institution_is_only_a_suggestion_and_manual_edit_is_valid(self):
        ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        name = 'Ministerio de Educación, Deporte y Cultura – MINEDEC'
        institution = Institucion.objects.create(nombre=name, sector='publico', pais=ec)
        data = {'entidad_html': {'texto_original': name}}
        self.assertEqual(_institution(data), institution)
        publication = self.capture()
        offer = publication.convocatoria
        self.assertIsNone(offer.institucion_id)
        # La mención puede variar; el campo de sugerencia se conserva solo si coincide exactamente.
        origin = BorradorRastreo.objects.get(publicacion=publication)
        if origin.datos_iniciales['entidad_mencionada'] == name:
            self.assertEqual(origin.datos_iniciales['entidad_sugerida']['id'], institution.pk)
        serializer = ConvocatoriaSerializer(offer, data={'institucion': institution.pk}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        key = offer.clave_deduplicacion
        serializer.save()
        offer.refresh_from_db()
        self.assertEqual(offer.clave_deduplicacion, key)
        self.assertEqual(offer.institucion_id, institution.pk)

    def test_publication_guard_and_admin_origin_permissions(self):
        publication = self.capture()
        offer = publication.convocatoria
        with self.assertRaises(ValidationError):
            publicar(offer)
        self.assertEqual(publicas().filter(pk=offer.pk).count(), 0)
        anon = APIClient(enforce_csrf_checks=True)
        path = f'/api/gestion/rastreo/convocatorias/{offer.pk}/origen/'
        self.assertIn(anon.get(path).status_code, (401, 403))
        anon.force_login(self.user)
        self.assertEqual(anon.get(path).status_code, 403)
        anon.force_login(self.actor)
        response = anon.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['automatico'])
        self.assertEqual(response.data['publicacion_id'], publication.pk)

    def test_non_candidate_is_ignored_and_minimal_review_can_publish(self):
        publication = self.capture()
        origin = BorradorRastreo.objects.get(publicacion=publication)
        version = origin.version
        version.datos_extraidos['titulo']['texto_original'] = 'Información de trámites'
        self.assertFalse(_candidate(publication, version))
        self.assertEqual(BorradorRastreo.objects.count(), 1)
        # Preparación sintética de todos los mínimos; no se escriben datos de desarrollo.
        ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        institution = Institucion.objects.create(nombre='Entidad de prueba', sector='publico', pais=ec)
        offer = origin.convocatoria
        offer.institucion = institution
        offer.url_oficial = 'https://siau.senescyt.gob.ec/convocatoria-prueba/'
        offer.cierre_dia = None
        offer.cierre_original = None
        from django.utils import timezone
        from datetime import timedelta
        offer.cierre = timezone.now() + timedelta(days=30)
        offer.save()
        OpcionEstudio.objects.create(convocatoria=offer, nivel='grado', modalidad='virtual')
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        kind = TipoRequisito.objects.get(codigo='OTRO')
        Requisito.objects.create(convocatoria=offer, tipo_requisito=kind,
            texto_original='Condición sintética', operador='externo',
            valor_estructurado={'descripcion': 'Condición sintética'},
            modo_comprobacion='entidad_oferente', validado=True)
        self.assertFalse(pending_for_publication(offer, origin))
        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        csrf = admin.get('/api/auth/csrf/').data['csrfToken']
        response = admin.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {}, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 200, response.data)
        offer.refresh_from_db()
        self.assertEqual(offer.revision, 'validada')
        self.assertEqual(publicas().filter(pk=offer.pk).count(), 1)
        self.assertTrue(Evento.objects.filter(convocatoria=offer, actor=self.actor, accion='publicar').exists())

    def test_verified_ec_offerer_without_nationality_creates_private_blocked_draft(self):
        publication = self.capture(citizenship=False)
        self.assertIsNotNone(publication.convocatoria_id)
        self.assertEqual(BorradorRastreo.objects.count(), 1)
        version = latest_version(publication)
        self.assertEqual(classify_candidate(publication, version)['estado'], 'apta')
        self.assertEqual(classify_candidate(publication, version)['elegibilidad'], 'no_especificada')
        self.assertTrue(any('participación ecuatoriana' in x for x in pending_for_publication(publication.convocatoria, BorradorRastreo.objects.get(publicacion=publication))))
        self.assertFalse(publicas().filter(pk=publication.convocatoria_id).exists())
        self.assertTrue(Incidencia.objects.filter(publicacion=publication,
            codigo='BORRADOR_REVISION_PENDIENTE', gravedad='aviso').exists())
        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        detail = admin.get(f'/api/gestion/rastreo/publicaciones/{publication.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['clasificacion_borrador']['estado'], 'apta')
        self.assertEqual(detail.data['borrador']['id'], publication.convocatoria_id)
        self.assertEqual(detail.data['borrador']['revision'], 'pendiente')
        self.assertTrue(any('participación ecuatoriana' in reason for reason in detail.data['borrador']['bloqueos']))
        self.assertTrue(detail.data['cierre_extraido'])

    def test_unknown_offerer_with_confirmed_recipients_creates_private_draft(self):
        publication = self.capture(offerer=False)
        self.assertIsNotNone(publication.convocatoria_id)
        self.assertEqual(classify_candidate(publication, latest_version(publication))['estado'], 'apta')
        self.assertIsNone(publication.convocatoria.institucion_id)
        self.assertFalse(publicas().filter(pk=publication.convocatoria_id).exists())

    def test_nationality_evidence_without_literal_citizenship_is_distinct_from_offerer(self):
        publication = self.capture(offerer=False, citizenship=False)
        version = latest_version(publication)
        self.assertEqual(classify_candidate(publication, version)['elegibilidad'], 'no_especificada')
        self.assertEqual(classify_candidate(publication, version)['estado'], 'pendiente')
        version.datos_extraidos['requisitos']['texto_original'] += '\nNacionalidad ecuatoriana acreditada.'
        assessment = classify_candidate(publication, version)
        self.assertEqual(assessment['elegibilidad'], 'confirmada')
        self.assertEqual(assessment['estado'], 'apta')
        self.assertNotEqual(assessment['oferente'], 'verificado_ec')

    def test_publish_without_identified_offerer_keeps_source_and_unknown_requirements(self):
        from datetime import timedelta
        from django.utils import timezone
        from convocatorias.comparacion import evaluar_convocatoria
        from .auto_borradores import review_notes

        publication = self.capture(offerer=False)
        offer = publication.convocatoria
        origin = BorradorRastreo.objects.get(convocatoria=offer)
        offer.url_oficial = publication.url_original
        offer.cierre_dia = None
        offer.cierre_original = None
        offer.cierre = timezone.now() + timedelta(days=30)
        offer.save(update_fields=['url_oficial', 'cierre_dia', 'cierre_original', 'cierre'])
        ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        option = OpcionEstudio.objects.create(convocatoria=offer, nivel='grado', modalidad='virtual')
        option.paises.add(ec)
        self.assertTrue(any('Requisitos extraídos' in note for note in review_notes(offer, origin)))
        self.assertFalse(pending_for_publication(offer, origin))
        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        token = admin.get('/api/auth/csrf/').data['csrfToken']
        response = admin.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.data)
        offer.refresh_from_db()
        self.assertIsNone(offer.institucion_id)
        self.assertEqual(offer.revision, 'validada')
        self.assertEqual(publicas().filter(pk=offer.pk).count(), 1)
        self.assertEqual(evaluar_convocatoria(self.user, offer)['opciones'][0]['resultado'], 'desconocido')
        public = APIClient()
        self.assertEqual(public.get('/api/becas/').data['count'], 1)
        self.assertIsNone(public.get(f'/api/becas/{offer.pk}/').data['institucion'])
        from favoritos.models import Favorito
        Favorito.objects.create(usuario=self.user, convocatoria=offer)
        public.force_login(self.user)
        favorite = public.get('/api/favoritos/')
        self.assertEqual(favorite.status_code, 200)
        self.assertEqual(favorite.data['results'][0]['convocatoria']['institucion'], 'No identificada')
        self.assertTrue(Evento.objects.filter(convocatoria=offer, actor=self.actor, accion='publicar').exists())

    def test_unknown_and_expired_validity_are_historical_not_recommended(self):
        from datetime import timedelta
        from django.utils import timezone

        publication = self.capture(offerer=False)
        offer = publication.convocatoria
        offer.url_oficial = publication.url_original
        offer.cierre = None
        offer.cierre_dia = None
        offer.cierre_original = None
        offer.save(update_fields=['url_oficial', 'cierre', 'cierre_dia', 'cierre_original'])
        OpcionEstudio.objects.create(convocatoria=offer, nivel='grado', modalidad='virtual')
        publicar(offer)
        self.assertEqual(offer.estado, 'sin_fecha')
        public = APIClient()
        self.assertEqual(public.get('/api/becas/').data['count'], 0)
        self.assertEqual(public.get('/api/becas/?estado=sin_fecha').data['count'], 1)
        public.force_login(self.user)
        recommendations = public.get('/api/becas/recomendaciones/')
        self.assertEqual(recommendations.status_code, 200)
        self.assertFalse(recommendations.data['results'])
        offer.cierre = timezone.now() - timedelta(days=1)
        offer.save(update_fields=['cierre'])
        self.assertEqual(offer.estado, 'cerrada')
        self.assertEqual(public.get('/api/becas/').data['count'], 0)
        self.assertEqual(public.get('/api/becas/?estado=cerrada').data['count'], 1)

    def test_expired_verified_offer_can_be_published_only_as_history(self):
        from datetime import timedelta
        from django.utils import timezone

        publication = self.capture(offerer=False)
        offer = publication.convocatoria
        offer.url_oficial = publication.url_original
        offer.cierre_dia = None
        offer.cierre_original = None
        offer.cierre = timezone.now() - timedelta(days=1)
        offer.save(update_fields=['url_oficial', 'cierre_dia', 'cierre_original', 'cierre'])
        OpcionEstudio.objects.create(convocatoria=offer, nivel='grado', modalidad='virtual')
        publicar(offer)
        self.assertEqual(offer.estado, 'cerrada')
        public = APIClient()
        self.assertEqual(public.get('/api/becas/').data['count'], 0)
        self.assertEqual(public.get('/api/becas/?estado=cerrada').data['count'], 1)
        self.assertFalse(Notificacion.objects.filter(convocatoria=offer).exists())

    def test_stored_reevaluation_is_read_only_by_default_and_idempotent_when_applied(self):
        publication = self.capture(offerer=False, citizenship=False)
        self.assertEqual(reevaluate_stored(publication.pk)['estado'], 'pendiente')
        ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        Institucion.objects.create(nombre='Universidad ecuatoriana sintética', sector='publico', pais=ec)
        preview = reevaluate_stored(publication.pk)
        self.assertEqual(preview['estado'], 'apta')
        self.assertIsNone(preview['borrador_id'])
        first = reevaluate_stored(publication.pk, apply=True)
        second = reevaluate_stored(publication.pk, apply=True)
        self.assertTrue(first['creado'])
        self.assertFalse(second['creado'])
        self.assertEqual(first['borrador_id'], second['borrador_id'])
        self.assertEqual(BorradorRastreo.objects.filter(publicacion=publication).count(), 1)
        offer = Convocatoria.objects.get(pk=first['borrador_id'])
        self.assertIsNone(offer.institucion_id)
        offer.titulo = 'Título revisado por administración'
        offer.save(update_fields=['titulo'])
        self.assertFalse(reevaluate_stored(publication.pk, apply=True)['creado'])
        offer.refresh_from_db()
        self.assertEqual(offer.titulo, 'Título revisado por administración')

    def test_foundation_and_cooffer_allow_private_draft_with_province_only_recipients(self):
        ec_offerer = {'nombre': 'Fundación ecuatoriana sintética', 'rol': 'cooferente',
            'pais_codigo': 'EC', 'pais_verificado': True, 'evidencia': 'Cooferente según la ficha.'}
        foreign = {'nombre': 'Universidad extranjera sintética', 'rol': 'oferente',
            'pais_codigo': 'US', 'pais_verificado': True, 'evidencia': 'Oferente según la ficha.'}
        provincial_ficha = national_ficha().replace(
            b'<ol>', b'<ol><li>Residentes de la provincia de Pichincha.</li>')
        publication = self.capture(html=provincial_ficha, citizenship=False, offerers=[ec_offerer, foreign])
        assessment = classify_candidate(publication, latest_version(publication))
        self.assertEqual(assessment['oferente'], 'verificado_ec')
        self.assertEqual(assessment['elegibilidad'], 'no_especificada')
        self.assertEqual(assessment['estado'], 'apta')
        self.assertEqual(BorradorRastreo.objects.count(), 1)
        self.assertFalse(publicas().filter(pk=publication.convocatoria_id).exists())

    def test_explicit_exclusion_and_informative_category_never_create_draft(self):
        publication = self.capture(offerer=False, citizenship=False)
        version = latest_version(publication)
        version.datos_extraidos['requisitos']['texto_original'] += '\nNo pueden postular ciudadanos ecuatorianos.'
        self.assertEqual(classify_candidate(publication, version)['elegibilidad'], 'excluida')
        self.assertEqual(classify_candidate(publication, version)['estado'], 'fuera_alcance')
        version.datos_extraidos['tipo_oportunidad'] = 'categoria_general'
        self.assertEqual(classify_candidate(publication, version)['naturaleza'], 'informativa')
        self.assertEqual(classify_candidate(publication, version)['estado'], 'fuera_alcance')
        self.assertFalse(BorradorRastreo.objects.exists())

    def test_international_title_without_offerer_evidence_stays_pending(self):
        publication = self.capture(citizenship=False, offerer=False)
        version = latest_version(publication)
        version.datos_extraidos['titulo']['texto_original'] = 'Programa de becas internacionales'
        self.assertEqual(classify_candidate(publication, version)['estado'], 'pendiente')
        self.assertFalse(_candidate(publication, version))

    def test_verified_foreign_offerer_is_out_of_scope_even_with_ecuadorian_recipients(self):
        foreign = [{'nombre': 'Entidad extranjera sintética', 'rol': 'oferente',
            'pais_codigo': 'US', 'pais_verificado': True, 'evidencia': 'La entidad ofrece la beca.'},
            {'nombre': 'Portal ecuatoriano', 'rol': 'difusor', 'pais_codigo': 'EC', 'pais_verificado': True,
             'evidencia': 'El portal difunde la noticia.'}]
        publication = self.capture(offerers=foreign)
        version = latest_version(publication)
        self.assertEqual(classify_candidate(publication, version)['estado'], 'fuera_alcance')
        self.assertIsNone(publication.convocatoria_id)

    def test_editable_candidates_keep_literal_source_and_require_complete_option(self):
        publication = self.capture()
        version = latest_version(publication)
        data = version.datos_extraidos
        data['requisitos']['texto_original'] = '- Promedio mínimo 8.5\n- Certificado de idioma B2'
        data['estudios'] = {'niveles_mencionados': ['maestría'],
            'modalidad': {'texto_original': 'Virtual'}, 'destino': {'texto_original': 'Ecuador'}}
        candidates = editable_candidates(version)
        self.assertEqual([r['texto_original'] for r in candidates['requisitos']], ['Promedio mínimo 8.5', 'Certificado de idioma B2'])
        self.assertEqual([r['tipo_sugerido'] for r in candidates['requisitos']], ['PROMEDIO', 'IDIOMA'])
        self.assertTrue(all(not r['validado'] and r['procedencia']['version_id'] == version.pk for r in candidates['requisitos']))
        self.assertEqual(candidates['opciones'][0]['nivel'], 'maestria')
        data['estudios']['destino'] = {'texto_original': ''}
        self.assertEqual(editable_candidates(version)['opciones'], [])

    def test_origin_shows_distinct_source_links_without_assigning_official_application(self):
        publication = self.capture()
        origin = BorradorRastreo.objects.get(publicacion=publication)
        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        response = admin.get(f'/api/gestion/rastreo/convocatorias/{origin.convocatoria_id}/origen/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['enlaces_origen']['publicacion'], publication.url_original)
        self.assertEqual(response.data['candidatos_editables']['requisitos'][0]['procedencia']['version_id'], origin.version_id)
        self.assertEqual(origin.convocatoria.url_oficial, '')

    def test_relevant_new_version_hides_validated_offer_until_admin_confirmation(self):
        publication = self.capture()
        origin = BorradorRastreo.objects.get(publicacion=publication)
        offer = origin.convocatoria
        ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        offer.institucion = Institucion.objects.create(nombre='Oferente sintético', sector='publico', pais=ec)
        offer.titulo = 'Título corregido por administración'
        offer.revision = 'validada'
        offer.save(update_fields=['institucion', 'titulo', 'revision'])
        original_version = origin.version_id
        self.capture(national_ficha().replace(b'2026', b'2030'))
        offer.refresh_from_db()
        current = latest_version(publication)
        self.assertNotEqual(current.pk, original_version)
        self.assertEqual(origin.version_id, original_version)
        self.assertEqual(offer.titulo, 'Título corregido por administración')
        self.assertEqual(offer.revision, 'pendiente')
        self.assertEqual(publicas().filter(pk=offer.pk).count(), 0)
        self.assertTrue(any('versión' in text for text in pending_for_publication(offer, origin)))
        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        token = admin.get('/api/auth/csrf/').data['csrfToken']
        path = f'/api/gestion/rastreo/convocatorias/{offer.pk}/origen/'
        rejected = admin.post(path, {'version_id': original_version, 'version_convocatoria': offer.version,
            'motivo': 'Versión anterior'}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(rejected.status_code, 400)
        approved = admin.post(path, {'version_id': current.pk, 'version_convocatoria': offer.version,
            'motivo': 'Comparé los cambios con la ficha sintética y conservé la corrección del título.'},
            format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(approved.status_code, 201, approved.data)
        self.assertFalse(any('versión' in text for text in pending_for_publication(offer, origin)))
        self.assertEqual(Evento.objects.filter(convocatoria=offer, accion='confirmar_version_rastreo').count(), 1)

        offer.revision = 'validada'
        offer.save(update_fields=['revision'])
        same_content = national_ficha().replace(b'2026', b'2030') + b'<!--byte-change-->'
        self.capture(same_content)
        offer.refresh_from_db()
        self.assertEqual(offer.revision, 'validada')
        self.assertFalse(any('versión' in text for text in pending_for_publication(offer, origin)))

    def test_manual_proposal_can_update_linked_draft_only_with_explicit_admin_choice(self):
        publication = self.capture()
        origin = BorradorRastreo.objects.get(publicacion=publication)
        offer = origin.convocatoria
        observation = publication.observaciones.filter(version=origin.version).order_by('-id').first()
        evidence = origin.version.documentos.first()
        proposal, created = guardar(self.actor.pk, publication.pk, {
            'clave_accion': str(uuid.uuid4()), 'version_id': origin.version_id,
            'observacion_base_id': observation.pk, 'revisiones': [],
            'datos': {'titulo': 'Título revisado desde propuesta'},
            'procedencia': [{'campo': 'titulo', 'evidencia_id': evidence.pk,
                             'localizador': 'Ficha sintética', 'motivo': 'Transcripción revisada'}],
        })
        self.assertTrue(created)
        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        path = f'/api/gestion/rastreo/propuestas/{proposal.pk}/aplicar-borrador/'
        listing = admin.get(f'/api/gestion/rastreo/publicaciones/{publication.pk}/propuesta/')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['borrador_automatico_id'], offer.pk)
        body = {'version_convocatoria': offer.version, 'hash_propuesta': proposal.hash_propuesta,
                'campos': ['titulo'], 'motivo': 'Comparé la ficha y confirmo únicamente el título.'}
        self.assertIn(APIClient(enforce_csrf_checks=True).post(path, body, format='json').status_code, (401, 403))
        admin_no_csrf = APIClient(enforce_csrf_checks=True)
        admin_no_csrf.force_login(self.actor)
        self.assertEqual(admin_no_csrf.post(path, body, format='json').status_code, 403)
        token = admin.get('/api/auth/csrf/').data['csrfToken']
        result = admin.post(path, body, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(result.status_code, 200, result.data)
        offer.refresh_from_db()
        self.assertEqual(offer.titulo, 'Título revisado desde propuesta')
        self.assertEqual(BorradorRastreo.objects.filter(publicacion=publication).count(), 1)
        self.assertEqual(Evento.objects.filter(convocatoria=offer, actor=self.actor,
                                             accion='aplicar_propuesta_borrador').count(), 1)
        self.assertEqual(admin.post(path, body, format='json', HTTP_X_CSRFTOKEN=token).status_code, 400)

    def test_joint_lifecycle_keeps_draft_private_until_admin_reviews_new_version_and_publishes(self):
        from datetime import timedelta
        from django.utils import timezone

        publication = self.capture()
        origin = BorradorRastreo.objects.get(publicacion=publication)
        offer = origin.convocatoria
        self.assertFalse(publicas().filter(pk=offer.pk).exists())
        self.assertEqual(Convocatoria.objects.count(), 1)

        ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        institution = Institucion.objects.create(nombre='Entidad ecuatoriana sintética', sector='publico', pais=ec)
        offer.institucion = institution
        offer.url_oficial = 'https://siau.senescyt.gob.ec/convocatoria-sintetica/'
        offer.cierre_dia = None
        offer.cierre_original = None
        offer.cierre = timezone.now() + timedelta(days=30)
        offer.save()
        OpcionEstudio.objects.create(convocatoria=offer, nivel='grado', modalidad='virtual')
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        kind = TipoRequisito.objects.get(codigo='OTRO')
        Requisito.objects.create(convocatoria=offer, tipo_requisito=kind,
            texto_original='Condición sintética', operador='externo',
            valor_estructurado={'descripcion': 'Condición sintética'},
            modo_comprobacion='entidad_oferente', validado=True)

        observation = publication.observaciones.filter(version=origin.version).order_by('-id').first()
        evidence = origin.version.documentos.first()
        proposal, _ = guardar(self.actor.pk, publication.pk, {
            'clave_accion': str(uuid.uuid4()), 'version_id': origin.version_id,
            'observacion_base_id': observation.pk, 'revisiones': [],
            'datos': {'titulo': 'Beca revisada por administración'},
            'procedencia': [{'campo': 'titulo', 'evidencia_id': evidence.pk,
                             'localizador': 'Ficha sintética', 'motivo': 'Lectura administrativa'}],
        })
        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        token = admin.get('/api/auth/csrf/').data['csrfToken']
        applied = admin.post(f'/api/gestion/rastreo/propuestas/{proposal.pk}/aplicar-borrador/', {
            'version_convocatoria': offer.version, 'hash_propuesta': proposal.hash_propuesta,
            'campos': ['titulo'], 'motivo': 'Confirmé el título de la ficha sintética.'},
            format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(applied.status_code, 200, applied.data)
        offer.refresh_from_db()
        self.assertEqual(offer.titulo, 'Beca revisada por administración')

        self.capture(national_ficha().replace(b'2026', b'2030'))
        latest = latest_version(publication)
        self.assertNotEqual(latest.pk, origin.version_id)
        blocked = admin.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {},
                             format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(blocked.status_code, 400)
        offer.refresh_from_db()
        reviewed = admin.post(f'/api/gestion/rastreo/convocatorias/{offer.pk}/origen/', {
            'version_id': latest.pk, 'version_convocatoria': offer.version,
            'motivo': 'Revisé la nueva versión; mantengo los datos administrativos.'},
            format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(reviewed.status_code, 201, reviewed.data)
        self.assertFalse(pending_for_publication(offer, origin))
        published = admin.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {},
                               format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(published.status_code, 200, published.data)
        self.assertEqual(publicas().filter(pk=offer.pk).count(), 1)
        self.assertEqual(BorradorRastreo.objects.filter(publicacion=publication).count(), 1)
        self.assertTrue(Evento.objects.filter(convocatoria=offer, actor=self.actor,
                                             accion='aplicar_propuesta_borrador').exists())
        self.assertTrue(Evento.objects.filter(convocatoria=offer, actor=self.actor,
                                             accion='confirmar_version_rastreo').exists())
