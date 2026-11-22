"""Identidad de versión por contenido (no por bytes del HTML) y evidencia exacta de cada descarga.

HTTP simulado; escribe solo en la base de pruebas aislada.
"""
import uuid
from unittest.mock import patch

from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from convocatorias.siau_red import PAGES, PDFS
from convocatorias.test_siau import FIXTURE
from . import tests as base
from .models import Acceso, Documento, Ejecucion, Observacion, Publicacion, Version, VersionDocumento
from .services import run_manual, summary

ORIGINAL = FIXTURE.read_text(encoding='utf8')


def con_ids_aleatorios(semilla):
    """Mismo contenido con los identificadores de plugins que SIAU cambia en cada respuesta."""
    return ORIGINAL.replace('<nav>', f'<nav><div class="n2-ss-slider n-uc-{semilla}A" id="ubtn-{semilla}">'
                                      f'<script>var wpdm_js = {{"client_id":"{semilla:032d}"}};</script></div>')


class VersionPorContenidoTests(TransactionTestCase):
    setUp = base.RastreoTests.setUp
    source = base.RastreoTests.source
    fake = base.RastreoTests.fake

    def correr(self, source, html=ORIGINAL, pdf=None):
        def red(url):
            if url in PAGES:
                return 200, {'content-type': 'text/html'}, html.encode('utf8')
            if pdf is not None and url in PDFS:
                return 200, {'content-type': 'application/pdf'}, pdf
            return self.fake(url)
        with patch('convocatorias.siau_red.Downloader.once', side_effect=red):
            run = run_manual(source.pk, self.actor.pk, uuid.uuid4())
        self.assertEqual(summary(run)['estado'], 'finalizada')
        return run

    def resultados(self, run):
        return sorted(run.observaciones.values_list('resultado', flat=True))

    @base.ventana_cumplida()
    def test_ids_aleatorios_no_crean_versiones_y_cada_descarga_conserva_sus_bytes(self):
        source = self.source()
        primera = self.correr(source, con_ids_aleatorios(1111))
        self.assertEqual(self.resultados(primera), ['nueva', 'nueva'])
        self.assertEqual(summary(primera)['resumen']['versiones_con_cambios'], 2)  # la primera versión cuenta como nueva
        for semilla in (2222, 3333):
            run = self.correr(source, con_ids_aleatorios(semilla))
            self.assertEqual(self.resultados(run), ['sin_cambios', 'sin_cambios'])
            self.assertEqual(summary(run)['versiones_nuevas'], 0)
            self.assertEqual(summary(run)['observaciones_sin_cambios'], 2)
            self.assertEqual(summary(run)['resumen']['versiones_con_cambios'], 0)
        for publicacion in Publicacion.objects.all():
            self.assertEqual(publicacion.versiones.count(), 1)
            accesos = Acceso.objects.filter(publicacion=publicacion, rol='ficha', documento__isnull=False).select_related('documento')
            self.assertEqual(len({a.documento.sha256 for a in accesos}), 3)  # una huella distinta por descarga
            for acceso in accesos:
                # Trazabilidad: la observación de cada ejecución lleva a los bytes exactos que se descargaron en ella.
                observada = Observacion.objects.get(ejecucion=acceso.ejecucion, publicacion=publicacion)
                self.assertEqual(observada.version.publicacion_id, publicacion.pk)
                self.assertEqual(Documento.objects.filter(pk=acceso.documento_id, mime='text/html').count(), 1)

    @base.ventana_cumplida()
    def test_cambio_real_de_texto_y_de_pdf_crean_version_nueva_y_a_b_a_reutiliza_a(self):
        source = self.source()
        a = self.correr(source, con_ids_aleatorios(1))
        b = self.correr(source, con_ids_aleatorios(2).replace('$3000', '$2500'))
        self.assertEqual(self.resultados(b), ['cambio_relevante', 'cambio_relevante'])
        self.assertEqual(summary(b)['resumen']['versiones_con_cambios'], 2)
        vuelta = self.correr(source, con_ids_aleatorios(3))
        self.assertEqual(self.resultados(vuelta), ['cambio_relevante', 'cambio_relevante'])
        self.assertEqual(summary(vuelta)['versiones_nuevas'], 0)  # CP19: A→B→A reutiliza la versión de A
        self.assertEqual(list(a.observaciones.order_by('publicacion_id').values_list('version_id', flat=True)),
                         list(vuelta.observaciones.order_by('publicacion_id').values_list('version_id', flat=True)))
        pdf = self.correr(source, con_ids_aleatorios(4), pdf=b'%PDF-1.4\nBases sinteticas cambiadas')
        self.assertEqual(self.resultados(pdf), ['cambio_relevante', 'cambio_relevante'])
        self.assertEqual(summary(pdf)['versiones_nuevas'], 2)
        self.assertEqual(Version.objects.count(), 6)

    def test_el_disparador_sigue_exigiendo_la_evidencia_de_la_ejecucion(self):
        source = self.source()
        with patch('convocatorias.siau_red.Downloader.once', side_effect=self.fake):
            run_manual(source.pk, self.actor.pk, uuid.uuid4())
        version = Version.objects.order_by('id').first()
        sin_nada = Ejecucion.objects.create(fuente=source, solicitado_por=self.actor, configuracion_snapshot={}, version_extractor='test')
        # Ni la ficha HTML de esa URL ni el PDF exacto se obtuvieron en esta ejecución: la base lo rechaza.
        with self.assertRaises(DatabaseError), transaction.atomic():
            Observacion.objects.create(ejecucion=sin_nada, publicacion=version.publicacion, version=version, resultado='sin_cambios')

    def test_la_migracion_0016_se_revierte_y_se_vuelve_a_aplicar(self):
        self.assertIn(connection.settings_dict['NAME'], ('test_becanexo_db', 'test_becanexo_fusion_db'))

        def funcion():
            with connection.cursor() as cursor:
                cursor.execute("SELECT prosrc FROM pg_proc WHERE proname='rastreo_evidencia_observada'")
                return cursor.fetchone()[0]

        self.assertIn("rol<>'ficha_html'", funcion())
        try:
            MigrationExecutor(connection).migrate([('rastreo', '0015_fuente_frecuencia_12h')])
            self.assertNotIn('ficha_html', funcion())
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        self.assertIn("rol<>'ficha_html'", funcion())
