"""Toda publicación con «beca» en el título genera borrador privado; publicar sin entidad ecuatoriana exige confirmación.

HTTP simulado; escribe solo en la base de pruebas aislada.
"""
import io
import json

from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from convocatorias.models import BorradorRastreo, Evento, Institucion, OpcionEstudio
from convocatorias.services import publicas
from perfiles.models import Pais
from .auto_borradores import MARCA_OFERENTE_NO_EC
from .models import Publicacion
from . import test_candidate_transition as transicion
from .test_candidate_transition import TITLE, URL, fiche


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class BorradorTodaPublicacionTests(TransactionTestCase):
    setUpBase = transicion.CandidateTransitionTests.setUpBase
    source = transicion.CandidateTransitionTests.source
    setUp = transicion.CandidateTransitionTests.setUp
    execute = transicion.CandidateTransitionTests.execute

    def admin(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.actor)
        token = client.get('/api/auth/csrf/').data['csrfToken']
        return client, token

    def publicable(self, offer):
        """Completa los mínimos que no dependen de la entidad: enlace oficial y una opción activa."""
        client, token = self.admin()
        response = client.patch(f'/api/gestion/convocatorias/{offer.pk}/', {'url_oficial': URL, 'descripcion': offer.descripcion or 'Descripción de prueba.'},
                                format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.data)
        if not offer.opciones.filter(activa=True).exists():
            option = OpcionEstudio.objects.create(convocatoria=offer, nivel='grado', modalidad='virtual')
            option.paises.add(Pais.objects.get(codigo='EC'))
        return client, token

    def test_oferente_extranjero_crea_borrador_con_marca_sin_registrar_la_entidad(self):
        entidades = Institucion.objects.count()
        run, _ = self.execute(fiche(foreign=True))
        self.assertEqual(run.estado, 'finalizada')
        origin = BorradorRastreo.objects.get(publicacion__url_normalizada=URL)
        offer = origin.convocatoria
        self.assertIsNone(offer.institucion_id)
        self.assertEqual(Institucion.objects.count(), entidades)  # no se registra la entidad extranjera
        self.assertTrue(origin.datos_iniciales['oferente_no_ecuatoriano'])
        # La ficha sintética no nombra una entidad reconocible: sin nombre detectado («Oferente por confirmar»).
        self.assertEqual(origin.datos_iniciales['oferente_detectado'], '')
        self.assertTrue(any(MARCA_OFERENTE_NO_EC in mark for mark in origin.datos_iniciales['clasificacion_inicial']['marcas']))
        self.assertTrue(any('Publicar bajo mi responsabilidad' in item for item in origin.pendientes_iniciales))
        self.assertFalse(publicas().filter(pk=offer.pk).exists())
        client, _ = self.admin()
        situation = client.get('/api/gestion/rastreo/publicaciones/').data['results'][0]['situacion']
        self.assertEqual((situation['tipo'], situation['oferente_no_ecuatoriano'], situation['descartado']), ('borrador', True, False))
        self.assertGreater(situation['pendientes'], 0)

    def test_beca_nacional_sin_entidad_asignada_crea_borrador_sin_marca(self):
        title = 'Programa de Becas Nacionales de prueba'
        self.candidate.titulo_publico = title
        self.candidate.save(update_fields=['titulo_publico'])
        html = fiche(requirements=False, deadline=False).replace(TITLE.encode(), title.encode()).replace(
            b'Universidad Ecuatoriana Demo ofrece esta beca a estudiantes ecuatorianos.',
            b'Este programa apoya estudios de grado; la institucion oferente debe verificarse.')
        self.execute(html)
        origin = BorradorRastreo.objects.get(publicacion__url_normalizada=URL)
        self.assertIsNone(origin.convocatoria.institucion_id)
        self.assertFalse(origin.datos_iniciales['oferente_no_ecuatoriano'])
        client, token = self.publicable(origin.convocatoria)
        detail = client.get(f'/api/gestion/convocatorias/{origin.convocatoria_id}/').data
        self.assertEqual(detail['aviso_oferente'], 'Esta beca no tiene una entidad oferente ecuatoriana asignada')
        self.assertFalse(detail['oferente_externo']['no_ecuatoriano'])

    def test_publicar_sin_entidad_exige_confirmacion_y_la_registra(self):
        self.execute(fiche(foreign=True))
        offer = BorradorRastreo.objects.get(publicacion__url_normalizada=URL).convocatoria
        client, token = self.publicable(offer)
        sin = client.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(sin.status_code, 400, sin.data)
        self.assertIn('Esta beca no corresponde a una entidad oferente ecuatoriana', str(sin.data['detail']))
        self.assertTrue(sin.data['requiere_confirmacion_oferente'])
        self.assertFalse(publicas().filter(pk=offer.pk).exists())
        invalido = client.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {'confirmar_oferente_no_ecuatoriano': 'sí'},
                               format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(invalido.status_code, 400)
        con = client.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {'confirmar_oferente_no_ecuatoriano': True},
                          format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(con.status_code, 200, con.data)
        self.assertTrue(publicas().filter(pk=offer.pk).exists())
        evento = Evento.objects.filter(convocatoria=offer, accion='confirmar_publicacion').get()
        self.assertTrue(evento.cambios['confirmacion_sin_entidad'])
        self.assertIsNone(evento.cambios['entidad'])
        self.assertIn('Publicar bajo mi responsabilidad', evento.cambios['texto_confirmacion'])
        public = APIClient().get(f'/api/becas/{offer.pk}/').data
        self.assertIsNone(public['institucion'])
        self.assertTrue(public['oferente_externo']['no_ecuatoriano'])
        self.assertIsNone(public['oferente_externo']['nombre'])  # se muestra «Oferente por confirmar»

    def test_descartar_y_restaurar_borrador_quedan_auditados(self):
        self.execute(fiche(foreign=True))
        offer = BorradorRastreo.objects.get(publicacion__url_normalizada=URL).convocatoria
        client, token = self.publicable(offer)
        descartar = client.post(f'/api/gestion/convocatorias/{offer.pk}/descartar/', {}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(descartar.status_code, 200, descartar.data)
        self.assertTrue(descartar.data['descartado'])
        self.assertEqual(client.post(f'/api/gestion/convocatorias/{offer.pk}/descartar/', {}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 400)
        bloqueada = client.post(f'/api/gestion/convocatorias/{offer.pk}/publicar/', {'confirmar_oferente_no_ecuatoriano': True},
                                format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(bloqueada.status_code, 400)
        self.assertIn('descartado', str(bloqueada.data['detail']))
        situation = client.get('/api/gestion/rastreo/publicaciones/').data['results'][0]['situacion']
        self.assertTrue(situation['descartado'])
        restaurar = client.post(f'/api/gestion/convocatorias/{offer.pk}/restaurar/', {}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(restaurar.status_code, 200, restaurar.data)
        self.assertFalse(restaurar.data['descartado'])
        self.assertEqual(list(Evento.objects.filter(convocatoria=offer, accion__in=['descartar_borrador', 'restaurar_borrador'])
                              .order_by('id').values_list('accion', 'actor_id')),
                         [('descartar_borrador', self.actor.pk), ('restaurar_borrador', self.actor.pk)])

    def test_exclusion_expresa_de_ecuatorianos_no_crea_borrador_ni_en_el_backfill(self):
        html = fiche(foreign=True).replace('Ser ciudadano ecuatoriano.'.encode(), 'No pueden postular ciudadanos ecuatorianos.'.encode())
        run, _ = self.execute(html)
        self.assertFalse(BorradorRastreo.objects.exists())
        incident = run.incidencias.get(codigo='CANDIDATO_FUERA_ALCANCE')
        self.assertEqual(incident.detalle, 'Descartada: la ficha excluye expresamente a ciudadanos ecuatorianos.')
        out = io.StringIO()
        call_command('crear_borradores_pendientes', '--aplicar', stdout=out)
        informe = json.loads(out.getvalue())
        self.assertEqual(informe['total_creados'], 0)
        self.assertEqual(informe['sin_borrador'][0]['motivo'], 'Descartada: la ficha excluye expresamente a ciudadanos ecuatorianos.')
        self.assertFalse(BorradorRastreo.objects.exists())

    def test_ficha_sin_destinatarios_especificados_sigue_creando_borrador_con_dato_pendiente(self):
        html = fiche(foreign=True).replace('<ol><li>Ser ciudadano ecuatoriano.</li></ol>'.encode(), '<ol><li>Tener título de grado.</li></ol>'.encode())
        self.execute(html)
        origin = BorradorRastreo.objects.get(publicacion__url_normalizada=URL)
        marcas = origin.datos_iniciales['clasificacion_inicial']['marcas']
        self.assertIn('Participación de ciudadanos ecuatorianos por confirmar en las bases.', marcas)
        self.assertTrue(any('Confirmar en las bases si ciudadanos ecuatorianos pueden participar.' == item for item in origin.pendientes_iniciales))

    def test_backfill_idempotente_simula_aplica_y_no_toca_borradores_existentes(self):
        with override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=False):
            self.execute(fiche(foreign=True))
        publication = Publicacion.objects.get(url_normalizada=URL)
        self.assertFalse(BorradorRastreo.objects.exists())

        def correr(*args):
            out = io.StringIO()
            call_command('crear_borradores_pendientes', *args, stdout=out)
            return json.loads(out.getvalue())

        simulacion = correr()
        self.assertEqual((simulacion['modo'], simulacion['total_creados']), ('simulacion', 1))
        self.assertFalse(BorradorRastreo.objects.exists())  # la simulación se revierte
        aplicado = correr('--aplicar')
        self.assertEqual(aplicado['total_creados'], 1)
        self.assertTrue(aplicado['creados'][0]['oferente_no_ecuatoriano'])
        origin = BorradorRastreo.objects.get(publicacion=publication)
        antes = (origin.convocatoria.version, origin.convocatoria.titulo)
        repetido = correr('--aplicar')
        self.assertEqual((repetido['total_creados'], repetido['omitidas']), (0, 1))
        origin.convocatoria.refresh_from_db()
        self.assertEqual((origin.convocatoria.version, origin.convocatoria.titulo), antes)

    def test_incidencia_de_revision_por_destinatarios_muestra_su_motivo_real(self):
        from .auto_borradores import MOTIVO_ELEGIBILIDAD
        html = fiche(foreign=True).replace('<ol><li>Ser ciudadano ecuatoriano.</li></ol>'.encode(), '<ol><li>Tener título de grado.</li></ol>'.encode())
        run, _ = self.execute(html)
        incidencia = run.incidencias.get(codigo='BORRADOR_REVISION_PENDIENTE')
        self.assertEqual(incidencia.gravedad, 'aviso')
        self.assertEqual(incidencia.detalle, MOTIVO_ELEGIBILIDAD)
        self.assertNotIn('oferente', incidencia.detalle.lower())
        # El motivo del oferente sigue en su propia marca del borrador, sin mezclarse.
        marcas = BorradorRastreo.objects.get(publicacion__url_normalizada=URL).datos_iniciales['clasificacion_inicial']['marcas']
        self.assertIn(MOTIVO_ELEGIBILIDAD, marcas)
        self.assertTrue(any(MARCA_OFERENTE_NO_EC in marca for marca in marcas))

    def test_con_destinatarios_confirmados_no_hay_incidencia_y_el_motivo_del_oferente_se_conserva(self):
        from .auto_borradores import classify_candidate, motivo_revision
        run, _ = self.execute(fiche(foreign=True))
        self.assertFalse(run.incidencias.filter(codigo='BORRADOR_REVISION_PENDIENTE').exists())
        origin = BorradorRastreo.objects.get(publicacion__url_normalizada=URL)
        motivo = origin.datos_iniciales['clasificacion_inicial']['motivo']
        self.assertTrue(motivo.startswith('Borrador privado:'), motivo)
        self.assertNotIn('ciudadanos ecuatorianos por confirmar', motivo)
        # Si la ficha no es apta, el motivo de la incidencia es el de la clasificación, tal cual.
        evaluacion = classify_candidate(origin.publicacion, origin.version)
        self.assertEqual(motivo_revision({**evaluacion, 'estado': 'pendiente'}), evaluacion['motivo'])
        self.assertIsNone(motivo_revision({**evaluacion, 'estado': 'apta', 'elegibilidad': 'confirmada'}))
