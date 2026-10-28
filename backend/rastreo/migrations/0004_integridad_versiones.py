from importlib import import_module
from django.db import migrations


OLD = import_module('rastreo.migrations.0002_integridad_historial').SQL
START = OLD.index('CREATE FUNCTION rastreo_ejecucion_guard()')
END = OLD.index('CREATE TRIGGER rast_ejec_guard')
OLD_GUARD = OLD[START:END].replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1)
NEW_GUARD = OLD_GUARD.replace("'error_resumen']", "'error_resumen','publicaciones_observadas','versiones_nuevas','observaciones_sin_cambios']")

SQL = r'''
ALTER TABLE "TRA_PUBLICACION_FUENTE" ADD CONSTRAINT rast_publicacion_url_bytes CHECK (octet_length(url_normalizada) BETWEEN 1 AND 2048);
ALTER TABLE "REL_VERSION_DOCUMENTO" ADD CONSTRAINT rast_rel_url_bytes CHECK (octet_length(url_normalizada) BETWEEN 1 AND 2048);
CREATE FUNCTION rastreo_publicacion_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-'ultima_deteccion') IS DISTINCT FROM (to_jsonb(OLD)-'ultima_deteccion') OR NEW.ultima_deteccion < OLD.ultima_deteccion THEN
  RAISE EXCEPTION 'Identidad inmutable; vinculacion no habilitada';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER rast_publicacion_guard BEFORE UPDATE ON "TRA_PUBLICACION_FUENTE" FOR EACH ROW EXECUTE FUNCTION rastreo_publicacion_guard();
CREATE TRIGGER rast_publicacion_no_delete BEFORE DELETE ON "TRA_PUBLICACION_FUENTE" FOR EACH ROW EXECUTE FUNCTION rastreo_inmutable();
CREATE TRIGGER rast_version_inmutable BEFORE UPDATE OR DELETE ON "TRA_VERSION_PUBLICACION" FOR EACH ROW EXECUTE FUNCTION rastreo_inmutable();
CREATE TRIGGER rast_rel_inmutable BEFORE UPDATE OR DELETE ON "REL_VERSION_DOCUMENTO" FOR EACH ROW EXECUTE FUNCTION rastreo_inmutable();
CREATE TRIGGER rast_obs_inmutable BEFORE UPDATE OR DELETE ON "TRA_OBSERVACION_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_inmutable();

CREATE FUNCTION rastreo_version_sello() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.transaccion_id := txid_current(); RETURN NEW; END $$;
CREATE TRIGGER rast_version_sello BEFORE INSERT ON "TRA_VERSION_PUBLICACION" FOR EACH ROW EXECUTE FUNCTION rastreo_version_sello();

CREATE FUNCTION rastreo_rel_sello() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE sello bigint; tipo text;
BEGIN
 SELECT transaccion_id INTO sello FROM "TRA_VERSION_PUBLICACION" WHERE id=NEW.version_id;
 IF sello IS DISTINCT FROM txid_current() THEN RAISE EXCEPTION 'No anexar documentos a una version confirmada'; END IF;
 SELECT mime INTO tipo FROM "TEC_DOCUMENTO_RASTREO" WHERE id=NEW.documento_id;
 IF (NEW.rol='ficha_html' AND tipo <> 'text/html') OR (NEW.rol='bases_pdf' AND tipo <> 'application/pdf') THEN RAISE EXCEPTION 'MIME incompatible con rol documental'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER rast_rel_sello BEFORE INSERT ON "REL_VERSION_DOCUMENTO" FOR EACH ROW EXECUTE FUNCTION rastreo_rel_sello();

CREATE FUNCTION rastreo_manifiesto_completo() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE evidencias jsonb;
BEGIN
 SELECT COALESCE(jsonb_agg(jsonb_build_object('rol',r.rol,'url',r.url_normalizada,'sha256',d.sha256) ORDER BY r.rol,r.url_normalizada), '[]'::jsonb)
 INTO evidencias FROM "REL_VERSION_DOCUMENTO" r JOIN "TEC_DOCUMENTO_RASTREO" d ON d.id=r.documento_id WHERE r.version_id=NEW.id;
 IF NEW.manifiesto->'documentos' IS DISTINCT FROM evidencias OR
    NOT EXISTS (SELECT 1 FROM "REL_VERSION_DOCUMENTO" WHERE version_id=NEW.id AND rol='ficha_html') THEN
  RAISE EXCEPTION 'Manifiesto no corresponde al conjunto exacto de documentos';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER rast_manifiesto_completo AFTER INSERT ON "TRA_VERSION_PUBLICACION" DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION rastreo_manifiesto_completo();

CREATE FUNCTION rastreo_pertenencia_bloque2() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE fuente bigint; pub bigint; ex_fuente bigint; acc_pub bigint;
BEGIN
 IF TG_TABLE_NAME='TRA_OBSERVACION_RASTREO' THEN
  SELECT fuente_id INTO ex_fuente FROM "TRA_EJECUCION_RASTREO" WHERE id=NEW.ejecucion_id AND estado='en_curso';
  SELECT fuente_id INTO fuente FROM "TRA_PUBLICACION_FUENTE" WHERE id=NEW.publicacion_id;
  IF fuente IS NULL OR ex_fuente IS DISTINCT FROM fuente THEN RAISE EXCEPTION 'Observacion requiere misma fuente y ejecucion activa'; END IF;
 ELSIF TG_TABLE_NAME='TRA_ACCESO_RASTREO' THEN
  IF NEW.publicacion_id IS NOT NULL THEN
   SELECT fuente_id INTO ex_fuente FROM "TRA_EJECUCION_RASTREO" WHERE id=NEW.ejecucion_id;
   SELECT fuente_id INTO fuente FROM "TRA_PUBLICACION_FUENTE" WHERE id=NEW.publicacion_id;
   IF fuente IS DISTINCT FROM ex_fuente THEN RAISE EXCEPTION 'Acceso de otra fuente'; END IF;
  END IF;
  RETURN NEW;
 ELSE
  IF NEW.publicacion_id IS NOT NULL THEN
   SELECT fuente_id INTO fuente FROM "TRA_PUBLICACION_FUENTE" WHERE id=NEW.publicacion_id;
   IF fuente IS DISTINCT FROM NEW.fuente_id THEN RAISE EXCEPTION 'Incidencia de otra publicacion/fuente'; END IF;
  END IF;
  IF NEW.acceso_id IS NOT NULL THEN
   SELECT publicacion_id INTO acc_pub FROM "TRA_ACCESO_RASTREO" WHERE id=NEW.acceso_id;
   IF acc_pub IS NOT NULL AND acc_pub IS DISTINCT FROM NEW.publicacion_id THEN RAISE EXCEPTION 'Incidencia de otro acceso/publicacion'; END IF;
  END IF;
 END IF;
 IF NEW.version_id IS NOT NULL THEN
  SELECT publicacion_id INTO pub FROM "TRA_VERSION_PUBLICACION" WHERE id=NEW.version_id;
  IF pub IS NULL OR pub IS DISTINCT FROM NEW.publicacion_id THEN RAISE EXCEPTION 'Version de otra publicacion'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER rast_obs_pertenencia BEFORE INSERT ON "TRA_OBSERVACION_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_pertenencia_bloque2();
CREATE TRIGGER rast_acceso_bloque2 BEFORE INSERT ON "TRA_ACCESO_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_pertenencia_bloque2();
CREATE TRIGGER rast_incid_bloque2 BEFORE INSERT ON "TRA_INCIDENCIA_RASTREO" FOR EACH ROW EXECUTE FUNCTION rastreo_pertenencia_bloque2();
'''

REVERSE = r'''
DROP FUNCTION rastreo_pertenencia_bloque2() CASCADE;
DROP FUNCTION rastreo_manifiesto_completo() CASCADE;
DROP FUNCTION rastreo_rel_sello() CASCADE;
DROP FUNCTION rastreo_version_sello() CASCADE;
DROP FUNCTION rastreo_publicacion_guard() CASCADE;
DROP TRIGGER rast_publicacion_no_delete ON "TRA_PUBLICACION_FUENTE";
DROP TRIGGER rast_version_inmutable ON "TRA_VERSION_PUBLICACION";
DROP TRIGGER rast_rel_inmutable ON "REL_VERSION_DOCUMENTO";
DROP TRIGGER rast_obs_inmutable ON "TRA_OBSERVACION_RASTREO";
ALTER TABLE "TRA_PUBLICACION_FUENTE" DROP CONSTRAINT rast_publicacion_url_bytes;
ALTER TABLE "REL_VERSION_DOCUMENTO" DROP CONSTRAINT rast_rel_url_bytes;
'''


class Migration(migrations.Migration):
    dependencies = [('rastreo', '0003_publicaciones_versiones')]
    operations = [migrations.RunSQL(NEW_GUARD + SQL, REVERSE + OLD_GUARD)]
