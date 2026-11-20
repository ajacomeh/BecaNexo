"""Ensayo aislado: candidato simulado y evidencia PDF local antes del borrador."""
import json
import uuid

from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from convocatorias.models import BorradorRastreo, Requisito, TipoRequisito
from convocatorias.services import publicar, publicas
from convocatorias.siau_extraccion import extract_html

from .auto_borradores import editable_candidates, pending_for_publication, prepare_automatic_draft
from .models import Acceso, Ejecucion, Publicacion
from .observaciones import observe
from .services import snapshot
from .storage import save_document
from . import test_candidate_transition as transition
from .test_evidencia_pdf import pdf_pages


@override_settings(RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS=False)
class EnsayoIntegralDocumental(TransactionTestCase):
    # Reutiliza únicamente la preparación y el cliente HTTP simulado existentes.
    setUpBase = transition.CandidateTransitionTests.setUpBase
    source = transition.CandidateTransitionTests.source
    setUp = transition.CandidateTransitionTests.setUp
    execute = transition.CandidateTransitionTests.execute

    def test_candidato_html_pdf_y_borrador_privado(self):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))
        html = transition.fiche() + b'''<h2>Requisitos generales</h2><table>
          <tr><td>Presentar solicitud institucional</td></tr></table>'''
        first_run, calls = self.execute(html=html)
        self.assertEqual(first_run.estado, 'finalizada')
        self.assertEqual(len(calls), 2)  # robots y ficha; ninguna base externa
        publication = Publicacion.objects.get(fuente=self.source, url_normalizada=self.candidate.url_normalizada)
        first_version = publication.versiones.get()
        first_origin, first_created, _ = prepare_automatic_draft(publication.pk, first_version.pk, allow_partial=True)
        self.assertTrue(first_created)
        self.assertEqual(first_origin.convocatoria.estado, 'borrador')
        html_evidence = first_version.documentos.get(rol='ficha_html')

        pdf = pdf_pages([
            'Programa de becas nacionales', 'Requisitos generales',
            'Ser ciudadano ecuatoriano', 'Cierre de postulaciones 20/11/2026',
            'Beneficios', 'Cobertura del 75% al 100% segun evaluacion',
        ], ['Beca deportiva', 'Requisitos especificos', 'Acreditar actividad deportiva'])
        pdf_document, _ = save_document(pdf, 'application/pdf')
        second_run = Ejecucion.objects.create(fuente=self.source, solicitado_por=self.actor,
            origen='manual', clave_idempotencia=uuid.uuid4(),
            configuracion_snapshot=snapshot(self.source.pk),
            version_extractor=first_run.version_extractor,
            version_normalizador=first_run.version_normalizador)
        pdf_url = self.candidate.url_normalizada + 'bases.pdf'
        for sequence, role, url, document in (
                (1, 'ficha', html_evidence.url_normalizada, html_evidence.documento),
                (2, 'bases', pdf_url, pdf_document)):
            now = timezone.now()
            Acceso.objects.create(ejecucion=second_run, publicacion=publication,
                documento=document, secuencia=sequence, rol=role,
                url_original=url, url_normalizada=url, url_final=url,
                admitido_en=now, fin=now, resultado='reutilizado', http_status=200)
        item = extract_html({'contenido': html, 'url': self.candidate.url_normalizada,
                             'consulta_utc': timezone.now().isoformat()})
        observed = observe(second_run, publication, item, [
            {'rol': 'ficha_html', 'url': html_evidence.url_normalizada,
             'documento': html_evidence.documento},
            {'rol': 'bases_pdf', 'url': pdf_url,
             'documento': pdf_document},
        ])
        self.assertEqual(observed.resultado, 'cambio_relevante')
        version = observed.version
        self.assertEqual(version.documentos.count(), 2)
        origin, created, _ = prepare_automatic_draft(publication.pk, version.pk, allow_partial=True)
        self.assertFalse(created)
        self.assertEqual(origin.version_id, first_version.pk)
        self.assertEqual(origin.publicacion_id, publication.pk)
        self.assertEqual(origin.convocatoria.estado, 'borrador')
        self.assertIsNone(origin.convocatoria.institucion_id)

        editorial = editable_candidates(version)['otros_campos']
        self.assertEqual(editorial['evidencia_tabular']['estado'], 'extraida')
        self.assertEqual(editorial['evidencia_pdf']['documentos'][0]['estado'], 'extraido')
        proposals = editorial['propuestas_documentales']
        self.assertTrue(any(row['procedencia'].get('pagina') == 1 for row in proposals))
        self.assertTrue(any(row['campo'] == 'cierre_dia' and row['valor'] == '2026-11-20' for row in proposals))
        self.assertTrue(any(row['campo'] == 'beneficio' and 'porcentaje fijo' in ' '.join(row['advertencias']) for row in proposals))
        self.assertTrue(any(row['categoria'] == 'Beca deportiva' and row['destino'] is None for row in proposals))
        self.assertTrue(all(row['estado'] == 'pendiente_revision' for row in proposals))
        self.assertTrue(all(row['procedencia']['version_id'] == version.pk for row in proposals))

        before = (origin.convocatoria.titulo, origin.convocatoria.descripcion,
                  origin.convocatoria.requisitos.count(), origin.convocatoria.beneficios.count())
        repeated, new, _ = prepare_automatic_draft(publication.pk, version.pk, allow_partial=True)
        origin.convocatoria.refresh_from_db()
        self.assertFalse(new)
        self.assertEqual(repeated.pk, origin.pk)
        self.assertEqual(BorradorRastreo.objects.count(), 1)
        self.assertEqual(before, (origin.convocatoria.titulo, origin.convocatoria.descripcion,
                                 origin.convocatoria.requisitos.count(), origin.convocatoria.beneficios.count()))
        self.assertTrue(origin.pendientes_iniciales)
        requirement_type = TipoRequisito.objects.create(codigo='OTRO', nombre='Otra condición',
                                                       esquema_valor={'campos': {}})
        Requisito.objects.create(convocatoria=origin.convocatoria,
            tipo_requisito=requirement_type,
            texto_original='Acreditar condición según bases', obligatorio=True,
            operador='externo', validado=False, modo_comprobacion='entidad_oferente',
            valor_estructurado={'descripcion': 'Acreditar condición según bases'})
        with self.assertRaises(ValidationError) as publication_error:
            publicar(origin.convocatoria)
        self.assertIn('institución oferente ecuatoriana', str(publication_error.exception))
        self.assertFalse(publicas().filter(pk=origin.convocatoria_id).exists())
        self.assertEqual(APIClient().get(f'/api/becas/{origin.convocatoria_id}/').status_code, 404)
        client = APIClient()
        client.force_login(self.actor)
        response = client.get(f'/api/gestion/rastreo/convocatorias/{origin.convocatoria_id}/origen/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['version_actual_id'], version.pk)
        self.assertTrue(response.data['cambio_relevante'])
        self.assertEqual(set(response.data['evidencia']), {'campos', 'registros'})
        print(json.dumps({'ensayo_id': origin.convocatoria_id, 'estado': origin.convocatoria.estado,
                          'publicacion': publication.pk, 'version': version.pk,
                          'propuestas': len(proposals), 'bloqueos_origen': len(pending_for_publication(origin.convocatoria, origin)),
                          'requisito_no_validado': True}))
