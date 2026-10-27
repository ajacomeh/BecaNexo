from django.db import migrations


SQL = r'''
CREATE FUNCTION rastreo_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Historial de rastreo inmutable: %', TG_TABLE_NAME; END $$;
CREATE FUNCTION rastreo_ejecucion_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'No eliminar ejecuciones'; END IF;
 IF TG_OP = 'UPDATE' THEN
  IF OLD.estado <> 'en_curso' THEN RAISE EXCEPTION 'Ejecucion finalizada inmutable'; END IF;
  IF (to_jsonb(NEW) - ARRAY['fin','estado','latido_en','error_resumen']) IS DISTINCT FROM
     (to_jsonb(OLD) - ARRAY['fin','estado','latido_en','error_resumen']) THEN
   RAISE EXCEPTION 'Campos de ejecucion no editables';
  END IF;
  IF NEW.estado = 'omitida' THEN RAISE EXCEPTION 'No omitir una ejecucion iniciada'; END IF;
 ELSE
  IF NEW.origen = 'manual' AND NOT EXISTS (SELECT 1 FROM "MAE_USUARIO" WHERE id=NEW.solicitado_por_id AND activo AND rol='administrador') THEN
   RAISE EXCEPTION 'Actor administrador activo requerido';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER rast_ejec_guard BEFORE INSERT OR UPDATE OR DELETE ON "TRA_EJECUCION_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_ejecucion_guard();

CREATE FUNCTION rastreo_pertenencia() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE src bigint; ex bigint; prev record;
BEGIN
 IF TG_TABLE_NAME = 'TRA_ACCESO_RASTREO' THEN
  IF NOT EXISTS (SELECT 1 FROM "TRA_EJECUCION_RASTREO" WHERE id=NEW.ejecucion_id AND estado='en_curso') THEN RAISE EXCEPTION 'Acceso requiere ejecucion activa'; END IF;
 ELSIF TG_TABLE_NAME = 'TRA_INCIDENCIA_RASTREO' THEN
  IF NEW.ejecucion_id IS NOT NULL THEN
   SELECT fuente_id INTO src FROM "TRA_EJECUCION_RASTREO" WHERE id=NEW.ejecucion_id;
   IF src IS DISTINCT FROM NEW.fuente_id THEN RAISE EXCEPTION 'Incidencia de otra fuente'; END IF;
  END IF;
  IF NEW.acceso_id IS NOT NULL THEN
   SELECT ejecucion_id INTO ex FROM "TRA_ACCESO_RASTREO" WHERE id=NEW.acceso_id;
   IF ex IS DISTINCT FROM NEW.ejecucion_id THEN RAISE EXCEPTION 'Acceso de otra ejecucion'; END IF;
  END IF;
 ELSIF TG_TABLE_NAME = 'AUD_REVISION_RASTREO' THEN
  IF NOT EXISTS (SELECT 1 FROM "MAE_USUARIO" WHERE id=NEW.actor_id AND activo AND rol='administrador') THEN RAISE EXCEPTION 'Revision requiere administrador activo'; END IF;
  NEW.transaccion_id := txid_current();
  IF NEW.sustituye_id IS NOT NULL THEN
   SELECT * INTO prev FROM "AUD_REVISION_RASTREO" WHERE id=NEW.sustituye_id;
   IF prev.id IS NULL OR prev.dimension <> NEW.dimension OR prev.fuente_id IS DISTINCT FROM NEW.fuente_id OR prev.incidencia_id IS DISTINCT FROM NEW.incidencia_id THEN RAISE EXCEPTION 'Revision sustituida de otro objeto'; END IF;
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER rast_acceso_pertenencia BEFORE INSERT ON "TRA_ACCESO_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_pertenencia();
CREATE TRIGGER rast_incid_pertenencia BEFORE INSERT ON "TRA_INCIDENCIA_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_pertenencia();
CREATE TRIGGER rast_revision_pertenencia BEFORE INSERT ON "AUD_REVISION_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_pertenencia();

CREATE FUNCTION rastreo_fuente_auditada() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE antes jsonb;
BEGIN
 IF TG_OP='INSERT' THEN antes := 'null'::jsonb; ELSE antes := to_jsonb(OLD); END IF;
 IF NOT EXISTS (SELECT 1 FROM "AUD_REVISION_RASTREO" r WHERE r.fuente_id=NEW.id
  AND r.dimension='configuracion' AND r.decision='aplicada' AND r.transaccion_id=txid_current()
  AND r.detalle->'antes'=antes AND r.detalle->'despues'=to_jsonb(NEW)) THEN
  RAISE EXCEPTION 'Configuracion requiere auditoria antes/despues en la misma transaccion';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER rast_fuente_auditada AFTER INSERT OR UPDATE ON "CFG_FUENTE"
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION rastreo_fuente_auditada();
CREATE TRIGGER rast_fuente_no_delete BEFORE DELETE ON "CFG_FUENTE" FOR EACH ROW EXECUTE FUNCTION rastreo_inmutable();
CREATE TRIGGER rast_documento_inmutable BEFORE UPDATE OR DELETE ON "TEC_DOCUMENTO_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_inmutable();
CREATE TRIGGER rast_acceso_inmutable BEFORE UPDATE OR DELETE ON "TRA_ACCESO_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_inmutable();
CREATE TRIGGER rast_incidencia_inmutable BEFORE UPDATE OR DELETE ON "TRA_INCIDENCIA_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_inmutable();
CREATE TRIGGER rast_revision_inmutable BEFORE UPDATE OR DELETE ON "AUD_REVISION_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_inmutable();
'''

REVERSE = '''
DROP FUNCTION rastreo_fuente_auditada() CASCADE;
DROP FUNCTION rastreo_pertenencia() CASCADE;
DROP FUNCTION rastreo_ejecucion_guard() CASCADE;
DROP FUNCTION rastreo_inmutable() CASCADE;
'''


class Migration(migrations.Migration):
    dependencies = [('rastreo', '0001_initial')]
    operations = [migrations.RunSQL(SQL, REVERSE)]
