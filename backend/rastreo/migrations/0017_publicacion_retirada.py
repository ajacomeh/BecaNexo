"""Marca de ficha retirada por la fuente (retirada_en) y guarda de identidad que la admite.

El disparador rast_publicacion_guard solo permite actualizar ultima_deteccion y convocatoria_id; ahora también
retirada_en. La reversión restaura la guarda anterior (0011) y elimina la columna.
"""
from django.db import migrations, models


def guarda(columnas):
    return f'''
CREATE OR REPLACE FUNCTION rastreo_publicacion_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.convocatoria_id IS NOT NULL THEN RAISE EXCEPTION 'La publicacion nace sin vinculo'; END IF;
 ELSE
  IF (to_jsonb(NEW)-ARRAY[{columnas}]) IS DISTINCT FROM
     (to_jsonb(OLD)-ARRAY[{columnas}]) OR NEW.ultima_deteccion < OLD.ultima_deteccion
     OR (OLD.convocatoria_id IS NOT NULL AND NEW.convocatoria_id IS DISTINCT FROM OLD.convocatoria_id)
  THEN RAISE EXCEPTION 'Identidad y vinculo inmutables'; END IF;
 END IF;
 RETURN NEW;
END $$;
'''


ANTERIOR = guarda("'ultima_deteccion','convocatoria_id'")
NUEVA = guarda("'ultima_deteccion','convocatoria_id','retirada_en'")


class Migration(migrations.Migration):
    dependencies = [('rastreo', '0016_evidencia_observada_por_contenido')]
    operations = [
        migrations.AddField(model_name='publicacion', name='retirada_en', field=models.DateTimeField(blank=True, null=True)),
        migrations.RunSQL(NUEVA, ANTERIOR),
    ]
