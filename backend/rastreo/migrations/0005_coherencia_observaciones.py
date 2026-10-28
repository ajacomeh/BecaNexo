from django.db import migrations

SQL = r'''
CREATE FUNCTION rastreo_contadores_exactos() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE ex bigint; total bigint; nuevas bigint; iguales bigint; actual record;
BEGIN
 IF TG_TABLE_NAME='TRA_OBSERVACION_RASTREO' THEN ex := NEW.ejecucion_id; ELSE ex := NEW.id; END IF;
 SELECT count(*), count(*) FILTER (WHERE o.resultado='sin_cambios'),
        count(*) FILTER (WHERE o.version_id IS NOT NULL AND NOT EXISTS
          (SELECT 1 FROM "TRA_OBSERVACION_RASTREO" prev WHERE prev.version_id=o.version_id AND prev.id<o.id))
 INTO total, iguales, nuevas FROM "TRA_OBSERVACION_RASTREO" o WHERE o.ejecucion_id=ex;
 SELECT * INTO actual FROM "TRA_EJECUCION_RASTREO" WHERE id=ex;
 IF actual.publicaciones_observadas<>total OR actual.versiones_nuevas<>nuevas OR actual.observaciones_sin_cambios<>iguales THEN
  RAISE EXCEPTION 'Contadores no corresponden a las observaciones confirmadas';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER rast_contadores_ejec AFTER INSERT OR UPDATE ON "TRA_EJECUCION_RASTREO" DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION rastreo_contadores_exactos();
CREATE CONSTRAINT TRIGGER rast_contadores_obs AFTER INSERT ON "TRA_OBSERVACION_RASTREO" DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION rastreo_contadores_exactos();

CREATE FUNCTION rastreo_evidencia_observada() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.version_id IS NOT NULL AND EXISTS (
  SELECT 1 FROM "REL_VERSION_DOCUMENTO" r WHERE r.version_id=NEW.version_id AND NOT EXISTS (
   SELECT 1 FROM "TRA_ACCESO_RASTREO" a WHERE a.ejecucion_id=NEW.ejecucion_id AND a.documento_id=r.documento_id
  )) THEN RAISE EXCEPTION 'Observacion sin obtencion de la evidencia exacta en esa ejecucion'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER rast_evidencia_observada AFTER INSERT ON "TRA_OBSERVACION_RASTREO" DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION rastreo_evidencia_observada();
'''


class Migration(migrations.Migration):
    dependencies = [('rastreo', '0004_integridad_versiones')]
    operations = [migrations.RunSQL(SQL, 'DROP FUNCTION rastreo_evidencia_observada() CASCADE; DROP FUNCTION rastreo_contadores_exactos() CASCADE;')]
