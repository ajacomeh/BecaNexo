from django.db import migrations


SQL = r'''
CREATE FUNCTION rastreo_revision_editorial_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prev record;
BEGIN
 IF NEW.version_id IS NULL THEN RETURN NEW; END IF;
 PERFORM id FROM "MAE_USUARIO" WHERE id=NEW.actor_id AND activo AND rol='administrador' FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Administrador activo requerido'; END IF;
 PERFORM id FROM "TRA_VERSION_PUBLICACION" WHERE id=NEW.version_id FOR UPDATE;
 IF NEW.evidencia_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM "REL_VERSION_DOCUMENTO" WHERE id=NEW.evidencia_id AND version_id=NEW.version_id
 ) THEN RAISE EXCEPTION 'Evidencia de otra version'; END IF;
 IF NEW.dimension='oferente' THEN
  IF NOT (NEW.detalle ? 'tipo_oferente') OR NOT (NEW.detalle ? 'referencia')
   OR NEW.detalle->>'tipo_oferente' NOT IN ('entidad_ecuatoriana','convenio','no_determinado')
   OR COALESCE(NEW.detalle->>'referencia','') !~ '\S'
   OR (NEW.decision='aprobada' AND NEW.detalle->>'tipo_oferente' <> 'entidad_ecuatoriana')
  THEN RAISE EXCEPTION 'Evidencia de oferente insuficiente o convenio no habilitado'; END IF;
 END IF;
 IF NEW.sustituye_id IS NOT NULL THEN
  SELECT * INTO prev FROM "AUD_REVISION_RASTREO" WHERE id=NEW.sustituye_id;
  IF prev.id IS NULL OR prev.version_id IS DISTINCT FROM NEW.version_id
    OR prev.dimension <> NEW.dimension
    OR prev.evidencia_id IS DISTINCT FROM NEW.evidencia_id
    OR prev.creada_en > NEW.creada_en
  THEN RAISE EXCEPTION 'Sustitucion de otro objeto, evidencia o fecha'; END IF;
  IF EXISTS (SELECT 1 FROM "AUD_REVISION_RASTREO" WHERE sustituye_id=NEW.sustituye_id)
  THEN RAISE EXCEPTION 'Revision ya sustituida'; END IF;
 END IF;
 NEW.creada_en := statement_timestamp();
 RETURN NEW;
END $$;
CREATE TRIGGER rast_revision_editorial_guard BEFORE INSERT ON "AUD_REVISION_RASTREO"
 FOR EACH ROW EXECUTE FUNCTION rastreo_revision_editorial_guard();
'''


class Migration(migrations.Migration):
    dependencies = [('rastreo', '0006_revision_editorial')]
    operations = [migrations.RunSQL(SQL, 'DROP FUNCTION rastreo_revision_editorial_guard() CASCADE;')]
