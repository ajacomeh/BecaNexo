from django.db import migrations

SQL = '''
CREATE FUNCTION rast_propuesta_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM "TRA_PUBLICACION_FUENTE" WHERE id=NEW.publicacion_id FOR UPDATE;
 IF NOT EXISTS (SELECT 1 FROM "MAE_USUARIO" WHERE id=NEW.actor_id AND activo AND rol='administrador') THEN
  RAISE EXCEPTION 'Actor no autorizado';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM "TRA_OBSERVACION_RASTREO" o JOIN "TRA_VERSION_PUBLICACION" v ON v.id=o.version_id
 WHERE o.id=NEW.observacion_base_id AND v.id=NEW.version_id AND v.publicacion_id=NEW.publicacion_id AND o.publicacion_id=NEW.publicacion_id) THEN
  RAISE EXCEPTION 'Origen incoherente';
 END IF;
 IF NEW.sustituye_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "TRA_PROPUESTA_CAMBIO" WHERE id=NEW.sustituye_id AND publicacion_id=NEW.publicacion_id) THEN
  RAISE EXCEPTION 'Sucesor incoherente';
 END IF;
 IF jsonb_typeof(NEW.datos)<>'object' OR jsonb_typeof(NEW.procedencia)<>'array' OR jsonb_typeof(NEW.pendientes)<>'object' THEN
  RAISE EXCEPTION 'Contrato incorrecto';
 END IF;
 IF EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.procedencia) p WHERE NOT EXISTS
 (SELECT 1 FROM "REL_VERSION_DOCUMENTO" d WHERE d.id=(p->>'evidencia_id')::bigint AND d.version_id=NEW.version_id)) THEN
  RAISE EXCEPTION 'Evidencia ajena';
 END IF;
 NEW.transaccion_id := txid_current();
 NEW.creada_en := statement_timestamp();
 RETURN NEW;
END $$;
CREATE TRIGGER rast_propuesta_insert BEFORE INSERT ON "TRA_PROPUESTA_CAMBIO" FOR EACH ROW EXECUTE FUNCTION rast_propuesta_guard();
CREATE TRIGGER rast_propuesta_inmutable BEFORE UPDATE OR DELETE ON "TRA_PROPUESTA_CAMBIO" FOR EACH ROW EXECUTE FUNCTION rastreo_inmutable();
CREATE FUNCTION rast_propuesta_revision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM "TRA_PROPUESTA_CAMBIO" p JOIN "AUD_REVISION_RASTREO" r ON r.version_id=p.version_id
 WHERE p.id=NEW.propuesta_id AND r.id=NEW.revision_id AND p.transaccion_id=txid_current()) THEN
  RAISE EXCEPTION 'Revision ajena o snapshot cerrado';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER rast_propuesta_revision_insert BEFORE INSERT ON "REL_PROPUESTA_REVISION" FOR EACH ROW EXECUTE FUNCTION rast_propuesta_revision_guard();
CREATE TRIGGER rast_propuesta_revision_inmutable BEFORE UPDATE OR DELETE ON "REL_PROPUESTA_REVISION" FOR EACH ROW EXECUTE FUNCTION rastreo_inmutable();
'''

REVERSE = '''
DROP TRIGGER rast_propuesta_revision_inmutable ON "REL_PROPUESTA_REVISION";
DROP TRIGGER rast_propuesta_revision_insert ON "REL_PROPUESTA_REVISION";
DROP FUNCTION rast_propuesta_revision_guard();
DROP TRIGGER rast_propuesta_inmutable ON "TRA_PROPUESTA_CAMBIO";
DROP TRIGGER rast_propuesta_insert ON "TRA_PROPUESTA_CAMBIO";
DROP FUNCTION rast_propuesta_guard();
'''


class Migration(migrations.Migration):
    dependencies = [('rastreo', '0008_propuesta_propuestarevision_and_more')]
    operations = [migrations.RunSQL(SQL, REVERSE)]
