"""Integridad SQL del vínculo; únicamente fixtures y almacenamiento temporales."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from django.db import connections
from unittest.mock import patch
from django.db import DatabaseError, transaction, connection
from django.test import TransactionTestCase
from convocatorias.models import Convocatoria, Institucion
from convocatorias.serializers import ConvocatoriaSerializer
from perfiles.models import Pais
from . import tests as base
from .models import Version, Publicacion, Revision
from .propuestas import guardar
from .revisiones import vigentes, ConflictoRevision
from .revisiones import registrar
from convocatorias.services import publicar, publicas, detalle
from .integracion import crear_borrador, resolver_pendiente, estado_publicacion_integrada, digest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from convocatorias.models import OpcionEstudio


class IntegridadIntegracionTests(TransactionTestCase):
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    run_fake = base.RastreoTests.run_fake

    def setUp(self):
        base.RastreoTests.setUp(self)
        self.run_fake(self.source())
        self.version = Version.objects.first()
        self.pub = self.version.publicacion
        self.payload = dict(clave_accion=str(uuid.uuid4()), version_id=self.version.pk,
            observacion_base_id=self.pub.observaciones.first().pk, revisiones=[], datos={}, procedencia=[])
        self.proposal, _ = guardar(self.actor.pk, self.pub.pk, self.payload)
        country = Pais.objects.create(codigo='EC', nombre='Ecuador')
        institution = Institucion.objects.create(nombre='Entidad sintética', sector='publico', pais=country)
        self.institution = institution
        serializer = ConvocatoriaSerializer(data={'institucion': institution.pk, 'titulo': 'Borrador sintético'})
        serializer.is_valid(raise_exception=True)
        self.offer = serializer.save()

    def application(self, **kwargs):
        return Revision.objects.create(actor=self.actor, version=self.version, propuesta=self.proposal,
            convocatoria=self.offer, dimension='integracion', decision='aplicada', motivo='Prueba sintética',
            detalle={}, **kwargs)

    def link(self):
        Publicacion.objects.filter(pk=self.pub.pk).update(convocatoria=self.offer)

    def test_link_requires_atomic_audit_and_cannot_be_replaced(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            self.link()
        self.pub.refresh_from_db()
        self.assertIsNone(self.pub.convocatoria_id)
        with transaction.atomic():
            app = self.application()
            self.link()
        self.assertFalse(vigentes(self.version.pk).filter(pk=app.pk).exists())
        with self.assertRaises(DatabaseError), transaction.atomic():
            Publicacion.objects.filter(pk=self.pub.pk).update(convocatoria=None)
        with self.assertRaises(DatabaseError), transaction.atomic():
            Revision.objects.filter(pk=app.pk).update(motivo='Cambio prohibido')
        body = {**self.payload, 'clave_accion': str(uuid.uuid4())}
        with self.assertRaises(ConflictoRevision):
            guardar(self.actor.pk, self.pub.pk, body, self.proposal.pk)

    def test_application_without_link_rolls_back(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            self.application()
        self.assertFalse(Revision.objects.filter(dimension='integracion').exists())

    def test_new_publication_cannot_start_linked(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            Publicacion.objects.create(fuente=self.pub.fuente, convocatoria=self.offer,
                url_original='https://example.org/new', url_normalizada='https://example.org/new', normalizacion_version='1')

    def test_resolution_cannot_reference_another_application(self):
        with transaction.atomic():
            app = self.application()
            self.link()
        with self.assertRaises(DatabaseError), transaction.atomic():
            Revision.objects.create(actor=self.actor, version=self.version, propuesta=self.proposal,
                convocatoria=self.offer, dimension='integracion', decision='resuelta', motivo='Sintética',
                detalle={}, aplicacion=None)
        self.assertEqual(Revision.objects.filter(dimension='integracion').count(), 1)
        with transaction.atomic():
            Revision.objects.create(actor=self.actor, version=self.version, propuesta=self.proposal,
                convocatoria=self.offer, dimension='integracion', decision='resuelta', motivo='Sintética',
                detalle={}, aplicacion=app)

    def test_database_is_test_only(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database()')
            self.assertEqual(cursor.fetchone()[0], 'test_becanexo_db')

    def reviewed_proposal(self, *, options=None):
        relation = self.version.documentos.first()
        def review(dimension, evidence=None, **extra):
            row, _ = registrar(self.actor.pk, self.version.pk, dict(dimension=dimension,
                decision='aprobada', motivo='Revisión sintética verificable', evidencia_id=evidence,
                sustituye_id=None, clave_accion=uuid.uuid4(), **extra))
            return row.pk
        ids = [review('extraccion'), review('oferente', relation.pk,
            tipo_oferente='entidad_ecuatoriana', referencia='Encabezado: entidad sintética')]
        for doc in self.version.documentos.all():
            ids.append(review('documental', doc.pk))
        body = dict(clave_accion=str(uuid.uuid4()), version_id=self.version.pk,
            observacion_base_id=self.pub.observaciones.first().pk, revisiones=ids,
            datos={'institucion': self.institution.pk, 'titulo': 'Beca sintética rastreada',
                   'descripcion': 'Bases sintéticas revisadas', 'url_oficial': 'https://example.org/oficial',
                   'opciones': options or []},
            procedencia=[{'campo': field, 'evidencia_id': relation.pk, 'localizador': 'Sección sintética',
                          'motivo': 'Transcripción revisada'} for field in
                         ['institucion', 'titulo', 'url_oficial'] + [f"opciones.{x['id']}" for x in (options or [])]])
        proposal, _ = guardar(self.actor.pk, self.pub.pk, body, self.proposal.pk)
        return proposal, ids

    def confirmation(self, proposal, ids, *, selected=None):
        return dict(clave_accion=str(uuid.uuid4()), hash_propuesta=proposal.hash_propuesta,
            observacion_base_id=proposal.observacion_base_id, revisiones=ids,
            motivo_institucion='La entidad sintética corresponde al encabezado revisado',
            confirmados=[x['id'] for kind in ('opciones', 'beneficios', 'requisitos') for x in proposal.datos.get(kind, [])],
            opciones=selected or [], beneficios=[], requisitos=[])

    def test_atomic_creation_idempotence_and_publication_guard(self):
        proposal, ids = self.reviewed_proposal()
        body = self.confirmation(proposal, ids)
        first, created = crear_borrador(self.actor.pk, proposal.pk, body)
        self.assertTrue(created)
        self.assertEqual(first.convocatoria.revision, 'pendiente')
        self.assertFalse(first.convocatoria.activa)
        self.assertEqual(first.convocatoria.eventos.filter(accion='rastreo_borrador_crear').count(), 1)
        self.assertEqual(Publicacion.objects.get(pk=self.pub.pk).convocatoria_id, first.convocatoria_id)
        self.assertFalse(publicas().filter(pk=first.convocatoria_id).exists())
        anonymous = APIClient()
        self.assertEqual(anonymous.get(f'/api/becas/{first.convocatoria_id}/').status_code, 404)
        self.assertFalse(any(x['id'] == first.convocatoria_id for x in anonymous.get('/api/becas/').data['results']))
        second, created = crear_borrador(self.actor.pk, proposal.pk, body)
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        other = dict(body, motivo_institucion='Otro contenido')
        with self.assertRaises(ConflictoRevision):
            crear_borrador(self.actor.pk, proposal.pk, other)
        with self.assertRaises(ValidationError):
            publicar(first.convocatoria)
        self.assertEqual(Convocatoria.objects.filter(titulo='Beca sintética rastreada').count(), 1)

    def test_creating_selected_option_and_resolution(self):
        candidate = {'id': 'o1', 'texto': 'Programa sintético', 'nivel': 'maestria', 'modalidad': 'virtual', 'paises': ['EC']}
        proposal, ids = self.reviewed_proposal(options=[candidate])
        body = self.confirmation(proposal, ids)
        # Se conserva el candidato sin mapear como pendiente explícito.
        applied, _ = crear_borrador(self.actor.pk, proposal.pk, body)
        self.assertIn('opciones.o1', applied.detalle['omitidos'])
        self.assertTrue(estado_publicacion_integrada(applied.convocatoria)['pendientes'])

    def test_selected_option_uses_catalog_serializer_and_relation(self):
        candidate = {'id': 'o1', 'texto': 'Programa sintético', 'nivel': 'maestria', 'modalidad': 'virtual', 'paises': ['EC']}
        proposal, ids = self.reviewed_proposal(options=[candidate])
        selected = [{'id': 'o1', 'motivo': 'Transcripción exacta de programa y modalidad',
            'datos': {'nivel': 'maestria', 'modalidad': 'virtual', 'programa': 'Programa sintético',
                      'paises': [self.institution.pais_id]}}]
        body = self.confirmation(proposal, ids, selected=selected)
        applied, _ = crear_borrador(self.actor.pk, proposal.pk, body)
        self.assertEqual(applied.convocatoria.opciones.count(), 1)
        self.assertEqual(list(applied.convocatoria.opciones.first().paises.values_list('codigo', flat=True)), ['EC'])
        self.assertFalse(any(x['codigo'] == 'CANDIDATO_PENDIENTE' for x in applied.detalle['pendientes']))
        self.assertFalse(publicas().filter(pk=applied.convocatoria_id).exists())

    def test_bad_selected_option_rolls_back_all(self):
        candidate = {'id': 'o1', 'texto': 'Programa sintético', 'nivel': 'maestria', 'modalidad': 'virtual', 'paises': ['EC']}
        proposal, ids = self.reviewed_proposal(options=[candidate])
        selected = [{'id': 'o1', 'motivo': 'Sintético', 'datos': {'nivel': 'grado', 'modalidad': 'virtual',
                     'programa': 'Programa sintético', 'paises': [self.institution.pais_id]}}]
        before = Convocatoria.objects.count()
        with self.assertRaises(ValidationError):
            crear_borrador(self.actor.pk, proposal.pk, self.confirmation(proposal, ids, selected=selected))
        self.assertEqual(Convocatoria.objects.count(), before)
        self.assertIsNone(Publicacion.objects.get(pk=self.pub.pk).convocatoria_id)

    def test_creation_rejects_missing_review_and_no_partial_rows(self):
        proposal, ids = self.reviewed_proposal()
        body = self.confirmation(proposal, ids)
        body['revisiones'] = []
        before = Convocatoria.objects.count()
        with self.assertRaises(ConflictoRevision):
            crear_borrador(self.actor.pk, proposal.pk, body)
        self.assertEqual(Convocatoria.objects.count(), before)

    def test_atomic_rollback_after_catalog_creation(self):
        proposal, ids = self.reviewed_proposal()
        before = Convocatoria.objects.count()
        with patch('rastreo.integracion.audit', side_effect=RuntimeError('Fallo sintético')):
            with self.assertRaises(RuntimeError):
                crear_borrador(self.actor.pk, proposal.pk, self.confirmation(proposal, ids))
        self.assertEqual(Convocatoria.objects.count(), before)
        self.assertIsNone(Publicacion.objects.get(pk=self.pub.pk).convocatoria_id)
        self.assertFalse(Revision.objects.filter(dimension='integracion').exists())

    def test_changed_review_and_missing_file_block_creation(self):
        proposal, ids = self.reviewed_proposal()
        doc = self.version.documentos.first().documento
        Path(self.temp.name, doc.clave_almacenamiento).unlink()
        before = Convocatoria.objects.count()
        with self.assertRaises(ValidationError):
            crear_borrador(self.actor.pk, proposal.pk, self.confirmation(proposal, ids))
        self.assertEqual(Convocatoria.objects.count(), before)
        extraction = vigentes(self.version.pk).get(dimension='extraccion')
        registrar(self.actor.pk, self.version.pk, dict(dimension='extraccion', decision='pendiente',
            motivo='Rectificación sintética', evidencia_id=None, sustituye_id=extraction.pk, clave_accion=uuid.uuid4()))
        with self.assertRaises(ConflictoRevision):
            crear_borrador(self.actor.pk, proposal.pk, self.confirmation(proposal, ids))

    def test_concurrent_requests_create_one_draft(self):
        proposal, ids = self.reviewed_proposal()
        bodies = [self.confirmation(proposal, ids), self.confirmation(proposal, ids)]
        def worker(body):
            connections.close_all()
            try:
                row, _ = crear_borrador(self.actor.pk, proposal.pk, body)
                return row.pk
            except ConflictoRevision:
                return None
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(worker, bodies))
        self.assertEqual(len([v for v in values if v]), 1)
        self.assertEqual(Convocatoria.objects.filter(titulo='Beca sintética rastreada').count(), 1)

    def test_manual_publication_stays_unaffected(self):
        self.assertIsNone(estado_publicacion_integrada(self.offer))
        self.assertEqual(self.offer.revision, 'pendiente')

    def test_resolution_requires_matching_offer_and_exact_evidence(self):
        proposal, ids = self.reviewed_proposal()
        applied, _ = crear_borrador(self.actor.pk, proposal.pk, self.confirmation(proposal, ids))
        offer = applied.convocatoria
        issue = next(x for x in applied.detalle['pendientes'] if x['codigo'] == 'SIN_OPCIONES')
        evidence = self.version.documentos.first()
        body = {'clave_accion': str(uuid.uuid4()), 'pendiente_id': issue['id'],
                'evidencia_id': evidence.pk, 'motivo': 'Opción comprobada en las bases sintéticas',
                'version_convocatoria': offer.version, 'hash_convocatoria': digest(detalle(offer))}
        with self.assertRaises(ValidationError):
            resolver_pendiente(self.actor.pk, offer.pk, body)
        OpcionEstudio.objects.create(convocatoria=offer, nivel='maestria', modalidad='virtual', programa='Programa revisado')
        body['hash_convocatoria'] = digest(detalle(offer))
        resolution, created = resolver_pendiente(self.actor.pk, offer.pk, body)
        self.assertTrue(created)
        self.assertEqual(resolution.aplicacion_id, applied.pk)
        self.assertFalse(any(x['id'] == issue['id'] for x in estado_publicacion_integrada(offer)['pendientes']))
        same, created = resolver_pendiente(self.actor.pk, offer.pk, body)
        self.assertEqual(same.pk, resolution.pk)
        self.assertFalse(created)
        offer.descripcion = 'Cambio posterior'; offer.save(update_fields=['descripcion'])
        self.assertTrue(any(x['id'] == issue['id'] for x in estado_publicacion_integrada(offer)['pendientes']))
        body2 = {**body, 'clave_accion': str(uuid.uuid4()), 'hash_convocatoria': digest(detalle(offer)),
                 'motivo': 'Rectificación posterior comprobada'}
        newer, _ = resolver_pendiente(self.actor.pk, offer.pk, body2)
        self.assertEqual(newer.sustituye_id, resolution.pk)
        self.assertFalse(any(x['id'] == issue['id'] for x in estado_publicacion_integrada(offer)['pendientes']))

    def test_candidate_resolution_requires_same_option_destinations_and_provenance(self):
        candidate = {'id': 'o1', 'texto': 'Programa sintético', 'nivel': 'maestria',
                     'modalidad': 'virtual', 'paises': ['EC']}
        proposal, ids = self.reviewed_proposal(options=[candidate])
        applied, _ = crear_borrador(self.actor.pk, proposal.pk, self.confirmation(proposal, ids))
        offer = applied.convocatoria
        issue = next(x for x in applied.detalle['pendientes'] if x['campo'] == 'opciones.o1')
        row = OpcionEstudio.objects.create(convocatoria=offer, nivel='maestria', modalidad='virtual',
                                           programa='Programa sintético')
        relation = self.version.documentos.first()
        body = {'clave_accion': str(uuid.uuid4()), 'pendiente_id': issue['id'],
                'evidencia_id': relation.pk, 'motivo': 'Destino comprobado en evidencia sintética',
                'version_convocatoria': offer.version, 'hash_convocatoria': digest(detalle(offer))}
        with self.assertRaises(ValidationError):
            resolver_pendiente(self.actor.pk, offer.pk, body)
        row.paises.add(self.institution.pais)
        body['hash_convocatoria'] = digest(detalle(offer))
        other = self.version.documentos.exclude(pk=relation.pk).first()
        self.assertIsNotNone(other)
        with self.assertRaises(ValidationError):
            resolver_pendiente(self.actor.pk, offer.pk, {**body, 'evidencia_id': other.pk})
        resolution, created = resolver_pendiente(self.actor.pk, offer.pk, body)
        self.assertTrue(created)
        self.assertEqual(resolution.aplicacion_id, applied.pk)

    def test_create_api_requires_admin_session_and_csrf(self):
        proposal, ids = self.reviewed_proposal()
        body = self.confirmation(proposal, ids)
        path = f'/api/gestion/rastreo/propuestas/{proposal.pk}/crear-borrador/'
        anonymous = APIClient(enforce_csrf_checks=True)
        self.assertEqual(anonymous.post(path, body, format='json').status_code, 403)
        reader = APIClient(enforce_csrf_checks=True); reader.force_login(self.user)
        self.assertEqual(reader.post(path, body, format='json').status_code, 403)
        admin = APIClient(enforce_csrf_checks=True); admin.force_login(self.actor)
        self.assertEqual(admin.post(path, body, format='json').status_code, 403)
        token = admin.get('/api/auth/csrf/').data['csrfToken']
        created = admin.post(path, body, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(admin.post(path, body, format='json', HTTP_X_CSRFTOKEN=token).status_code, 200)
        origin = admin.get(f'/api/gestion/rastreo/convocatorias/{created.data["convocatoria_id"]}/origen/')
        self.assertEqual(origin.status_code, 200, origin.data)
        self.assertEqual(origin.data['publicacion_id'], self.pub.pk)
        self.assertEqual(anonymous.get(f'/api/gestion/rastreo/convocatorias/{created.data["convocatoria_id"]}/origen/').status_code, 403)
