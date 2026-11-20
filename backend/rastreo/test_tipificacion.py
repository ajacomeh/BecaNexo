"""Tipificación estricta de requisitos, condición administrativa y retipificación. Base aislada, sin red."""
import io
import json

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from convocatorias.comparacion import agregar, evaluar_requisito
from convocatorias.models import BorradorRastreo, Convocatoria, Evento, Institucion, Requisito, TipoRequisito
from convocatorias.reglas import CONTRATOS, EXTERNOS, validar
from perfiles.models import Pais
from . import test_auto_borradores as auto_tests
from . import tests as base
from .auto_borradores import latest_version
from .estructura_semantica import interpretar_requisitos
from .llenado import complementar_con_bases, contenido_de_requisito, llenar_origen

ADMINISTRATIVAS = [
    'Persona natural en goce de derechos de participación ciudadana en el Ecuador.',
    'Ser persona natural en ejercicio de sus derechos de participación en el Ecuador.',
    'No contar con un título académico del mismo nivel de formación.',
    'No constar como persona beneficiaria incumplida de crédito educativo.',
    'No mantener la calidad vigente de persona becaria o beneficiaria de ayuda económica por esta cartera de Estado.',
    'No haber sido sancionada con la prohibición de postular por desistimiento de una beca otorgada por esta Cartera Estado.',
    'No haber sido sujeta a terminación anticipada por incumplimiento de obligaciones de un contrato de financiamiento de beca o ayuda académica de esta Cartera Estado.',
    'No estar cursando o por iniciar estudios en otros programas del mismo grado académico al que va a ser subvencionado con la beca.',
    'No haber obtenido un título de cuarto nivel del mismo grado académico al que se va a cursar (Especialización, Maestría o Maestría Tecnológica).',
    'Acreditar, conforme a los registros de la institución de educación superior en la que se encuentra cursando sus estudios, que no mantiene una beca vigente otorgada por dicha institución.',
]


def uno(texto):
    candidatos = interpretar_requisitos(texto, version_id=1, url=None)
    assert len(candidatos) == 1, candidatos
    return candidatos[0]


class TipificacionEstrictaTests(SimpleTestCase):
    def test_las_condiciones_repetidas_de_siau_son_condiciones_administrativas_literales(self):
        for texto in ADMINISTRATIVAS:
            with self.subTest(texto=texto[:60]):
                candidato = uno(texto)
                self.assertEqual((candidato['tipo_sugerido'], candidato['estado']), ('CONDICION_ADMINISTRATIVA', 'externa'))
                self.assertEqual(candidato['valor_sugerido'], {})

    def test_goce_de_derechos_nunca_se_convierte_en_nacionalidad(self):
        for texto in ADMINISTRATIVAS[:2]:
            self.assertNotEqual(uno(texto)['tipo_sugerido'], 'NACIONALIDAD')

    def test_nacionalidad_y_estudios_escritos_explicitamente_se_tipifican(self):
        for texto in ('Ser nacionalidad ecuatoriana', 'Ser ciudadano/a ecuatoriano/a', 'tener nacionalidad ecuatoriana'):
            with self.subTest(texto=texto):
                candidato = uno(texto)
                self.assertEqual((candidato['tipo_sugerido'], candidato['estado'], candidato['valor_sugerido']),
                                 ('NACIONALIDAD', 'identificada', {'codigos_pais': ['EC']}))
        self.assertEqual(uno('Ser Bachiller')['valor_sugerido'], {'nivel_minimo': 'bachillerato', 'estado_exigido': 'concluidos', 'titulo_obtenido': True})
        matricula = uno('Estar matriculada en una carrera de tercer nivel de grado de una universidad o escuela politécnica pública del país.')
        self.assertEqual((matricula['tipo_sugerido'], matricula['valor_sugerido']['niveles_admitidos']), ('FORMACION', ['grado']))

    def test_lo_que_el_contrato_no_admite_sin_inventar_queda_como_otra_condicion_externa(self):
        # Niveles técnico/tecnológico no existen en el perfil; el título «académico previo» no escribe su nivel.
        for texto in ('Ser estudiante regular de una carrera de tercer nivel técnico, tecnológico superior o tecnológico superior universitario',
                      'Haber sido admitido o estar cursando estudios de maestrías o especializaciones en universidades o escuelas politécnicas del país.',
                      'Contar con un título académico previo para cursar un programa de especialización, maestría o maestría tecnológica.',
                      'Haber sido admitida en la UE en el programa de preferencia.'):
            with self.subTest(texto=texto[:50]):
                candidato = uno(texto)
                self.assertEqual((candidato['tipo_sugerido'], candidato['estado']), ('OTRO', 'externa'))
        # Una negación de un título nunca se invierte en un requisito de formación.
        self.assertNotEqual(uno('No contar con un título académico del mismo nivel de formación.')['tipo_sugerido'], 'FORMACION')

    def test_lo_ambiguo_no_se_tipifica(self):
        for texto in ('Ser mujer en toda su diversidad', 'Pagar la reserva de plaza para asegurar el cupo'):
            self.assertEqual(uno(texto)['estado'], 'ambigua')


class CondicionAdministrativaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ec, _ = Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        cls.institucion = Institucion.objects.create(nombre='Entidad de prueba', sector='publico', pais=cls.ec)

    def test_el_tipo_se_registra_con_la_carga_de_catalogos_y_es_externo(self):
        tipo = TipoRequisito.objects.get(codigo='CONDICION_ADMINISTRATIVA')
        self.assertEqual(tipo.nombre, 'Condición administrativa')
        self.assertEqual(tipo.esquema_valor['operadores'], ['externo'])
        self.assertEqual(EXTERNOS, {'ACREDITACION', 'DOCUMENTO', 'OTRO', 'CONDICION_ADMINISTRATIVA'})
        validar('CONDICION_ADMINISTRATIVA', {'descripcion': 'No constar como incumplido'}, None, 'entidad_oferente', 'externo')
        with self.assertRaises(Exception):
            validar('CONDICION_ADMINISTRATIVA', {'descripcion': 'x'}, None, 'dato_declarado', 'externo')

    def test_la_comparacion_nunca_da_cumple_y_queda_por_confirmar(self):
        oferta = Convocatoria.objects.create(titulo='Prueba', institucion=self.institucion, clave_deduplicacion='a' * 64)
        evaluaciones = []
        for codigo in sorted(EXTERNOS):
            valor = {'OTRO': {'descripcion': 'x'}, 'CONDICION_ADMINISTRATIVA': {'descripcion': 'x'}, 'DOCUMENTO': {'documento': 'x'},
                     'ACREDITACION': {'certificados_admitidos': 'x'}}[codigo]
            requisito = Requisito.objects.create(convocatoria=oferta, tipo_requisito=TipoRequisito.objects.get(codigo=codigo),
                texto_original=f'Condición {codigo}', valor_estructurado=valor, operador=CONTRATOS[codigo][1],
                modo_comprobacion='entidad_oferente', obligatorio=True, validado=True, activo=True)
            resultado = evaluar_requisito(requisito, None, [], {})
            with self.subTest(codigo=codigo):
                self.assertEqual(resultado['resultado'], 'desconocido')
                self.assertTrue(resultado['comprobacion_externa'])
            evaluaciones.append(resultado)
        # Solo condiciones externas: no hay nada comparable, el agregado nunca es «cumple».
        self.assertEqual(agregar(evaluaciones), 'desconocido')


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=True)
class LlenadoYRetipificacionTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    capture = auto_tests.AutoDraftTests.capture

    def borrador(self, requisitos):
        Pais.objects.get_or_create(codigo='EC', defaults={'nombre': 'Ecuador'})
        call_command('cargar_catalogos_convocatorias', verbosity=0)
        origin = BorradorRastreo.objects.get(publicacion=self.capture(offerer=False))
        version = latest_version(origin.publicacion)
        version.datos_extraidos['requisitos']['texto_original'] = requisitos
        origin.datos_iniciales = {k: v for k, v in origin.datos_iniciales.items() if k != 'llenado_automatico'}
        origin.save(update_fields=['datos_iniciales'])
        origin.convocatoria.requisitos.all().delete()
        llenar_origen(origin, version)
        origin.refresh_from_db()
        return origin, version

    def test_el_llenado_crea_condiciones_administrativas_con_procedencia_sin_validar(self):
        origin, _ = self.borrador('No constar como persona beneficiaria incumplida de crédito educativo.\nSer nacionalidad ecuatoriana')
        tipos = dict(origin.convocatoria.requisitos.values_list('texto_original', 'tipo_requisito__codigo'))
        self.assertEqual(tipos['No constar como persona beneficiaria incumplida de crédito educativo.'], 'CONDICION_ADMINISTRATIVA')
        self.assertEqual(tipos['Ser nacionalidad ecuatoriana'], 'NACIONALIDAD')
        self.assertFalse(origin.convocatoria.requisitos.filter(validado=True).exists())
        administrativa = origin.convocatoria.requisitos.get(tipo_requisito__codigo='CONDICION_ADMINISTRATIVA')
        self.assertEqual((administrativa.modo_comprobacion, administrativa.valor_estructurado),
                         ('entidad_oferente', {'descripcion': 'No constar como persona beneficiaria incumplida de crédito educativo.'}))

    def test_un_requisito_eliminado_no_reaparece_aunque_cambie_su_tipificacion(self):
        origin, version = self.borrador('No constar como persona beneficiaria incumplida de crédito educativo.')
        origin.convocatoria.requisitos.all().delete()
        llenar_origen(origin, version)
        self.assertFalse(origin.convocatoria.requisitos.exists())

    def test_la_nacionalidad_de_la_ficha_y_la_de_las_bases_dan_un_solo_requisito(self):
        found = {'requisitos': interpretar_requisitos('Ser ciudadano/a ecuatoriano/a', version_id=1, url=None), 'otros_campos': {}}
        bases = [{'estado': 'extraido', 'documento_id': 4, 'url': None, 'parrafos': [
            {'texto': '1. Tener nacionalidad ecuatoriana.', 'pagina': 2, 'seccion_bases': 'requisitos', 'subseccion': '', 'elemento': True, 'encabezado': False}]}]
        complementar_con_bases(found, bases, 1)
        self.assertEqual([c['tipo_sugerido'] for c in found['requisitos']], ['NACIONALIDAD'])

    def preparar_legado(self, origin):
        """Simula un requisito creado por el llenado anterior como OTRO (huella del libro coherente)."""
        requisito = origin.convocatoria.requisitos.get(tipo_requisito__codigo='CONDICION_ADMINISTRATIVA')
        requisito.tipo_requisito = TipoRequisito.objects.get(codigo='OTRO')
        requisito.save(update_fields=['tipo_requisito'])
        libro = origin.datos_iniciales['llenado_automatico']
        for entrada in libro['registros']:
            if entrada['id'] == requisito.pk:
                entrada['contenido'] = contenido_de_requisito(requisito)
        origin.save(update_fields=['datos_iniciales'])
        return requisito

    def ejecutar(self, offer, *extra):
        salida = io.StringIO()
        call_command('retipificar_requisitos', '--convocatoria', str(offer.pk), *extra, stdout=salida)
        return json.loads(salida.getvalue())

    def test_retipificacion_simula_por_defecto_y_aplica_solo_lo_automatico_sin_editar(self):
        origin, _ = self.borrador('No constar como persona beneficiaria incumplida de crédito educativo.')
        requisito = self.preparar_legado(origin)
        offer = origin.convocatoria
        manual = Requisito.objects.create(convocatoria=offer, tipo_requisito=TipoRequisito.objects.get(codigo='OTRO'),
            texto_original='Ser nacionalidad ecuatoriana', valor_estructurado={'descripcion': 'Ser nacionalidad ecuatoriana'},
            operador='externo', modo_comprobacion='entidad_oferente', obligatorio=True, validado=False, activo=True)
        simulacion = self.ejecutar(offer)['convocatorias'][0]
        self.assertEqual([c['id'] for c in simulacion['cambiados']], [requisito.pk])
        self.assertEqual([(f['id'], f['a']) for f in simulacion['solo_informe']], [(manual.pk, 'NACIONALIDAD')])
        requisito.refresh_from_db()
        self.assertEqual(requisito.tipo_requisito.codigo, 'OTRO', 'la simulación no guarda')
        with self.assertRaises(CommandError):
            self.ejecutar(offer, '--aplicar')
        aplicado = self.ejecutar(offer, '--aplicar', '--actor-id', str(self.actor.pk))['convocatorias'][0]
        self.assertEqual([c['a'] for c in aplicado['cambiados']], ['CONDICION_ADMINISTRATIVA'])
        requisito.refresh_from_db()
        manual.refresh_from_db()
        self.assertEqual(requisito.tipo_requisito.codigo, 'CONDICION_ADMINISTRATIVA')
        self.assertEqual(manual.tipo_requisito.codigo, 'OTRO', 'lo creado a mano no se toca')
        self.assertFalse(requisito.validado)
        evento = Evento.objects.get(convocatoria=offer, accion='requisitos_retipificar')
        self.assertEqual(evento.actor_id, self.actor.pk)
        origin.refresh_from_db()
        entrada = next(e for e in origin.datos_iniciales['llenado_automatico']['registros'] if e['id'] == requisito.pk)
        self.assertEqual(entrada['retipificaciones'][0]['a'], 'CONDICION_ADMINISTRATIVA')
        self.assertEqual(entrada['contenido'], contenido_de_requisito(requisito))
        # Idempotente: repetir no cambia nada más ni vuelve a auditar.
        segundo = self.ejecutar(offer, '--aplicar', '--actor-id', str(self.actor.pk))['convocatorias'][0]
        self.assertEqual(segundo['cambiados'], [])
        self.assertEqual(Evento.objects.filter(convocatoria=offer, accion='requisitos_retipificar').count(), 1)

    def test_no_pisa_lo_editado_ni_lo_validado_ni_las_publicadas(self):
        origin, _ = self.borrador('No constar como persona beneficiaria incumplida de crédito educativo.')
        requisito = self.preparar_legado(origin)
        offer = origin.convocatoria
        requisito.texto_original += ' (texto revisado por el administrador)'
        requisito.save(update_fields=['texto_original'])
        informe = self.ejecutar(offer, '--aplicar', '--actor-id', str(self.actor.pk))['convocatorias'][0]
        self.assertEqual(informe['cambiados'], [])
        self.assertIn('editó', informe['solo_informe'][0]['motivo'])
        requisito.refresh_from_db()
        self.assertEqual(requisito.tipo_requisito.codigo, 'OTRO')
        # Validado: solo informe (se restaura el texto y la huella para aislar la condición de validación).
        Requisito.objects.filter(pk=requisito.pk).update(texto_original=requisito.texto_original.replace(' (texto revisado por el administrador)', ''))
        requisito.refresh_from_db()
        libro = origin.datos_iniciales['llenado_automatico']
        for entrada in libro['registros']:
            if entrada['id'] == requisito.pk:
                entrada['contenido'] = contenido_de_requisito(requisito)
        origin.save(update_fields=['datos_iniciales'])
        Requisito.objects.filter(pk=requisito.pk).update(validado=True)
        self.assertIn('validado', self.ejecutar(offer, '--aplicar', '--actor-id', str(self.actor.pk))['convocatorias'][0]['solo_informe'][0]['motivo'])
        # Publicada: solo informe.
        Requisito.objects.filter(pk=requisito.pk).update(validado=False)
        Convocatoria.objects.filter(pk=offer.pk).update(revision='validada', institucion=Institucion.objects.create(
            nombre='Entidad', sector='publico', pais=Pais.objects.get(codigo='EC')))
        informe = self.ejecutar(offer, '--aplicar', '--actor-id', str(self.actor.pk))['convocatorias'][0]
        self.assertEqual(informe['cambiados'], [])
        self.assertIn('publicada', informe['solo_informe'][0]['motivo'])
        requisito.refresh_from_db()
        self.assertEqual(requisito.tipo_requisito.codigo, 'OTRO')
        self.assertFalse(Evento.objects.filter(convocatoria=offer, accion='requisitos_retipificar').exists())
