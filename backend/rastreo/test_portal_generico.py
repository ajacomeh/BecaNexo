"""Portales ficticios y red simulada; escrituras solo en la base aislada autorizada."""
import tempfile
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from convocatorias.models import BorradorRastreo, Institucion
from perfiles.models import Pais
from .models import Fuente, Incidencia, Publicacion, Revision
from .portal_fuentes import extract_section, generic_portal, portal_for_source, sections
from .services import register_generic_portal, verify_generic_access, run_manual, set_portal_active, set_frequency


HOST = 'becas.universidad.edu.ec'
SEED = f'https://{HOST}/becas/'
INDEX = b'<html><h1>Becas</h1><a href="/becas/listado">Becas disponibles</a></html>'
FICHE = (b'<html><h1>Beca de movilidad para ecuatorianos</h1>'
         b'<p>Universidad ecuatoriana sintetica ofrece esta beca a ciudadanos ecuatorianos.</p><h2>Requisitos</h2>'
         b'<p>Ser estudiante activo y ciudadano ecuatoriano.</p>'
         b'<p>Cierre: 12 de noviembre de 2027</p></html>')


class GenericContractTests(SimpleTestCase):
    def test_numbered_call_and_nested_document_heading(self):
        portal = generic_portal('Universidad de las Artes',
            'https://www.uartes.edu.ec/sitio/becas-pregrado/', 'www.uartes.edu.ec', verified=True)
        html = ('<html><h2>21ª Convocatoria de Becas de Pregrado</h2>'
                '<p>La convocatoria estará abierta desde el 27 de agosto hasta el 25 de septiembre de 2026. '
                'El monto de la beca será USD 750.</p>'
                '<h4><a href="/sitio/bases.pdf">21ª Convocatoria de Becas</a></h4>'
                '<h3>Documentación Habilitante</h3><p>Consulte las bases.</p></html>').encode()
        found = sections(html, portal)
        self.assertEqual(len(found), 1)
        item = extract_section({'url': portal.indice, 'consulta_utc': '2026-11-14T12:00:00Z',
                                'contenido': html}, portal, found[0])
        self.assertEqual(item['cierre']['fecha'], '2026-09-25')
        self.assertEqual(item['vigencia_al_consultar'], 'vencida')
        self.assertIn('USD 750', item['beneficio']['texto_original'])
        self.assertEqual(item['enlaces_bases'][0]['url'], 'https://www.uartes.edu.ec/sitio/bases.pdf')

    def test_general_call_heading_is_not_an_individual_opportunity(self):
        portal = generic_portal('Universidad', SEED, HOST, verified=True)
        html = b'<html><h2>Convocatoria de Becas</h2><p>Conoce nuestros programas.</p></html>'
        self.assertEqual(sections(html, portal), [])

    def test_same_scholarship_in_distinct_student_groups_has_distinct_identity(self):
        portal = generic_portal('PUCE Ambato',
            'https://www.pucesa.edu.ec/financiamiento-y-becas/becas/', 'www.pucesa.edu.ec', verified=True)
        html = (b'<html><h2>Estudiantes de nuevo ingreso</h2>'
                b'<h2>Beca por Discapacidad</h2><p>Requisitos para nuevo ingreso.</p>'
                b'<h2>Estudiantes actuales</h2>'
                b'<h2>Beca por Discapacidad</h2><p>Requisitos para estudiantes actuales.</p></html>')
        found = sections(html, portal)
        self.assertEqual(len(found), 2)
        self.assertNotEqual(found[0].identidad, found[1].identidad)
        self.assertNotEqual(found[0].texto, found[1].texto)

    def test_fecha_de_apertura_del_grupo_no_se_atribuye_a_cada_beca(self):
        portal = generic_portal('PUCE Ambato',
            'https://www.pucesa.edu.ec/financiamiento-y-becas/becas/', 'www.pucesa.edu.ec', verified=True)
        html = (b'<h2>Estudiantes de nuevo ingreso</h2><p>Postulaciones abiertas desde el 01 de diciembre de 2026</p>'
                b'<h2>Beca por Solidaridad</h2><p>Requisitos para estudiantes nuevos.</p>'
                b'<h2>Estudiantes actuales</h2><h2>Beca por Solidaridad</h2><p>Requisitos distintos.</p>')
        found = sections(html, portal)
        self.assertEqual(len(found), 2)
        items = [extract_section({'url': portal.indice, 'consulta_utc': '2026-11-14T12:00:00Z', 'contenido': html}, portal, section)
                 for section in found]
        self.assertTrue(all(item['apertura'] is None and item['vigencia_al_consultar'] == 'desconocida' for item in items))
        direct = extract_section({'url': portal.indice, 'consulta_utc': '2026-11-14T12:00:00Z', 'contenido': html}, portal,
            type(found[0])(found[0].identidad, found[0].titulo,
                'Postulaciones abiertas desde el 01 de diciembre de 2026. Requisitos claros.', found[0].enlaces))
        self.assertEqual(direct['vigencia_al_consultar'], 'proxima')

    def test_closed_source_limits(self):
        portal = generic_portal('Universidad', SEED, HOST, 4, 2, 3, True)
        self.assertTrue(portal.generico)
        for seed, host in [('http://' + HOST + '/becas/', HOST),
                           ('https://other.edu.ec/becas/', HOST),
                           ('https://' + HOST + '/becas/?token=x', HOST),
                           ('https://localhost/becas/', 'localhost')]:
            with self.assertRaises(ValueError):
                generic_portal('Universidad', seed, host)
        with self.assertRaises(ValueError):
            generic_portal('Universidad', SEED, HOST, 13)


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class GenericRunTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_fusion_db')
        self.actor = get_user_model().objects.create_user(email='generic-admin@example.com', nombre='Admin', rol='administrador')
        self.user = get_user_model().objects.create_user(email='generic-user@example.com', nombre='User')
        ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        Institucion.objects.create(nombre='Universidad ecuatoriana sintetica', sector='publico', pais=ec)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        storage = override_settings(RASTREO_STORAGE_ROOT=temp.name)
        storage.enable()
        self.addCleanup(storage.disable)

    def register(self, verified=True, max_pages=8):
        return register_generic_portal(self.actor.pk, 'Universidad sintética', SEED, HOST,
            'Acceso público y robots verificados en entorno simulado',
            max_pages=max_pages, access_verified=verified)[0]

    def test_generic_source_accepts_twelve_hours_and_rejects_less(self):
        source = self.register()
        self.assertEqual(source.frecuencia_min, 720)
        self.assertTrue(portal_for_source(source))
        with self.assertRaises(ValidationError):
            set_frequency(source.pk, self.actor.pk, 'Intervalo demasiado corto', 719)
        source, changed = set_frequency(source.pk, self.actor.pk, 'Ensayo de frecuencia mayor', 1440)
        self.assertTrue(changed)
        source, changed = set_frequency(source.pk, self.actor.pk, 'Volver a doce horas', 720)
        self.assertTrue(changed)
        self.assertTrue(portal_for_source(source))

    def test_inactive_until_access_is_confirmed_and_audited(self):
        with self.assertRaises(ValidationError):
            register_generic_portal(self.user.pk, 'Universidad', SEED, HOST, 'Intento')
        source = self.register(False)
        self.assertFalse(source.activa)
        with self.assertRaises(ValidationError):
            set_portal_active(source.pk, self.actor.pk, 'Sin verificación', True)
        self.assertEqual(Revision.objects.filter(fuente=source).count(), 1)
        with patch('convocatorias.siau_red.Downloader.once') as network:
            self.assertEqual(run_manual(source.pk, self.actor.pk, uuid.uuid4()).estado, 'omitida')
            network.assert_not_called()
        source, changed = verify_generic_access(source.pk, self.actor.pk,
            'Condiciones públicas y robots.txt revisados en el portal sintético')
        self.assertTrue(changed)
        self.assertFalse(source.activa)
        self.assertEqual(Revision.objects.filter(fuente=source).count(), 2)
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)

    def test_paginated_individual_sections_duplicate_news_and_incomplete(self):
        source = self.register()
        self.assertEqual(portal_for_source(source).max_profundidad, 2)
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        listing = (b'<html><h1>Becas</h1><a href="/becas/ficha">Beca movilidad</a>'
                   b'<a href="/becas/ficha">Beca repetida</a>'
                   b'<a href="/becas/noticia">Noticia de becas</a>'
                   b'<a href="/becas/incompleta">Beca sin datos</a>'
                   b'<h2>Beca de apoyo para ecuatorianos</h2><p>Universidad ecuatoriana sintetica ofrece esta beca.</p>'
                   b'<p>Requisitos: ser ciudadano ecuatoriano. Cierre: 12 de noviembre de 2027.</p>'
                   b'<h2>Beca de investigacion para ecuatorianos</h2><p>Universidad ecuatoriana sintetica ofrece esta beca.</p>'
                   b'<p>Requisitos: ser estudiante ecuatoriano. Cierre: 12 de noviembre de 2027.</p></html>')
        responses = {SEED: INDEX, f'https://{HOST}/becas/listado': listing,
                     f'https://{HOST}/becas/ficha': FICHE,
                     f'https://{HOST}/becas/noticia': b'<html><h1>Noticia de becas</h1><p>Ganadores.</p></html>',
                     f'https://{HOST}/becas/incompleta': b'<html><h1>Beca sin datos</h1><p>Informaci\xc3\xb3n pendiente.</p></html>'}
        def network(url):
            if url == f'https://{HOST}/robots.txt':
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /privado/\n'
            self.assertIn(url, responses)
            return 200, {'content-type': 'text/html'}, responses[url]
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(run.estado, 'finalizada')
        self.assertEqual(Publicacion.objects.filter(fuente=source).count(), 4)
        self.assertEqual(BorradorRastreo.objects.filter(publicacion__fuente=source).count(), 3)
        self.assertTrue(Incidencia.objects.filter(fuente=source, codigo='CANDIDATO_PENDIENTE').exists())
        self.assertTrue(Incidencia.objects.filter(fuente=source, codigo='CANDIDATO_DESCARTADO').exists())
        self.assertFalse(Publicacion.objects.filter(fuente=source, url_original__endswith='noticia').exists())

    def test_puce_style_single_page_builds_private_draft_and_semantic_candidates(self):
        """La URL institucional es solo identidad del fixture; toda respuesta HTTP es simulada."""
        from django.core.management import call_command
        from convocatorias.models import OpcionEstudio, Requisito, TipoRequisito
        from convocatorias.services import publicas
        from .auto_borradores import editable_candidates
        from rest_framework.test import APIClient

        seed = 'https://www.pucesa.edu.ec/financiamiento-y-becas/becas/'
        source, _ = register_generic_portal(self.actor.pk, 'PUCE Ambato', seed, 'www.pucesa.edu.ec',
            'Verificación sintética de acceso exclusivamente en la base aislada',
            max_pages=1, max_depth=0, max_cards=4, access_verified=True)
        self.assertFalse(source.activa)
        self.assertEqual(source.frecuencia_min, 720)
        set_portal_active(source.pk, self.actor.pk, 'Activación únicamente del fixture aislado', True)
        html = ('<html><h2>Estudiantes de nuevo ingreso</h2>'
            '<h3>Beca de mérito académico</h3>'
            '<p>PUCE Ambato ofrece esta beca a estudiantes ecuatorianos.</p>'
            '<h4>Requisitos</h4><p>Ser ciudadano ecuatoriano.</p>'
            '<p>Promedio mínimo de 8,5.</p><p>Cierre: 12 de noviembre de 2027.</p>'
            '<p>Cobertura parcial de matrícula.</p></html>').encode('utf-8')

        def network(url):
            if url == 'https://www.pucesa.edu.ec/robots.txt':
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /wp-admin/\n'
            self.assertEqual(url, seed)
            return 200, {'content-type': 'text/html'}, html

        key = uuid.uuid4()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as requested:
            run = run_manual(source.pk, self.actor.pk, key)
        run.refresh_from_db()
        self.assertEqual(requested.call_count, 2)
        self.assertEqual(run.estado, 'finalizada')
        with patch('convocatorias.siau_red.Downloader.once') as repeated_network:
            self.assertEqual(run_manual(source.pk, self.actor.pk, key).pk, run.pk)
            repeated_network.assert_not_called()
        publication = Publicacion.objects.get(fuente=source)
        origin = BorradorRastreo.objects.get(publicacion=publication)
        offer = origin.convocatoria
        self.assertEqual(offer.revision, 'pendiente')
        self.assertIsNone(offer.institucion_id)
        self.assertEqual(offer.url_oficial, '')
        self.assertEqual(origin.version.datos_extraidos['vigencia_al_consultar'], 'abierta')
        self.assertEqual(str(offer.cierre_dia), '2027-11-12')
        candidates = editable_candidates(origin.version)
        self.assertIn('NACIONALIDAD', [item['tipo_sugerido'] for item in candidates['requisitos']])
        self.assertIn('PROMEDIO', [item['tipo_sugerido'] for item in candidates['requisitos']])
        self.assertFalse(any(item['validado'] for item in candidates['requisitos']))
        self.assertEqual(candidates['otros_campos']['tipo_beca_literal'], 'mérito académico')
        self.assertEqual(candidates['otros_campos']['cobertura_tipo_sugerida'], 'parcial')
        self.assertEqual(candidates['otros_campos']['fechas']['cierre']['fecha'], '2027-11-12')
        self.assertEqual(candidates['opciones'], [])
        admin = APIClient()
        admin.force_login(self.actor)
        response = admin.get(f'/api/gestion/rastreo/convocatorias/{offer.pk}/origen/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['publicacion_id'], publication.pk)
        self.assertEqual(response.data['candidatos_editables']['requisitos'], candidates['requisitos'])
        self.assertFalse(admin.get('/api/becas/').data['count'])
        # La sugerencia no publica: el administrador completa y valida datos en la base aislada.
        guarded = APIClient(enforce_csrf_checks=True)
        guarded.force_login(self.actor)
        token = guarded.get('/api/auth/csrf/').data['csrfToken']
        path = f'/api/gestion/convocatorias/{offer.pk}/publicar/'
        self.assertEqual(guarded.post(path, {}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 400)
        offer.url_oficial = seed  # Ficha del fixture confirmada manualmente en este ensayo.
        offer.save(update_fields=['url_oficial'])
        ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        offer.institucion = Institucion.objects.create(nombre='PUCE Ambato de prueba', sector='privado', pais=ec)
        offer.save(update_fields=['institucion'])
        OpcionEstudio.objects.create(convocatoria=offer, nivel='grado', modalidad='presencial')
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        kind = TipoRequisito.objects.get(codigo='OTRO')
        Requisito.objects.create(convocatoria=offer, tipo_requisito=kind,
            texto_original='Condición sintética revisada por administrador', operador='externo',
            valor_estructurado={'descripcion': 'Condición sintética revisada por administrador'},
            modo_comprobacion='entidad_oferente', validado=True)
        self.assertEqual(guarded.post(path, {}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(publicas().filter(pk=offer.pk).count(), 1)
        self.assertEqual(guarded.get('/api/becas/').data['count'], 1)

    def test_page_limit_and_http_backoff(self):
        source = self.register(max_pages=1)
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        def network(url):
            if url.endswith('/robots.txt'):
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow:\n'
            return 200, {'content-type': 'text/html'}, INDEX
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as requested:
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(requested.call_count, 2)
        self.assertTrue(run.incidencias.filter(codigo='INDICE_LIMITE').exists())
        self.assertEqual(Publicacion.objects.filter(fuente=source).count(), 0)
        with patch('rastreo.services.next_due', return_value=None):
            with patch('convocatorias.siau_red.Downloader.once', side_effect=lambda url: (
                    (200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow:\n')
                    if url.endswith('/robots.txt') else (503, {'retry-after': '120'}, b''))):
                later = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        later.refresh_from_db()
        self.assertEqual(later.estado, 'fallida')
        self.assertTrue(later.incidencias.filter(codigo='REINTENTO_FUENTE').exists())

    def test_robots_blocks_generic_page_without_publication(self):
        source = self.register()
        set_portal_active(source.pk, self.actor.pk, 'Activación sintética', True)
        def network(url):
            if url.endswith('/robots.txt'):
                return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /becas/listado\n'
            self.assertEqual(url, SEED)
            return 200, {'content-type': 'text/html'}, INDEX
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as requested:
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        run.refresh_from_db()
        self.assertEqual(Publicacion.objects.filter(fuente=source).count(), 0)
        self.assertTrue(run.incidencias.filter(codigo='ROBOTS').exists())
        self.assertEqual(requested.call_count, 2)
