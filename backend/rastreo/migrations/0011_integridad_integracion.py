from importlib import import_module
from django.db import migrations


SQL = r'''
CREATE OR REPLACE FUNCTION rastreo_publicacion_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.convocatoria_id IS NOT NULL THEN RAISE EXCEPTION 'La publicacion nace sin vinculo'; END IF;
 ELSE
  IF (to_jsonb(NEW)-ARRAY['ultima_deteccion','convocatoria_id']) IS DISTINCT FROM
     (to_jsonb(OLD)-ARRAY['ultima_deteccion','convocatoria_id']) OR NEW.ultima_deteccion < OLD.ultima_deteccion
     OR (OLD.convocatoria_id IS NOT NULL AND NEW.convocatoria_id IS DISTINCT FROM OLD.convocatoria_id)
  THEN RAISE EXCEPTION 'Identidad y vinculo inmutables'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER rast_publicacion_nace_libre BEFORE INSERT ON "TRA_PUBLICACION_FUENTE"
 FOR EACH ROW EXECUTE FUNCTION rastreo_publicacion_guard();

CREATE FUNCTION rastreo_vinculo_auditado() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.convocatoria_id IS DISTINCT FROM OLD.convocatoria_id AND NOT EXISTS (
  SELECT 1 FROM "AUD_REVISION_RASTREO" r JOIN "TRA_PROPUESTA_CAMBIO" p ON p.id=r.propuesta_id
  WHERE p.publicacion_id=NEW.id AND r.convocatoria_id=NEW.convocatoria_id
   AND r.dimension='integracion' AND r.decision='aplicada' AND r.transaccion_id=txid_current()
 ) THEN RAISE EXCEPTION 'Vinculo requiere integracion auditada atomica'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER rast_vinculo_auditado AFTER UPDATE ON "TRA_PUBLICACION_FUENTE"
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION rastreo_vinculo_auditado();

CREATE FUNCTION rastreo_integracion_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p record; original record;
BEGIN
 IF NEW.dimension <> 'integracion' THEN RETURN NEW; END IF;
 SELECT * INTO p FROM "TRA_PROPUESTA_CAMBIO" WHERE id=NEW.propuesta_id;
 IF p.version_id IS DISTINCT FROM NEW.version_id OR p.id IS NULL
 THEN RAISE EXCEPTION 'Integracion de otra propuesta/version'; END IF;
 PERFORM id FROM "TRA_PUBLICACION_FUENTE" WHERE id=p.publicacion_id FOR UPDATE;
 IF NEW.decision='aplicada' THEN
  IF EXISTS (SELECT 1 FROM "TRA_PROPUESTA_CAMBIO" WHERE sustituye_id=p.id)
   OR EXISTS (SELECT 1 FROM "TRA_PUBLICACION_FUENTE" WHERE id=p.publicacion_id AND convocatoria_id IS NOT NULL)
  THEN RAISE EXCEPTION 'Propuesta obsoleta o publicacion vinculada'; END IF;
  IF NOT EXISTS (SELECT 1 FROM "MAE_CONVOCATORIA" WHERE id=NEW.convocatoria_id AND revision='pendiente')
  THEN RAISE EXCEPTION 'Integracion requiere borrador'; END IF;
 ELSE
  SELECT * INTO original FROM "AUD_REVISION_RASTREO" WHERE id=NEW.aplicacion_id;
  IF original.dimension IS DISTINCT FROM 'integracion' OR original.decision IS DISTINCT FROM 'aplicada'
   OR original.propuesta_id IS DISTINCT FROM NEW.propuesta_id
   OR original.convocatoria_id IS DISTINCT FROM NEW.convocatoria_id
  THEN RAISE EXCEPTION 'Resolucion de otra aplicacion'; END IF;
  IF NEW.sustituye_id IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM "AUD_REVISION_RASTREO" previous WHERE previous.id=NEW.sustituye_id
    AND previous.aplicacion_id=NEW.aplicacion_id
    AND previous.detalle->>'pendiente_id'=NEW.detalle->>'pendiente_id'
  ) THEN RAISE EXCEPTION 'Rectificacion de otro pendiente'; END IF;
 END IF;
 NEW.transaccion_id := txid_current();
 RETURN NEW;
END $$;
CREATE TRIGGER rast_integracion_guard BEFORE INSERT ON "AUD_REVISION_RASTREO"
 FOR EACH ROW EXECUTE FUNCTION rastreo_integracion_guard();
CREATE UNIQUE INDEX rast_resolucion_pendiente_raiz ON "AUD_REVISION_RASTREO"
 (aplicacion_id, (detalle->>'pendiente_id')) WHERE dimension='integracion' AND decision='resuelta' AND sustituye_id IS NULL;

CREATE FUNCTION rastreo_aplicacion_completa() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.dimension='integracion' AND NEW.decision='aplicada' AND NOT EXISTS (
  SELECT 1 FROM "TRA_PROPUESTA_CAMBIO" p JOIN "TRA_PUBLICACION_FUENTE" f ON f.id=p.publicacion_id
  WHERE p.id=NEW.propuesta_id AND f.convocatoria_id=NEW.convocatoria_id
 ) THEN RAISE EXCEPTION 'Aplicacion sin vinculo'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER rast_aplicacion_completa AFTER INSERT ON "AUD_REVISION_RASTREO"
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION rastreo_aplicacion_completa();

CREATE FUNCTION rastreo_propuesta_no_aplicada() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM id FROM "TRA_PUBLICACION_FUENTE" WHERE id=NEW.publicacion_id FOR UPDATE;
 IF EXISTS (SELECT 1 FROM "TRA_PUBLICACION_FUENTE" WHERE id=NEW.publicacion_id AND convocatoria_id IS NOT NULL)
 THEN RAISE EXCEPTION 'Publicacion ya integrada; no admite sucesores'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER rast_propuesta_no_aplicada BEFORE INSERT ON "TRA_PROPUESTA_CAMBIO"
 FOR EACH ROW EXECUTE FUNCTION rastreo_propuesta_no_aplicada();
'''

OLD = import_module('rastreo.migrations.0004_integridad_versiones').SQL
GUARD = OLD[OLD.index('CREATE FUNCTION rastreo_publicacion_guard()'):OLD.index('CREATE TRIGGER rast_publicacion_guard')].replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1)
REVERSE = '''
DROP FUNCTION rastreo_propuesta_no_aplicada() CASCADE;
DROP FUNCTION rastreo_aplicacion_completa() CASCADE;
DROP FUNCTION rastreo_integracion_guard() CASCADE;
DROP INDEX rast_resolucion_pendiente_raiz;
DROP FUNCTION rastreo_vinculo_auditado() CASCADE;
DROP TRIGGER rast_publicacion_nace_libre ON "TRA_PUBLICACION_FUENTE";
''' + GUARD


class Migration(migrations.Migration):
    dependencies = [('rastreo', '0010_integracion_borrador')]
    operations = [migrations.RunSQL(SQL, REVERSE)]
