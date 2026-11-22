"""Evidencia de una observación cuando la versión se identifica por contenido.

Solo reemplaza la función del disparador rast_evidencia_observada (migración 0005); no cambia tablas ni datos.
- PDF de bases y anexos: la ejecución debe haber obtenido exactamente ese documento (igual que antes).
- HTML de ficha: la ejecución debe haber obtenido el documento exacto, o una ficha HTML de la misma publicación
  (incluida una redirección), o un HTML de la misma URL (secciones de portales); sus bytes exactos quedan en su acceso. La versión reutilizada puede conservar la huella HTML de la primera descarga porque el portal
  inserta identificadores aleatorios en cada respuesta sin cambiar el contenido.
"""
from django.db import migrations

NUEVA = r'''
CREATE OR REPLACE FUNCTION rastreo_evidencia_observada() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.version_id IS NOT NULL AND (
  EXISTS (
   SELECT 1 FROM "REL_VERSION_DOCUMENTO" r WHERE r.version_id=NEW.version_id AND r.rol<>'ficha_html' AND NOT EXISTS (
    SELECT 1 FROM "TRA_ACCESO_RASTREO" a WHERE a.ejecucion_id=NEW.ejecucion_id AND a.documento_id=r.documento_id))
  OR EXISTS (
   SELECT 1 FROM "REL_VERSION_DOCUMENTO" r WHERE r.version_id=NEW.version_id AND r.rol='ficha_html' AND NOT EXISTS (
    SELECT 1 FROM "TRA_ACCESO_RASTREO" a JOIN "TEC_DOCUMENTO_RASTREO" d ON d.id=a.documento_id
    WHERE a.ejecucion_id=NEW.ejecucion_id AND (
     a.documento_id=r.documento_id
     OR (d.mime='text/html' AND a.rol='ficha' AND a.publicacion_id=NEW.publicacion_id)
     OR (d.mime='text/html' AND a.url_normalizada=r.url_normalizada))))
 ) THEN RAISE EXCEPTION 'Observacion sin obtencion de la evidencia exacta en esa ejecucion'; END IF;
 RETURN NULL;
END $$;
'''

ANTERIOR = r'''
CREATE OR REPLACE FUNCTION rastreo_evidencia_observada() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.version_id IS NOT NULL AND EXISTS (
  SELECT 1 FROM "REL_VERSION_DOCUMENTO" r WHERE r.version_id=NEW.version_id AND NOT EXISTS (
   SELECT 1 FROM "TRA_ACCESO_RASTREO" a WHERE a.ejecucion_id=NEW.ejecucion_id AND a.documento_id=r.documento_id
  )) THEN RAISE EXCEPTION 'Observacion sin obtencion de la evidencia exacta en esa ejecucion'; END IF;
 RETURN NULL;
END $$;
'''


class Migration(migrations.Migration):
    dependencies = [('rastreo', '0015_fuente_frecuencia_12h')]
    operations = [migrations.RunSQL(NUEVA, ANTERIOR)]
