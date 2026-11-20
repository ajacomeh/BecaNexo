"""Llenado automático del borrador al crearlo y comando `completar_borradores`. HTTP simulado; base aislada."""
import io
import json

from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from convocatorias.comparacion import evaluar_requisito
from convocatorias.models import BorradorRastreo, Evento, Institucion, Requisito, TipoRequisito
from convocatorias.services import errores_publicacion, publicas
from notificaciones.models import Notificacion
from perfiles.models import Pais
from . import test_auto_borradores as auto_tests
from . import tests as base
from .auto_borradores import latest_version
from .llenado import evidencia_visible, llenar_origen

TEXTO_REQUISITOS = ('- Ser ciudadano ecuatoriano\n- Estar en pleno goce de sus derechos\n'
                    '- No tener prohibición vigente para postular a becas')


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class LlenadoAutomaticoTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    capture = auto_tests.AutoDraftTests.capture

    def borrador(self, oferente=True):
        Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        publication = self.capture(offerer=oferente)
        return BorradorRastreo.objects.get(publicacion=publication)

    def con_requisitos(self, origin, texto=TEXTO_REQUISITOS):
        version = latest_version(origin.publicacion)
        version.datos_extraidos['requisitos']['texto_original'] = texto
        return version

    def test_creacion_escribe_solo_con_evidencia_sin_validar_ni_publicar(self):
        origin = self.borrador(oferente=False)
        offer = origin.convocatoria
        self.assertTrue(offer.url_oficial)
        self.assertEqual(offer.estado, 'borrador')
        self.assertFalse(publicas().filter(pk=offer.pk).exists())
        self.assertFalse(offer.requisitos.filter(validado=True).exists())
        self.assertEqual(Evento.objects.filter(convocatoria=offer).count(), 0)
        self.assertEqual(Notificacion.objects.filter(convocatoria=offer).count(), 0)
        registro = origin.datos_iniciales['llenado_automatico']
        self.assertIn('url_oficial', [item['campo'] for item in registro['campos']])
        self.assertIsNone(registro.get('error'))
        self.assertIsNone(offer.institucion_id)

    def test_requisitos_se_crean_activos_sin_validar_y_con_procedencia(self):
        origin = self.borrador()
        version = self.con_requisitos(origin)
        resumen = llenar_origen(origin, version)
        origin.refresh_from_db()
        self.assertIsNone(resumen['error'])
        requisitos = origin.convocatoria.requisitos.all()
        self.assertTrue(requisitos.exists())
        self.assertTrue(all(r.activo and not r.validado for r in requisitos))
        visibles = evidencia_visible(origin)['registros']
        self.assertEqual({item['id'] for item in visibles if item['modelo'] == 'requisitos'}, {r.pk for r in requisitos})
        self.assertTrue(all(item['texto'] and item['seccion'] for item in visibles))
        self.assertEqual(Evento.objects.filter(convocatoria=origin.convocatoria).count(), 0)

    def test_idempotente_y_respeta_lo_que_el_administrador_cambio_o_borro(self):
        origin = self.borrador()
        version = self.con_requisitos(origin)
        llenar_origen(origin, version)
        offer = origin.convocatoria
        antes = list(offer.requisitos.order_by('pk').values_list('pk', 'texto_original'))
        self.assertGreaterEqual(len(antes), 2)
        repetido = llenar_origen(origin, version)
        self.assertEqual(repetido['creados'], [])
        self.assertEqual(list(offer.requisitos.order_by('pk').values_list('pk', 'texto_original')), antes)
        editado, borrado = offer.requisitos.order_by('pk')[0], offer.requisitos.order_by('pk')[1]
        editado.texto_original = 'Texto corregido por el administrador'
        editado.save()
        borrado_id = borrado.pk
        borrado.delete()
        offer.url_oficial = 'https://administrador.example/oficial'
        offer.save(update_fields=['url_oficial'])
        llenar_origen(origin, version)
        offer.refresh_from_db()
        self.assertEqual(offer.url_oficial, 'https://administrador.example/oficial')
        self.assertFalse(Requisito.objects.filter(pk=borrado_id).exists())
        self.assertEqual(offer.requisitos.count(), len(antes) - 1)
        self.assertEqual(Requisito.objects.get(pk=editado.pk).texto_original, 'Texto corregido por el administrador')
        offer.url_oficial = ''
        offer.save(update_fields=['url_oficial'])
        llenar_origen(origin, version)
        offer.refresh_from_db()
        self.assertEqual(offer.url_oficial, '', 'un campo vaciado por el administrador no se reescribe')

    def test_requisitos_externos_y_no_validados_siguen_en_desconocido(self):
        origin = self.borrador()
        offer = origin.convocatoria
        otro = TipoRequisito.objects.get(codigo='OTRO')
        sin_validar = Requisito.objects.create(convocatoria=offer, tipo_requisito=otro, texto_original='No tener sanciones',
                                               valor_estructurado={'descripcion': 'No tener sanciones'},
                                               modo_comprobacion='entidad_oferente', obligatorio=True, validado=False, activo=True)
        externo_validado = Requisito.objects.create(convocatoria=offer, tipo_requisito=otro, texto_original='Carta de la entidad',
                                                    valor_estructurado={'descripcion': 'Carta de la entidad'},
                                                    modo_comprobacion='entidad_oferente', obligatorio=True, validado=True, activo=True)
        for requisito in (sin_validar, externo_validado):
            resultado = evaluar_requisito(requisito, None, [], {})
            self.assertEqual(resultado['resultado'], 'desconocido')
            self.assertTrue(resultado['comprobacion_externa'])

    def test_no_se_publica_ni_se_notifica_y_no_queda_aviso_de_precarga(self):
        origin = self.borrador(oferente=False)
        version = self.con_requisitos(origin)
        llenar_origen(origin, version)
        offer = origin.convocatoria
        offer.refresh_from_db()
        self.assertEqual((offer.estado, offer.revision), ('borrador', 'pendiente'))
        pendientes = errores_publicacion(offer, estricto=False)
        self.assertTrue(pendientes)
        self.assertFalse(any('precargadas' in texto for texto in pendientes))
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_origen_devuelve_para_publicar_y_evidencia_y_los_endpoints_de_precarga_no_existen(self):
        origin = self.borrador()
        admin = APIClient(enforce_csrf_checks=True)
        admin.force_login(self.actor)
        token = admin.get('/api/auth/csrf/').data['csrfToken']
        offer_id = origin.convocatoria_id
        respuesta = admin.get(f'/api/gestion/rastreo/convocatorias/{offer_id}/origen/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['para_publicar'], errores_publicacion(origin.convocatoria, estricto=False))
        self.assertEqual(set(respuesta.data['evidencia']), {'campos', 'registros'})
        for prohibido in ('candidatos_editables', 'bloqueos_actuales', 'pendientes_iniciales', 'precarga', 'datos_iniciales'):
            self.assertNotIn(prohibido, respuesta.data)
        for ruta in ('precargar', 'precarga/resolver'):
            self.assertEqual(admin.post(f'/api/gestion/rastreo/convocatorias/{offer_id}/{ruta}/', {}, format='json',
                                        HTTP_X_CSRFTOKEN=token).status_code, 404)

    def test_comando_simula_sin_guardar_y_aplica_con_la_opcion(self):
        origin = self.borrador()
        offer = origin.convocatoria
        # Estado previo al llenado: borrador sin registros ni libro, como los borradores 22-25.
        offer.requisitos.all().delete()
        offer.beneficios.all().delete()
        offer.opciones.all().delete()
        offer.url_oficial = ''
        offer.save(update_fields=['url_oficial'])
        datos = dict(origin.datos_iniciales)
        datos.pop('llenado_automatico', None)
        origin.datos_iniciales = datos
        origin.save(update_fields=['datos_iniciales'])
        salida = io.StringIO()
        call_command('completar_borradores', '--convocatoria', str(offer.pk), stdout=salida)
        informe = json.loads(salida.getvalue())
        self.assertEqual(informe['modo'], 'simulacion')
        self.assertTrue(informe['borradores'][0]['campos'])
        offer.refresh_from_db()
        self.assertEqual(offer.url_oficial, '')
        origin.refresh_from_db()
        self.assertNotIn('llenado_automatico', origin.datos_iniciales)
        salida = io.StringIO()
        call_command('completar_borradores', '--convocatoria', str(offer.pk), '--aplicar', stdout=salida)
        self.assertEqual(json.loads(salida.getvalue())['modo'], 'aplicar')
        offer.refresh_from_db()
        self.assertTrue(offer.url_oficial)
        self.assertFalse(offer.requisitos.filter(validado=True).exists())
        self.assertEqual(Evento.objects.filter(convocatoria=offer).count(), 0)
        self.assertEqual(Notificacion.objects.count(), 0)

    def con_texto(self, origin, descripcion, oferentes=None):
        version = latest_version(origin.publicacion)
        version.datos_extraidos['descripcion']['texto_original'] = descripcion
        version.datos_extraidos['oferentes'] = oferentes or []
        return version

    def test_entidad_ecuatoriana_no_registrada_se_crea_con_procedencia_y_sin_duplicar(self):
        origin = self.borrador(oferente=False)
        offer = origin.convocatoria
        offer.institucion = None
        offer.save(update_fields=['institucion'])
        version = self.con_texto(origin, 'Becas otorgadas por Universidad Politécnica del Ecuador para estudios de posgrado.')
        antes = Institucion.objects.count()
        llenar_origen(origin, version)
        offer.refresh_from_db()
        self.assertEqual(Institucion.objects.count(), antes + 1)
        creada = Institucion.objects.get(pk=offer.institucion_id)
        self.assertEqual((creada.nombre, creada.pais.codigo), ('Universidad Politécnica del Ecuador', 'EC'))
        self.assertIsNone(creada.url_oficial)
        entrada = next(c for c in origin.datos_iniciales['llenado_automatico']['campos'] if c['campo'] == 'institucion')
        self.assertTrue(entrada['entidad_creada'])
        self.assertIn('Universidad Politécnica del Ecuador', entrada['literal'])
        self.assertEqual(entrada['seccion'], 'Descripción')
        self.assertEqual(Evento.objects.filter(convocatoria=offer).count(), 0)
        # Idempotente: repetir no duplica; si el administrador la vacía, no se reasigna ni se recrea.
        llenar_origen(origin, version)
        offer.institucion = None
        offer.save(update_fields=['institucion'])
        llenar_origen(origin, version)
        offer.refresh_from_db()
        self.assertIsNone(offer.institucion_id)
        self.assertEqual(Institucion.objects.count(), antes + 1)

    def test_entidad_registrada_se_asigna_sin_crear_otra_y_no_pisa_la_elegida(self):
        origin = self.borrador(oferente=False)
        offer = origin.convocatoria
        offer.institucion = None
        offer.save(update_fields=['institucion'])
        existente = Institucion.objects.create(nombre='Universidad Politécnica del Ecuador', sector='publico', pais=self.pais_ec())
        version = self.con_texto(origin, 'Becas otorgadas por Universidad Politécnica del Ecuador.')
        antes = Institucion.objects.count()
        llenar_origen(origin, version)
        offer.refresh_from_db()
        self.assertEqual((offer.institucion_id, Institucion.objects.count()), (existente.pk, antes))
        elegida = Institucion.objects.create(nombre='Otra entidad elegida', sector='privado', pais=self.pais_ec())
        origin2 = self.borrador(oferente=False)
        origin2.convocatoria.institucion = elegida
        origin2.convocatoria.save(update_fields=['institucion'])
        llenar_origen(origin2, self.con_texto(origin2, 'Becas otorgadas por Universidad Politécnica del Ecuador.'))
        origin2.convocatoria.refresh_from_db()
        self.assertEqual(origin2.convocatoria.institucion_id, elegida.pk)

    def pais_ec(self):
        return Pais.objects.get(codigo='EC')

    def test_no_se_crea_entidad_extranjera_ambigua_ni_con_varios_candidatos(self):
        casos = {
            'extranjera': 'Becas otorgadas por Universidad de Zaragoza para estudios de posgrado.',
            'sin_evidencia': 'Becas otorgadas por Fundación Horizonte Austral para estudios.',
            'varias_ecuatorianas': 'Becas otorgadas por Universidad Politécnica del Ecuador en convenio con '
                                   'Universidad Técnica del Ecuador.',
            'solo_destinatarios': 'Becas para ciudadanos ecuatorianos que estudien en universidades de Ecuador.',
        }
        for nombre, texto in casos.items():
            origin = self.borrador(oferente=False)
            offer = origin.convocatoria
            offer.institucion = None
            offer.save(update_fields=['institucion'])
            antes = Institucion.objects.count()
            llenar_origen(origin, self.con_texto(origin, texto))
            offer.refresh_from_db()
            with self.subTest(nombre):
                self.assertIsNone(offer.institucion_id)
                self.assertEqual(Institucion.objects.count(), antes)
                self.assertTrue(origin.datos_iniciales['llenado_automatico'].get('entidad_omitida'))

    def test_entidad_registrada_por_sigla_cuando_la_ficha_la_nombra_con_su_objetivo(self):
        origin = self.borrador(oferente=False)
        offer = origin.convocatoria
        offer.institucion = None
        offer.save(update_fields=['institucion'])
        existente = Institucion.objects.create(nombre='Ministerio de Educación, Deporte y Cultura del Ecuador (MINEDEC)',
                                               sector='publico', pais=self.pais_ec())
        version = self.con_texto(origin, 'El Programa “Ecuador Productivo”, del Ministerio de Educación, Deporte y Cultura – '
                                         'MINEDEC tiene por objetivo la concesión de becas a personas naturales.')
        antes = Institucion.objects.count()
        llenar_origen(origin, version)
        offer.refresh_from_db()
        self.assertEqual((offer.institucion_id, Institucion.objects.count()), (existente.pk, antes))

    def test_una_ecuatoriana_con_extranjeras_nombradas_se_crea_y_el_titulo_con_ministerio_no_es_ambiguo(self):
        origin = self.borrador(oferente=False)
        offer = origin.convocatoria
        offer.institucion = None
        offer.save(update_fields=['institucion'])
        version = latest_version(origin.publicacion)
        version.datos_extraidos['titulo']['texto_original'] = (
            'Programa de Becas para Mujeres Ecuatorianas Universidad Europea – Ministerio de Gobierno del Ecuador')
        version.datos_extraidos['descripcion']['texto_original'] = 'Becas para estudiar en la Universidad Europea.'
        version.datos_extraidos['oferentes'] = []
        antes = Institucion.objects.count()
        llenar_origen(origin, version)
        offer.refresh_from_db()
        self.assertEqual(Institucion.objects.count(), antes + 1)
        self.assertEqual(offer.institucion.nombre, 'Ministerio de Gobierno del Ecuador')
        self.assertEqual(offer.institucion.sector, 'publico')

    def test_cartera_de_estado_solo_se_asigna_si_un_documento_nombra_a_la_entidad_con_papel_de_oferente(self):
        origin = self.borrador(oferente=False)
        offer = origin.convocatoria
        offer.institucion = None
        offer.save(update_fields=['institucion'])
        minedec = Institucion.objects.create(nombre='Ministerio de Educación, Deporte y Cultura del Ecuador (MINEDEC)',
                                             sector='publico', pais=self.pais_ec())
        version = self.con_texto(origin, 'No mantener una beca otorgada por esta Cartera de Estado.')
        llenar_origen(origin, version)
        offer.refresh_from_db()
        self.assertIsNone(offer.institucion_id, 'MINEDEC no se asigna por defecto')
        # Un fragmento de las bases en PDF de la misma versión la nombra como impulsora del programa.
        version.datos_extraidos['evidencia_pdf'] = {'documentos': [{'documento_id': 77, 'fragmentos': [{
            'texto_original': 'El programa es impulsado por el Ministerio de Educación, Deporte y Cultura del Ecuador (MINEDEC).',
            'procedencia': {'documento_id': 77, 'pagina': 3}}]}]}
        origin.datos_iniciales = {k: v for k, v in origin.datos_iniciales.items() if k != 'llenado_automatico'}
        origin.save(update_fields=['datos_iniciales'])
        llenar_origen(origin, version)
        offer.refresh_from_db()
        self.assertEqual(offer.institucion_id, minedec.pk)
        entrada = next(c for c in origin.datos_iniciales['llenado_automatico']['campos'] if c['campo'] == 'institucion')
        self.assertEqual((entrada['documento_id'], entrada['pagina'], entrada['seccion']), (77, 3, 'Bases en PDF'))
        self.assertIn('impulsado por el Ministerio', entrada['literal'])

    def test_enlace_oficial_es_la_ficha_y_las_urls_cargadas_no_conservan_puntuacion_final(self):
        from .llenado import campos_generales, limpiar_url
        self.assertEqual(limpiar_url('https://pusak.example/cas/login.'), 'https://pusak.example/cas/login')
        self.assertEqual(limpiar_url(' https://a.example/bases.pdf; '), 'https://a.example/bases.pdf')
        self.assertEqual(limpiar_url('https://a.example/x_(y)'), 'https://a.example/x_(y)')
        self.assertEqual(limpiar_url('https://a.example/x)'), 'https://a.example/x')
        evidencia = {'url_ficha': 'https://siau.example/beca/.', 'documento_id': 5, 'datos': {
            'enlaces_postulacion': [{'url': 'https://pusak.example/cas/login.'}],
            'enlaces_bases': [{'url': 'https://siau.example/uploads/bases.pdf.'}]}}
        campos = {c['campo']: c['valor'] for c in campos_generales({}, evidencia)}
        self.assertEqual(campos['url_oficial'], 'https://siau.example/beca/')
        self.assertEqual(campos['url_bases'], 'https://siau.example/uploads/bases.pdf')
        # Sin ficha utilizable no se usa el enlace de postulación como sustituto.
        evidencia['url_ficha'] = ''
        self.assertNotIn('url_oficial', {c['campo'] for c in campos_generales({}, evidencia)})

    def test_el_borrador_creado_carga_la_ficha_como_enlace_oficial_y_las_bases_como_antes(self):
        origin = self.borrador(oferente=False)
        offer = origin.convocatoria
        self.assertEqual(offer.url_oficial, origin.publicacion.url_original)
        self.assertNotIn('/cas/login', offer.url_oficial)
        self.assertFalse(offer.url_oficial.endswith('.'))
        self.assertTrue(offer.url_bases.startswith('https://'))
        self.assertFalse(offer.url_bases.endswith('.'))
