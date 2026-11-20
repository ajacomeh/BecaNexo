"""Clasificación con confianza al crear borradores automáticos. HTTP simulado; reglas de publicación intactas."""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from convocatorias.models import BorradorRastreo, Institucion
from convocatorias.services import errores_publicacion, publicar
from perfiles.models import Pais
from . import tests as base
from . import test_auto_borradores as auto_tests
from .auto_borradores import _classify_for_publication, classify_candidate
from .descubrimiento import national_ficha_content, national_ficha_flexible
from .models import Incidencia, Publicacion

REQUISITOS = 'Requisitos generales: ser ciudadano ecuatoriano y presentar la solicitud.'


class Docs:
    def __init__(self, *roles):
        self.roles = set(roles)

    def filter(self, rol=None, **_):
        return SimpleNamespace(exists=lambda: rol in self.roles)


def evaluate(titulo, descripcion='', *, oferentes=None, requisitos=REQUISITOS, cierre='30 de diciembre de 2026',
             completa=True, adaptador='siau', documentos=('ficha_html',), **extra):
    data = {'titulo': {'texto_original': titulo}, 'descripcion': {'texto_original': descripcion},
            'requisitos': {'texto_original': requisitos},
            'cierre': {'texto_original': cierre, 'fecha': '2026-12-30' if cierre else None},
            'oferentes': oferentes or [], 'seccion_completa': completa, **extra}
    publication = SimpleNamespace(fuente=SimpleNamespace(adaptador=adaptador, nombre='Fuente sintética'),
                                  url_normalizada='https://example.org/beca', url_original='https://example.org/beca')
    version = SimpleNamespace(pk=1, datos_extraidos=data, documentos=Docs(*documentos))
    return classify_candidate(publication, version), _classify_for_publication(publication, version), (publication, version)


class ConfianzaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        Institucion.objects.create(nombre='Universidad Técnica Particular de Loja (UTPL)', sector='privado', pais=ec)

    def test_alta_requires_verified_ecuadorian_offerer_and_confirmed_recipients(self):
        offerer = [{'nombre': 'Universidad ecuatoriana sintética', 'rol': 'oferente', 'pais_codigo': 'EC',
                    'pais_verificado': True, 'evidencia': 'La universidad ofrece esta beca.'}]
        result, _, _ = evaluate('Beca de maestría', 'Para ciudadanos ecuatorianos.', oferentes=offerer)
        self.assertEqual((result['estado'], result['confianza']), ('apta', 'alta'))
        result, _, _ = evaluate('Beca de maestría', 'Beca de posgrado.', oferentes=offerer, requisitos='Presentar la solicitud.')
        self.assertEqual((result['estado'], result['confianza']), ('apta', 'media'))
        self.assertIn('Participación de ciudadanos ecuatorianos por confirmar en las bases.', result['marcas'])

    def test_media_for_named_ecuadorian_offerer_or_cooffer_even_for_study_abroad(self):
        cases = (
            ('Programa de Becas para Mujeres Ecuatorianas Universidad Europea – Ministerio de Gobierno del Ecuador', ''),
            ('Beca de doctorado en España', 'Beca otorgada por la Universidad Central del Ecuador para estudiar en Madrid.'),
            ('Beca de maestría en Chile', 'Programa en convenio con la Universidad Técnica Particular de Loja.'),
        )
        for title, description in cases:
            with self.subTest(title=title):
                result, _, _ = evaluate(title, description)
                self.assertEqual((result['estado'], result['confianza']), ('apta', 'media'))
                self.assertEqual(result['oferente'], 'mencionado_ec')
                self.assertTrue(any(mark.startswith('Oferente o cooferente ecuatoriano por verificar') for mark in result['marcas']))

    def test_recipients_alone_are_not_an_ecuadorian_offerer(self):
        result, _, _ = evaluate('Beca internacional de maestría', 'Dirigida a ciudadanos ecuatorianos y estudiantes del Ecuador.')
        self.assertEqual(result['estado'], 'pendiente')
        self.assertEqual(result['confianza'], 'baja')
        self.assertEqual(result['motivo'], 'Sin borrador: la ficha no nombra una entidad ecuatoriana como oferente o cooferente.')

    def test_foreign_only_offerer_is_discarded_even_for_ecuadorian_recipients(self):
        result, _, _ = evaluate('Becas Internacionales de Maestría', 'Becas otorgadas por la Universidad Americana de Europa para ecuatorianos.')
        self.assertEqual(result['estado'], 'fuera_alcance')
        self.assertTrue(result['motivo'].startswith('Descartada: oferente extranjero (Universidad Americana de Europa'))
        verified = [{'nombre': 'University abroad', 'rol': 'oferente', 'pais_codigo': 'US', 'pais_verificado': True, 'evidencia': 'Ofrece.'}]
        result, _, _ = evaluate('Beca de grado', 'Para personas ecuatorianas.', oferentes=verified)
        self.assertEqual(result['estado'], 'fuera_alcance')
        self.assertEqual(result['motivo'], 'Descartada: oferente extranjero (University abroad), sin entidad ecuatoriana.')

    def test_unregistered_entity_without_ecuadorian_marker_stays_without_draft(self):
        result, _, _ = evaluate('Beca de grado', 'Beca otorgada por la Universidad San Martín.')
        self.assertEqual(result['estado'], 'pendiente')
        self.assertIn('no consta como ecuatoriana', result['motivo'])

    def test_national_siau_is_media_and_missing_data_becomes_marks(self):
        result, strict, _ = evaluate('Programa de Becas Nacionales de Grado', '', requisitos='', cierre='', completa=False)
        self.assertEqual((result['estado'], result['confianza']), ('apta', 'media'))
        for mark in ('Oferente por identificar en las bases de la beca nacional.', 'Requisitos no encontrados en la ficha.',
                     'Cierre no encontrado en la ficha.', 'Descripción no encontrada en la ficha.',
                     'Estructura de ficha distinta o incompleta; revisa la ficha archivada.'):
            self.assertIn(mark, result['marcas'])
        # La regla de publicación conserva su exigencia anterior.
        self.assertEqual(strict['estado'], 'pendiente')

    def test_long_texts_are_kept_and_only_title_is_truncated(self):
        result, _, _ = evaluate('Programa de Becas Nacionales ' + 'x' * 300, 'Descripción ' * 3000, requisitos='Requisito. ' * 800)
        self.assertEqual(result['estado'], 'apta')
        self.assertIn('Título truncado a 250 caracteres; el texto completo está en la ficha.', result['marcas'])
        self.assertNotIn('Requisitos no encontrados en la ficha.', result['marcas'])
        self.assertNotIn('Descripción no encontrada en la ficha.', result['marcas'])

    def test_required_conditions_at_creation_are_kept(self):
        self.assertEqual(evaluate('Convocatoria general', 'Información institucional.')[0]['estado'], 'fuera_alcance')
        self.assertEqual(evaluate('Becas Nacionales', 'Beca.', documentos=())[0]['estado'], 'pendiente')
        excluded = evaluate('Becas Nacionales', 'No pueden postular ciudadanos ecuatorianos.')[0]
        self.assertEqual((excluded['estado'], excluded['elegibilidad']), ('fuera_alcance', 'excluida'))
        self.assertEqual(evaluate('Becas Nacionales', tipo_oportunidad='noticia')[0]['estado'], 'fuera_alcance')

    def test_institutional_portal_is_named_offerer_with_marks(self):
        from .portal_fuentes import PORTALES
        with patch('rastreo.portal_fuentes.portal_for_source', return_value=PORTALES['utpl']), \
                patch('rastreo.portal_fuentes.admitted_url', return_value=True):
            result, _, _ = evaluate('Beca de excelencia', 'Beca para estudiantes.', adaptador='portal_ec:utpl',
                                    cierre='', vigencia_al_consultar='vencida')
        self.assertEqual((result['estado'], result['confianza']), ('apta', 'media'))
        self.assertIn('Oferente inferido del portal institucional; confirma que la beca es propia.', result['marcas'])
        self.assertIn('Cierre vencido al consultar: solo puede publicarse como convocatoria histórica.', result['marcas'])


class FichaFlexibleTests(SimpleTestCase):
    def test_flexible_rule_keeps_title_requirement_and_relaxes_markers(self):
        page = '<h1 class="entry-title">Programa de Becas Nacionales 2027</h1><p>{}</p>'
        body = 'La convocatoria describe beneficios y condiciones generales para estudiantes de grado.'
        self.assertFalse(national_ficha_content(page.format(body).encode()))
        self.assertTrue(national_ficha_flexible(page.format(body).encode()))
        self.assertFalse(national_ficha_flexible(page.format('Corto.').encode()))
        self.assertFalse(national_ficha_flexible(page.replace('Nacionales', 'Internacionales').format(body).encode()))
        self.assertTrue(national_ficha_flexible(page.replace('Nacionales', 'Internacionales').format(body).encode(), include_all_becas=True))


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class BorradorConfianzaFlujoTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    capture = auto_tests.AutoDraftTests.capture

    def admin(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.actor)
        return client

    def test_draft_stores_confidence_internally_but_api_does_not_expose_or_filter_it(self):
        Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        publication = self.capture(offerer=False)
        origin = BorradorRastreo.objects.get(publicacion=publication)
        stored = origin.datos_iniciales['clasificacion_inicial']
        self.assertEqual(stored['confianza'], 'media')
        self.assertTrue(stored['marcas'])
        client = self.admin()
        listing = client.get('/api/gestion/convocatorias/', {})
        self.assertEqual(listing.status_code, 200, listing.data)
        row = next(item for item in listing.data['results'] if item['id'] == origin.convocatoria_id)
        self.assertEqual(row['origen_automatico'], {'publicacion_id': publication.pk, 'version_id': origin.version_id})
        offer = origin.convocatoria
        self.assertEqual(row['diagnostico']['pendientes_publicacion'], errores_publicacion(offer, estricto=False))
        self.assertEqual(row['diagnostico']['faltan'], len(row['diagnostico']['pendientes_publicacion']))
        self.assertGreater(row['diagnostico']['faltan'], 0)
        for params in ({'confianza': 'media'}, {'orden': 'confianza'}):
            self.assertEqual(client.get('/api/gestion/convocatorias/', params).status_code, 400)
        # La publicación sigue bloqueada con sus reglas actuales.
        with self.assertRaises(ValidationError):
            publicar(offer)
        situation = client.get(f'/api/gestion/rastreo/publicaciones/{publication.pk}/').data['situacion']
        self.assertEqual((situation['tipo'], situation['convocatoria_id']), ('borrador', origin.convocatoria_id))
        self.assertNotIn('confianza', situation)

    def test_foreign_only_offer_has_no_draft_and_shows_clear_reason_in_crawl_tray(self):
        foreign = [{'nombre': 'Universidad extranjera sintética', 'rol': 'oferente', 'pais_codigo': 'US',
                    'pais_verificado': True, 'evidencia': 'La universidad extranjera ofrece la beca.'}]
        publication = self.capture(offerers=foreign)
        self.assertFalse(BorradorRastreo.objects.filter(publicacion=publication).exists())
        incident = Incidencia.objects.get(publicacion=publication, codigo='CANDIDATO_FUERA_ALCANCE')
        self.assertEqual(incident.detalle, 'Descartada: oferente extranjero (Universidad extranjera sintética), sin entidad ecuatoriana.')
        client = self.admin()
        listed = client.get('/api/gestion/rastreo/publicaciones/').data['results']
        situation = next(row['situacion'] for row in listed if row['id'] == publication.pk)
        self.assertEqual((situation['tipo'], situation['motivo']), ('descartada', incident.detalle))
        detail = client.get(f'/api/gestion/rastreo/publicaciones/{publication.pk}/').data['situacion']
        self.assertEqual((detail['tipo'], detail['motivo']), ('descartada', incident.detalle))
        self.assertEqual(Publicacion.objects.filter(pk=publication.pk, convocatoria__isnull=True).count(), 1)
