import io
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, connections, transaction, DatabaseError
from django.test import TransactionTestCase

from convocatorias.siau_red import PAGES, PDFS, ROBOTS
from convocatorias.test_siau import FIXTURE
from . import tests as base
from .models import Fuente, Publicacion, Version, VersionDocumento, Observacion, Ejecucion, Incidencia, Acceso, Revision
from .observaciones import normalize_url, observe, differences, identity
from .services import run_manual, summary


class ObservacionesTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake
    run_fake = base.RastreoTests.run_fake

    def altered(self, source, html=None, pdf=None):
        def network(url):
            self.assertFalse(connection.in_atomic_block)
            if html is not None and url in PAGES:
                return 200, {'content-type': 'text/html'}, html.encode('utf8')
            if pdf is not None and url in PDFS:
                return 200, {'content-type': 'application/pdf'}, pdf
            return self.fake(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'finalizada')
        return run

    def test_first_detection_repeat_and_distinct_identities_shared_bytes(self):
        source = self.source()
        first = self.run_fake(source)
        self.assertEqual(Publicacion.objects.count(), 2)
        self.assertEqual(Version.objects.count(), 2)
        self.assertEqual(VersionDocumento.objects.count(), 4)
        self.assertEqual(first.observaciones.filter(resultado='nueva').count(), 2)
        self.assertFalse(Publicacion.objects.exclude(convocatoria=None).exists())
        repeated = self.run_fake(source)
        self.assertEqual(Version.objects.count(), 2)
        self.assertEqual(summary(repeated)['observaciones_sin_cambios'], 2)
        self.assertEqual(summary(repeated)['versiones_nuevas'], 0)
        self.assertEqual(list(first.observaciones.order_by('publicacion_id').values_list('version_id', flat=True)),
                         list(repeated.observaciones.order_by('publicacion_id').values_list('version_id', flat=True)))

    def test_cosmetic_html_has_new_manifest_same_relevant_content(self):
        source = self.source()
        self.run_fake(source)
        html = FIXTURE.read_text(encoding='utf8').replace('<nav>', '<nav class="redisenado">Menú nuevo ') + '<!-- cosmético -->'
        run = self.altered(source, html=html)
        self.assertEqual(run.observaciones.filter(resultado='cambio_bytes').count(), 2)
        for publication in Publicacion.objects.all():
            a, b = publication.versiones.order_by('numero')
            self.assertNotEqual(a.hash_manifiesto, b.hash_manifiesto)
            self.assertEqual(a.hash_contenido_relevante, b.hash_contenido_relevante)

    def test_relevant_requirements_benefits_preserve_negation(self):
        source = self.source()
        self.run_fake(source)
        original = FIXTURE.read_text(encoding='utf8')
        for html in (original.replace('No haber sido sancionado', 'Haber sido sancionado'), original.replace('$3000', '$2000')):
            run = self.altered(source, html=html)
            self.assertEqual(run.observaciones.filter(resultado='cambio_relevante').count(), 2)
        pub = Publicacion.objects.first()
        a, b, c = pub.versiones.order_by('numero')
        self.assertIn('requisitos', differences(a, b)['cambios'])
        self.assertIn('beneficio', differences(a, c)['cambios'])

    def test_pdf_change_records_exact_document_without_approval(self):
        source = self.source()
        self.run_fake(source)
        reviews = Revision.objects.count()
        run = self.altered(source, pdf=b'%PDF-1.4\nNuevas bases sinteticas sin parser')
        self.assertEqual(run.observaciones.filter(resultado='cambio_relevante').count(), 2)
        self.assertTrue(run.incidencias.filter(codigo='PDF_CAMBIADO').exists())
        self.assertEqual(Revision.objects.count(), reviews)
        pub = Publicacion.objects.first()
        a, b = pub.versiones.order_by('numero')
        self.assertEqual(a.hash_contenido_relevante, b.hash_contenido_relevante)
        self.assertNotEqual(a.documentos.get(rol='bases_pdf').documento_id, b.documentos.get(rol='bases_pdf').documento_id)

    def test_new_extractor_same_documents_new_version(self):
        source = self.source()
        self.run_fake(source)
        with patch('rastreo.services.EXTRACTOR_VERSION', 'siau-html/test-nueva'):
            run = self.run_fake(source)
        self.assertEqual(summary(run)['versiones_nuevas'], 2)
        self.assertEqual(Version.objects.count(), 4)
        self.assertTrue(all(o.version.version_extractor == 'siau-html/test-nueva' for o in run.observaciones.select_related('version')))

    def test_return_a_b_a_reuses_a_with_temporal_order(self):
        source = self.source()
        a = self.run_fake(source)
        self.altered(source, html=FIXTURE.read_text(encoding='utf8').replace('$3000', '$2500'))
        returned = self.run_fake(source)
        self.assertEqual(Version.objects.count(), 4)
        self.assertEqual(summary(returned)['versiones_nuevas'], 0)
        self.assertEqual(returned.observaciones.filter(resultado='cambio_relevante').count(), 2)
        self.assertEqual(list(a.observaciones.order_by('publicacion_id').values_list('version_id', flat=True)),
                         list(returned.observaciones.order_by('publicacion_id').values_list('version_id', flat=True)))

    def test_failed_pdf_preserves_html_and_pending_manifest_not_old_pdf(self):
        source = self.source()
        self.run_fake(source)
        def network(url):
            return (404, {}, b'') if url in PDFS else self.fake(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'parcial')
        for observation in run.observaciones.select_related('version'):
            self.assertEqual(observation.version.estado_extraccion, 'parcial')
            self.assertEqual(observation.version.documentos.count(), 1)
            self.assertEqual(observation.version.manifiesto['pendientes'][0]['estado'], 'inaccesible')
        self.assertTrue(run.incidencias.filter(codigo='BASE_INACCESIBLE', publicacion__isnull=False).exists())

    def test_known_and_unknown_fiche_failure_no_empty_version(self):
        source = self.source()
        def network(url):
            return (404, {}, b'') if url in PAGES else self.fake(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertFalse(Publicacion.objects.exists())
        self.assertFalse(run.observaciones.exists())
        self.run_fake(source)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(run.observaciones.filter(resultado='fallo', version=None).count(), 2)
        self.assertEqual(Version.objects.count(), 2)
        self.assertEqual(run.accesos.filter(rol='ficha', publicacion__isnull=False).count(), 2)

    def test_failed_robots_records_known_observations_without_versions(self):
        source = self.source()
        self.run_fake(source)
        with patch('convocatorias.siau_red.Downloader.once', return_value=(404, {}, b'')):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'fallida')
        self.assertEqual(run.observaciones.filter(resultado='fallo').count(), 2)
        self.assertEqual(Version.objects.count(), 2)

    def test_history_immutable_and_later_document_append_rejected(self):
        source = self.source()
        self.run_fake(source)
        for model, field, value in ((Version, 'texto_extraido', 'cambio'), (VersionDocumento, 'localizador', 'cambio'), (Observacion, 'detalle', 'cambio'), (Publicacion, 'url_original', 'https://otra.example/')):
            row = model.objects.first()
            with self.subTest(model=model.__name__):
                with self.assertRaises(DatabaseError), transaction.atomic():
                    model.objects.filter(pk=row.pk).update(**{field: value})
                with self.assertRaises(Exception), transaction.atomic():
                    row.delete()
        relation = VersionDocumento.objects.first()
        with self.assertRaises(DatabaseError), transaction.atomic():
            VersionDocumento.objects.create(version=relation.version, documento=relation.documento, rol='anexo', url_original=PAGES[0], url_normalizada=PAGES[0])

    def test_manifest_transaction_rolls_back_without_losing_valid_accesses(self):
        source = self.source()
        with patch('rastreo.observaciones.VersionDocumento.objects.bulk_create', side_effect=DatabaseError('simulado')):
            run = self.run_fake(source)
        self.assertEqual(summary(run)['estado'], 'fallida')
        self.assertFalse(Version.objects.exists())
        self.assertFalse(VersionDocumento.objects.exists())
        self.assertTrue(run.accesos.filter(documento__isnull=False).exists())
        self.assertTrue(run.observaciones.filter(resultado='fallo').exists())

    def test_incomplete_manifest_and_wrong_publication_rejected_by_database(self):
        source = self.source()
        run = self.run_fake(source)
        a, b = Publicacion.objects.order_by('id')
        version = a.versiones.get()
        with self.assertRaises(DatabaseError), transaction.atomic():
            fields = {f.name: getattr(version, f.name) for f in Version._meta.fields if f.name not in ('id', 'numero', 'transaccion_id', 'hash_manifiesto')}
            Version.objects.create(**fields, numero=2, hash_manifiesto='a' * 64)
        active = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor, configuracion_snapshot={}, version_extractor='test')
        with self.assertRaises(DatabaseError), transaction.atomic():
            Observacion.objects.create(ejecucion=active, publicacion=b, version=version, resultado='nueva')
        with self.assertRaises(DatabaseError), transaction.atomic():
            Incidencia.objects.create(fuente=source, publicacion=b, version=version, codigo='TEST', detalle='incoherente')
        with self.assertRaises(DatabaseError), transaction.atomic():
            Incidencia.objects.create(fuente=source, ejecucion=run, acceso=run.accesos.filter(publicacion=a).first(), publicacion=b, codigo='TEST', detalle='incoherente')

    def test_same_identity_concurrent_connections_unique(self):
        source = self.source()
        execution = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor, configuracion_snapshot={}, version_extractor='test')
        def contender():
            connections.close_all()
            try:
                self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_db')
                return identity(execution, PAGES[0]).pk
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(lambda _: contender(), range(2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Publicacion.objects.count(), 1)
        observation = observe(execution, Publicacion.objects.get(), detail='Fallo sintético')
        self.assertEqual(observe(execution, Publicacion.objects.get()).pk, observation.pk)
        execution.refresh_from_db()
        self.assertEqual(execution.publicaciones_observadas, 1)

    def test_url_identity_normalization_without_path_folding_or_queries(self):
        self.assertEqual(normalize_url('https://SIAU.senescyt.gob.ec:443/Ruta/#x'), 'https://siau.senescyt.gob.ec/Ruta/')
        self.assertNotEqual(normalize_url('https://a.example/A'), normalize_url('https://a.example/a'))
        for url in ('https://user:secret@a.example/', 'https://a.example/?token=valor', 'https://a.example/' + 'á' * 2048):
            with self.assertRaises(ValidationError):
                normalize_url(url)

    def test_readonly_cli_queries_and_cross_publication_diff_rejected(self):
        source = self.source()
        run = self.run_fake(source)
        pub = Publicacion.objects.first()
        version = pub.versiones.get()
        counts = (Version.objects.count(), Observacion.objects.count(), Acceso.objects.count())
        for action, kwargs in [('publicaciones', {'fuente_id': source.pk}), ('versiones', {'publicacion_id': pub.pk}), ('documentos', {'version_id': version.pk}), ('observaciones', {'ejecucion_id': run.pk}), ('diferencias', {'version_id': version.pk, 'otra_version_id': version.pk})]:
            out = io.StringIO()
            call_command('rastreo', action, stdout=out, **kwargs)
            self.assertTrue(json.loads(out.getvalue()))
        self.assertEqual(counts, (Version.objects.count(), Observacion.objects.count(), Acceso.objects.count()))
        with self.assertRaises(ValidationError):
            differences(version, Version.objects.exclude(publicacion=pub).get())

    def test_different_sources_do_not_merge_and_cross_source_access_rejected(self):
        source = self.source()
        run = self.run_fake(source)
        from .services import snapshot
        with transaction.atomic():
            other = Fuente.objects.create(nombre='Fuente sintética distinta', url_base='https://otra.example/', politica_acceso={})
            Revision.objects.create(actor=self.actor, fuente=other, dimension='configuracion', decision='aplicada', motivo='Solo prueba', detalle={'antes': None, 'despues': snapshot(other.pk)})
        active = Ejecucion.objects.create(fuente=other, solicitado_por=self.actor, configuracion_snapshot={}, version_extractor='test')
        separate = identity(active, PAGES[0])
        self.assertNotEqual(separate.pk, Publicacion.objects.get(fuente=source, url_normalizada=PAGES[0]).pk)
        access = run.accesos.filter(publicacion__isnull=False).first()
        fields = {f.name: getattr(access, f.name) for f in Acceso._meta.fields if f.name not in ('id', 'ejecucion')}
        with self.assertRaises(DatabaseError), transaction.atomic():
            Acceso.objects.create(**fields, ejecucion=active)
        with self.assertRaises(DatabaseError), transaction.atomic():
            Observacion.objects.create(ejecucion=active, publicacion=access.publicacion, resultado='fallo')

    def test_redirect_keeps_original_publication_identity(self):
        source = self.source()
        def network(url):
            if url == PAGES[0]:
                return 302, {'location': PAGES[1]}, b''
            return self.fake(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'finalizada')
        self.assertEqual(set(Publicacion.objects.values_list('url_normalizada', flat=True)), set(PAGES))
        self.assertEqual(run.observaciones.count(), 2)
        self.assertTrue(run.accesos.filter(resultado='redirigido').exists())

    def test_counters_cannot_be_invented(self):
        source = self.source()
        active = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor, configuracion_snapshot={}, version_extractor='test')
        with self.assertRaises(DatabaseError), transaction.atomic():
            Ejecucion.objects.filter(pk=active.pk).update(publicaciones_observadas=1)
