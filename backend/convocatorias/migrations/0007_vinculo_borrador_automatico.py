from django.db import migrations


FORWARD = '''
CREATE OR REPLACE FUNCTION rastreo_vinculo_auditado() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.convocatoria_id IS DISTINCT FROM OLD.convocatoria_id AND NOT EXISTS (
  SELECT 1 FROM "AUD_REVISION_RASTREO" r JOIN "TRA_PROPUESTA_CAMBIO" p ON p.id=r.propuesta_id
  WHERE p.publicacion_id=NEW.id AND r.convocatoria_id=NEW.convocatoria_id
   AND r.dimension='integracion' AND r.decision='aplicada' AND r.transaccion_id=txid_current()
 ) AND NOT EXISTS (
  SELECT 1 FROM "TRA_BORRADOR_RASTREO" b
  WHERE b.publicacion_id=NEW.id AND b.convocatoria_id=NEW.convocatoria_id
   AND EXISTS (SELECT 1 FROM "MAE_CONVOCATORIA" c WHERE c.id=b.convocatoria_id AND c.revision='pendiente')
 ) THEN RAISE EXCEPTION 'Vinculo requiere integracion auditada atomica'; END IF;
 RETURN NULL;
END $$;
'''

BACKWARD = '''
CREATE OR REPLACE FUNCTION rastreo_vinculo_auditado() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.convocatoria_id IS DISTINCT FROM OLD.convocatoria_id AND NOT EXISTS (
  SELECT 1 FROM "AUD_REVISION_RASTREO" r JOIN "TRA_PROPUESTA_CAMBIO" p ON p.id=r.propuesta_id
  WHERE p.publicacion_id=NEW.id AND r.convocatoria_id=NEW.convocatoria_id
   AND r.dimension='integracion' AND r.decision='aplicada' AND r.transaccion_id=txid_current()
 ) THEN RAISE EXCEPTION 'Vinculo requiere integracion auditada atomica'; END IF;
 RETURN NULL;
END $$;
'''

PROPOSAL_FORWARD = '''
CREATE OR REPLACE FUNCTION rastreo_propuesta_no_aplicada() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM id FROM "TRA_PUBLICACION_FUENTE" WHERE id=NEW.publicacion_id FOR UPDATE;
 IF EXISTS (
  SELECT 1 FROM "TRA_PUBLICACION_FUENTE" p
  WHERE p.id=NEW.publicacion_id AND p.convocatoria_id IS NOT NULL
   AND NOT EXISTS (
    SELECT 1 FROM "TRA_BORRADOR_RASTREO" b
    WHERE b.publicacion_id=p.id AND b.convocatoria_id=p.convocatoria_id
   )
 ) THEN RAISE EXCEPTION 'Publicacion ya integrada; no admite sucesores'; END IF;
 RETURN NEW;
END $$;
'''

PROPOSAL_BACKWARD = '''
CREATE OR REPLACE FUNCTION rastreo_propuesta_no_aplicada() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM id FROM "TRA_PUBLICACION_FUENTE" WHERE id=NEW.publicacion_id FOR UPDATE;
 IF EXISTS (SELECT 1 FROM "TRA_PUBLICACION_FUENTE" WHERE id=NEW.publicacion_id AND convocatoria_id IS NOT NULL)
 THEN RAISE EXCEPTION 'Publicacion ya integrada; no admite sucesores'; END IF;
 RETURN NEW;
END $$;
'''


class Migration(migrations.Migration):
    dependencies = [
        ('rastreo', '0012_permitir_rectificaciones_integracion'),
        ('convocatorias', '0006_borrador_automatico'),
    ]
    operations = [migrations.RunSQL(FORWARD, BACKWARD),
                  migrations.RunSQL(PROPOSAL_FORWARD, PROPOSAL_BACKWARD)]
