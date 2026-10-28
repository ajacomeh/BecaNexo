import io
import json
import tempfile
import shutil
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, connections, transaction, DatabaseError
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from convocatorias.siau_red import ROBOTS, INDEX, PAGES, PDFS
from convocatorias.test_siau import FIXTURE
from .models import Fuente, Ejecucion, Documento, Acceso, Incidencia, Revision
from .services import configure, run_manual, recover, exclusion, snapshot, summary
from .storage import save_document, integrity_report, StorageError


class RastreoTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_db')
        self.actor = get_user_model().objects.create_user(email='rastreo-admin@example.com', nombre='Prueba rastreo', rol='administrador')
        self.user = get_user_model().objects.create_user(email='rastreo-user@example.com', nombre='Prueba postulante')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_override = override_settings(RASTREO_STORAGE_ROOT=self.temp.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def source(self, active=True):
        source, _ = configure(self.actor.pk, 'Alta de prueba')
        if active:
            source, _ = configure(self.actor.pk, 'Activación de prueba', active=True)
        return source

    def fake(self, url):
        if url == ROBOTS:
            return 200, {'content-type': 'text/plain'}, b'User-agent: *\nDisallow: /wp-admin/\n'
        if url in PDFS:
            return 200, {'content-type': 'application/pdf'}, b'%PDF-1.4\nDocumento sintetico'
        return 200, {'content-type': 'text/html'}, FIXTURE.read_bytes()

    def run_fake(self, source, key=None):
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake):
            return run_manual(source.pk, self.actor.pk, key or uuid.uuid4())

    def test_configuration_idempotent_audit_and_disabled(self):
        source = self.source(False)
        self.assertFalse(source.activa)
        self.assertFalse(source.aprobada_publicacion_automatica)
        self.assertEqual(Revision.objects.count(), 1)
        same, changed = configure(self.actor.pk, 'Reintento')
        self.assertFalse(changed)
        self.assertEqual(same.pk, source.pk)
        audit = Revision.objects.get()
        self.assertIsNone(audit.detalle['antes'])
        self.assertEqual(audit.detalle['despues']['id'], source.pk)
        with patch('convocatorias.siau_red.Downloader.once') as request:
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(run.estado, 'omitida')
        request.assert_not_called()

    def test_actor_rejected_and_auto_approval_blocked(self):
        for actor in (None, 9999999, self.user.pk):
            with self.assertRaises(ValidationError):
                configure(actor, 'No permitido')
        source = self.source()
        with self.assertRaises(DatabaseError), transaction.atomic():
            Fuente.objects.filter(pk=source.pk).update(aprobada_publicacion_automatica=True)
        get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            run_manual(source.pk, self.actor.pk, uuid.uuid4())

    def test_source_cannot_bypass_audit_and_atomic_rollback(self):
        source = self.source()
        count = Revision.objects.count()
        with self.assertRaises(DatabaseError), transaction.atomic():
            Fuente.objects.filter(pk=source.pk).update(nombre='Sin auditoría')
        with patch('rastreo.services.Revision.objects.create', side_effect=RuntimeError('simulado')):
            with self.assertRaises(RuntimeError):
                configure(self.actor.pk, 'Fallo auditado', active=False)
        source.refresh_from_db()
        self.assertTrue(source.activa)
        self.assertEqual(source.nombre, 'SIAU')
        self.assertEqual(Revision.objects.count(), count)

    def test_manual_run_idempotence_and_document_dedup(self):
        source = self.source()
        key = uuid.uuid4()
        run = self.run_fake(source, key)
        self.assertEqual(summary(run)['estado'], 'finalizada')
        accesses = Acceso.objects.count()
        docs = Documento.objects.count()
        with patch('convocatorias.siau_red.Downloader.once') as request:
            same = run_manual(source.pk, self.actor.pk, key)
        request.assert_not_called()
        self.assertEqual(same.pk, run.pk)
        self.run_fake(source)
        self.assertEqual(Documento.objects.count(), docs)
        self.assertEqual(Acceso.objects.count(), accesses * 2)
        self.assertTrue(Acceso.objects.filter(resultado='reutilizado').exists())
        self.assertEqual(integrity_report()['problemas'], [])
        self.assertEqual(summary(run)['convocatorias_creadas'], 0)
        self.assertEqual(summary(run)['publicaciones_observadas'], 2)

    def test_history_and_finished_execution_immutable(self):
        source = self.source()
        run = self.run_fake(source)
        for model, field, value in ((Documento, 'mime', 'text/plain'), (Acceso, 'resultado', 'error'),
                                     (Incidencia, 'detalle', 'editado'), (Revision, 'motivo', 'editado'),
                                     (Ejecucion, 'estado', 'en_curso')):
            with self.subTest(model=model.__name__):
                row = model.objects.first()
                self.assertIsNotNone(row)
                with self.assertRaises(DatabaseError), transaction.atomic():
                    model.objects.filter(pk=row.pk).update(**{field: value})
                with self.assertRaises(Exception), transaction.atomic():
                    row.delete()
        self.assertEqual(Ejecucion.objects.get(pk=run.pk).estado, 'finalizada')

    def test_storage_corruption_limits_and_orphan_reporting(self):
        doc, _ = save_document(b'contenido sintetico', 'text/plain')
        path = Path(self.temp.name) / doc.clave_almacenamiento
        path.write_bytes(b'corrupto')
        with self.assertRaises(StorageError):
            save_document(b'contenido sintetico', 'text/plain')
        self.assertEqual(path.read_bytes(), b'corrupto')
        (Path(self.temp.name) / 'huerfano.txt').write_text('sin referencia')
        report = integrity_report()
        self.assertEqual(len(report['problemas']), 2)
        self.assertEqual(report['eliminados'], 0)
        for data, mime in ((b'bad', 'application/pdf'), (b'bad', 'image/png'), (b'x' * 2097153, 'text/plain')):
            with self.assertRaises(StorageError):
                save_document(data, mime)

    def test_disk_failure_and_database_rollback_leave_no_reference(self):
        with patch('rastreo.storage.os.link', side_effect=OSError('simulado')):
            with self.assertRaises(StorageError):
                save_document(b'fallo disco', 'text/plain')
        self.assertFalse(Documento.objects.exists())
        with self.assertRaises(RuntimeError), transaction.atomic():
            save_document(b'archivo antes del rollback', 'text/plain')
            raise RuntimeError('rollback')
        self.assertFalse(Documento.objects.exists())
        self.assertTrue(integrity_report()['problemas'])

    def test_network_failure_and_recovery(self):
        source = self.source()
        with patch('convocatorias.siau_red.Downloader.once', return_value=(404, {}, b'')):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'fallida')
        self.assertTrue(run.incidencias.filter(codigo='HTTP').exists())
        interrupted = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor, configuracion_snapshot=snapshot(source.pk), version_extractor='test')
        self.assertEqual(recover(source.pk, self.actor.pk, 'Recuperar prueba'), [interrupted.pk])
        interrupted.refresh_from_db()
        self.assertEqual(interrupted.estado, 'fallida')
        self.assertTrue(Revision.objects.filter(incidencia__ejecucion=interrupted, decision='resuelta').exists())
        self.assertEqual(summary(self.run_fake(source))['estado'], 'finalizada')

    def test_interruption_releases_lock_without_faking_completion(self):
        source = self.source()
        key = uuid.uuid4()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_manual(source.pk, self.actor.pk, key)
        run = Ejecucion.objects.get(clave_idempotencia=key)
        self.assertEqual(run.estado, 'en_curso')
        self.assertEqual(recover(source.pk, self.actor.pk, 'Interrupción simulada'), [run.pk])

    def test_controlled_connection_exclusion_and_live_recovery_refused(self):
        source = self.source()
        def contender():
            connections.close_all()
            try:
                self.assertEqual(connection.settings_dict['NAME'], 'test_becanexo_db')
                with self.assertRaises(ValidationError):
                    recover(source.pk, self.actor.pk, 'No recuperar vivo')
                return run_manual(source.pk, self.actor.pk, uuid.uuid4()).estado
            finally:
                connections.close_all()
        with exclusion(source.pk) as locked:
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertEqual(pool.submit(contender).result(timeout=15), 'omitida')
        self.assertEqual(summary(self.run_fake(source))['estado'], 'finalizada')

    def test_relation_ownership_and_execution_transition_guards(self):
        source = self.source()
        run = self.run_fake(source)
        with self.assertRaises(DatabaseError), transaction.atomic():
            # Acceso pertenece a run, no a otra ejecución.
            other = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor, configuracion_snapshot={}, version_extractor='test')
            Incidencia.objects.create(fuente=source, ejecucion=other, acceso=run.accesos.first(), codigo='TEST', detalle='inconsistente')
        active = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor, configuracion_snapshot={}, version_extractor='test')
        with self.assertRaises(DatabaseError), transaction.atomic():
            Ejecucion.objects.filter(pk=active.pk).update(version_extractor='otro')
        with self.assertRaises(DatabaseError), transaction.atomic():
            Ejecucion.objects.create(fuente=source, solicitado_por=self.actor, configuracion_snapshot={}, version_extractor='test')

    def test_command_outputs_and_no_changes_to_existing_business_rows(self):
        from django.apps import apps
        models = [m for m in apps.get_models() if m._meta.app_label in ['usuarios', 'perfiles', 'convocatorias', 'favoritos']]
        before = {m._meta.label: list(m.objects.order_by('pk').values()) for m in models}
        out = io.StringIO()
        call_command('rastreo', 'configurar', actor_id=self.actor.pk, motivo='Prueba CLI', stdout=out)
        source = Fuente.objects.get()
        call_command('rastreo', 'activar', actor_id=self.actor.pk, motivo='Activar CLI', stdout=io.StringIO())
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake):
            call_command('rastreo', 'ejecutar', actor_id=self.actor.pk, fuente_id=source.pk, clave=str(uuid.uuid4()), stdout=io.StringIO())
        out = io.StringIO()
        call_command('rastreo', 'resumen', ejecucion_id=Ejecucion.objects.get().pk, stdout=out)
        self.assertEqual(json.loads(out.getvalue())['estado'], 'finalizada')
        self.assertEqual(before, {m._meta.label: list(m.objects.order_by('pk').values()) for m in models})

    def test_same_key_in_competing_connections_never_downloads_twice(self):
        source = self.source()
        key = uuid.uuid4()
        def contender():
            connections.close_all()
            try:
                return run_manual(source.pk, self.actor.pk, key).pk
            finally:
                connections.close_all()
        # Se observa la ejecución ya creada mientras su descarga está en curso.
        first = [True]
        def network(url):
            if first[0]:
                first[0] = False
                with ThreadPoolExecutor(max_workers=1) as pool:
                    observed = pool.submit(contender).result(timeout=15)
                self.assertEqual(observed, Ejecucion.objects.get(clave_idempotencia=key).pk)
            return self.fake(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network) as calls:
            run = run_manual(source.pk, self.actor.pk, key)
        self.assertEqual(summary(run)['estado'], 'finalizada')
        self.assertEqual(Ejecucion.objects.count(), 1)
        self.assertEqual(calls.call_count, 5)

    def test_pdf_change_is_incidence_and_robots_failure_stops(self):
        source = self.source()
        self.run_fake(source)
        def changed(url):
            if url in PDFS:
                return 200, {'content-type': 'application/pdf'}, b'%PDF-1.4\nOtra version sintetica'
            return self.fake(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=changed):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertTrue(run.incidencias.filter(codigo='PDF_CAMBIADO').exists())
        self.assertTrue(run.incidencias.filter(codigo='REVISION_DOCUMENTAL_PENDIENTE').exists())
        with patch('convocatorias.siau_red.Downloader.once', side_effect=TimeoutError) as calls:
            failed = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(calls.call_count, 2)
        self.assertEqual(summary(failed)['estado'], 'fallida')
        self.assertTrue(all(a.url_original == ROBOTS for a in failed.accesos.all()))

    def test_document_transaction_failure_preserves_error_access_not_false_success(self):
        source = self.source()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake), patch('rastreo.storage.Documento.objects.get_or_create', side_effect=DatabaseError('simulado')):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'fallida')
        self.assertFalse(Documento.objects.exists())
        self.assertEqual(run.accesos.get().resultado, 'error')
        self.assertTrue(integrity_report()['problemas'])

    def test_missing_file_is_reported_without_deletion(self):
        document, _ = save_document(b'archivo temporal de prueba', 'text/plain')
        (Path(self.temp.name) / document.clave_almacenamiento).unlink()
        report = integrity_report()
        self.assertEqual(report['problemas'], [{'documento': document.pk, 'problema': 'ausente_o_corrupto'}])
        self.assertTrue(Documento.objects.filter(pk=document.pk).exists())

    def test_network_and_file_processing_are_outside_transactions(self):
        from .storage import prepare_document
        source = self.source()
        def network(url):
            self.assertFalse(connection.in_atomic_block)
            return self.fake(url)
        def prepare(*args):
            self.assertFalse(connection.in_atomic_block)
            return prepare_document(*args)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=network), patch('rastreo.services.prepare_document', side_effect=prepare):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'finalizada')

    def test_document_backup_restore_in_isolated_directories(self):
        # Recupera bytes contra metadatos de test_becanexo_db; NO restaura un dump.
        document, _ = save_document(b'%PDF-1.4\nEvidencia sintetica recuperable', 'application/pdf')
        with tempfile.TemporaryDirectory() as backup, tempfile.TemporaryDirectory() as restored:
            source = Path(self.temp.name) / document.clave_almacenamiento
            saved = Path(backup) / document.clave_almacenamiento
            saved.parent.mkdir()
            shutil.copy2(source, saved)
            manifest = {'clave': document.clave_almacenamiento, 'sha256': document.sha256, 'bytes': document.tamano_bytes}
            (Path(backup) / 'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
            source.unlink()  # Solo archivo sintético de la carpeta temporal del test.
            self.assertTrue(integrity_report()['problemas'])
            recovered = Path(restored) / document.clave_almacenamiento
            recovered.parent.mkdir()
            shutil.copy2(saved, recovered)
            with override_settings(RASTREO_STORAGE_ROOT=restored):
                self.assertEqual(integrity_report(), {'documentos': 1, 'problemas': [], 'eliminados': 0})
                self.assertEqual(recovered.stat().st_size, manifest['bytes'])
