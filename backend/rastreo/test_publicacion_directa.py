"""Publicación con un solo clic de un borrador del rastreador. HTTP simulado; base aislada."""
import io
from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from convocatorias.comparacion import evaluar_requisito
from convocatorias.models import BorradorRastreo, Evento, Institucion, OpcionEstudio, Requisito, TipoRequisito
from convocatorias.services import TEXTO_CONFIRMACION, errores_publicacion, publicas
from notificaciones.models import Notificacion
from perfiles.models import Pais
from . import test_auto_borradores as auto_tests
from . import tests as base
from .auto_borradores import latest_version
from .llenado import llenar_origen

REQUISITOS = '- Ser ciudadano ecuatoriano\n- Estar en pleno goce de sus derechos'


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class PublicacionDirectaTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    capture = auto_tests.AutoDraftTests.capture

    def borrador(self, oferente=False):
        self.ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        publication = self.capture(offerer=oferente)
        origin = BorradorRastreo.objects.get(publicacion=publication)
        version = latest_version(publication)
        version.datos_extraidos['requisitos']['texto_original'] = REQUISITOS
        llenar_origen(origin, version)
        return origin

    def completar(self, origin, institucion=True):
        offer = origin.convocatoria
        if institucion:
            offer.institucion = Institucion.objects.create(nombre='Entidad ecuatoriana de prueba', sector='publico', pais=self.ec)
            offer.save(update_fields=['institucion'])
        opcion = OpcionEstudio.objects.create(convocatoria=offer, nivel='grado', modalidad='virtual')
        opcion.paises.add(self.ec)
        return offer

    def admin(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.actor)
        client.token = client.get('/api/auth/csrf/').data['csrfToken']
        return client

    def publicar(self, client, offer):
        return client.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {}, format='json', HTTP_X_CSRFTOKEN=client.token)

    def test_un_solo_clic_publica_valida_requisitos_y_registra_la_confirmacion(self):
        origin = self.borrador()
        offer = self.completar(origin)
        requisitos = list(offer.requisitos.filter(activo=True))
        self.assertTrue(requisitos)
        self.assertTrue(all(not r.validado for r in requisitos))
        self.assertEqual(errores_publicacion(offer, estricto=False), [])
        respuesta = self.publicar(self.admin(), offer)
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        offer.refresh_from_db()
        self.assertEqual((offer.revision, offer.activa), ('validada', True))
        self.assertFalse(offer.requisitos.filter(activo=True, validado=False).exists())
        evento = Evento.objects.get(convocatoria=offer, accion='confirmar_publicacion')
        self.assertEqual(evento.actor_id, self.actor.pk)
        self.assertEqual(evento.cambios['entidad']['id'], offer.institucion_id)
        self.assertEqual(evento.cambios['texto_confirmacion'], TEXTO_CONFIRMACION)
        self.assertEqual(sorted(evento.cambios['requisitos_validados']), sorted(r.pk for r in requisitos))
        self.assertTrue(evento.cambios['fecha'])
        self.assertTrue(Evento.objects.filter(convocatoria=offer, accion='publicar', actor=self.actor).exists())

    def test_sin_entidad_ecuatoriana_no_se_publica(self):
        origin = self.borrador()
        offer = self.completar(origin, institucion=False)
        client = self.admin()
        respuesta = self.publicar(client, offer)
        self.assertEqual(respuesta.status_code, 400)
        # Sin entidad ya no es un bloqueo duro: se exige la confirmación «Publicar bajo mi responsabilidad».
        self.assertIn('Publicar bajo mi responsabilidad', str(respuesta.data))
        self.assertTrue(respuesta.data['requiere_confirmacion_oferente'])
        extranjera = Institucion.objects.create(nombre='Universidad extranjera de prueba', sector='privado',
                                                pais=Pais.objects.get_or_create(codigo='US', defaults={'nombre': 'Estados Unidos'})[0])
        type(offer).objects.filter(pk=offer.pk).update(institucion=extranjera)
        self.assertEqual(self.publicar(client, offer).status_code, 400)
        self.assertFalse(publicas().filter(pk=offer.pk).exists())
        self.assertFalse(Evento.objects.filter(convocatoria=offer, accion='confirmar_publicacion').exists())
        self.assertFalse(offer.requisitos.filter(validado=True).exists())

    def test_lo_publicado_queda_en_catalogo_y_las_condiciones_externas_siguen_en_desconocido(self):
        origin = self.borrador()
        offer = self.completar(origin)
        offer.cierre_dia = None
        offer.cierre = timezone.now() + timedelta(days=30)
        offer.save(update_fields=['cierre', 'cierre_dia'])
        externo = Requisito.objects.create(
            convocatoria=offer, tipo_requisito=TipoRequisito.objects.get(codigo='OTRO'), texto_original='No tener sanciones',
            valor_estructurado={'descripcion': 'No tener sanciones'}, modo_comprobacion='entidad_oferente',
            operador='externo', obligatorio=True, validado=False, activo=True)
        respuesta = self.publicar(self.admin(), offer)
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        externo.refresh_from_db()
        self.assertTrue(externo.validado)
        resultado = evaluar_requisito(externo, None, [], {})
        self.assertEqual(resultado['resultado'], 'desconocido')
        self.assertTrue(resultado['comprobacion_externa'])
        publico = APIClient()
        detalle = publico.get(f'/api/becas/{offer.pk}/')
        self.assertEqual(detalle.status_code, 200)
        self.assertEqual(len(detalle.data['opciones']), offer.opciones.filter(activa=True).count())
        self.assertEqual(len(detalle.data['requisitos']), offer.requisitos.filter(activo=True).count())
        listado = publico.get('/api/becas/')
        self.assertIn(offer.pk, [row['id'] for row in listado.data['results']])

    def test_nada_se_publica_sin_la_accion_de_un_administrador(self):
        origin = self.borrador()
        offer = self.completar(origin)
        self.assertFalse(publicas().filter(pk=offer.pk).exists())
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertFalse(Evento.objects.filter(accion__in=('publicar', 'confirmar_publicacion')).exists())
        anonimo = APIClient(enforce_csrf_checks=True)
        token = anonimo.get('/api/auth/csrf/').data['csrfToken']
        self.assertIn(anonimo.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {}, format='json',
                                   HTTP_X_CSRFTOKEN=token).status_code, (401, 403))
        usuario = APIClient(enforce_csrf_checks=True)
        usuario.force_login(self.user)
        token = usuario.get('/api/auth/csrf/').data['csrfToken']
        self.assertEqual(usuario.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {}, format='json',
                                      HTTP_X_CSRFTOKEN=token).status_code, 403)
        offer.refresh_from_db()
        self.assertEqual(offer.revision, 'pendiente')
        self.assertFalse(offer.requisitos.filter(validado=True).exists())
        self.assertEqual(Notificacion.objects.count(), 0)
        # El llenado y el comando tampoco publican ni validan.
        call_command('completar_borradores', '--convocatoria', str(offer.pk), '--aplicar', stdout=io.StringIO())
        offer.refresh_from_db()
        self.assertEqual(offer.revision, 'pendiente')
        self.assertFalse(publicas().filter(pk=offer.pk).exists())

    def test_borrador_con_entidad_asignada_por_el_rastreador_se_publica_con_un_clic(self):
        self.ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        origin = BorradorRastreo.objects.get(publicacion=self.capture(offerer=False))
        offer = origin.convocatoria
        offer.institucion = None
        offer.save(update_fields=['institucion'])
        version = latest_version(origin.publicacion)
        version.datos_extraidos['descripcion']['texto_original'] = 'Becas otorgadas por Universidad Politécnica del Ecuador.'
        version.datos_extraidos['oferentes'] = []
        version.datos_extraidos['requisitos']['texto_original'] = REQUISITOS
        llenar_origen(origin, version)
        offer.refresh_from_db()
        self.assertIsNotNone(offer.institucion_id)
        opcion = OpcionEstudio.objects.create(convocatoria=offer, nivel='grado', modalidad='virtual')
        opcion.paises.add(self.ec)
        self.assertEqual(errores_publicacion(offer, estricto=False), [])
        self.assertEqual(self.publicar(self.admin(), offer).status_code, 200)
        self.assertTrue(publicas().filter(pk=offer.pk).exists())

    def test_varias_condiciones_academicas_sin_relacion_no_bloquean_y_la_comparacion_queda_en_desconocido(self):
        origin = self.borrador()
        offer = self.completar(origin)
        formacion = TipoRequisito.objects.get(codigo='FORMACION')
        for texto in ('Ser bachiller', 'Estar matriculada en una carrera de tercer nivel'):
            Requisito.objects.create(convocatoria=offer, tipo_requisito=formacion, texto_original=texto, operador='>=',
                                     valor_estructurado={'nivel_minimo': 'bachillerato'}, modo_comprobacion='dato_declarado',
                                     obligatorio=True, validado=False, activo=True)
        pendientes = errores_publicacion(offer, estricto=False)
        self.assertFalse(any('Unifica' in texto for texto in pendientes), pendientes)
