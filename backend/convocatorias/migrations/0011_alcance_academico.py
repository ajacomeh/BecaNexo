from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("convocatorias", "0010_opcion_nivel_no_aplica")]

    operations = [
        migrations.AddField(
            model_name="convocatoria", name="alcance_academico",
            field=models.CharField(max_length=20, default="pendiente", choices=[
                ("pendiente", "Pendiente de confirmar"),
                ("programas", "Programas específicos"),
                ("transversal", "Transversal institucional"),
            ]),
        ),
        migrations.AddField(model_name="convocatoria", name="alcance_detalle",
                            field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="convocatoria", name="alcance_exclusiones",
                            field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="convocatoria", name="alcance_sede",
                            field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="convocatoria", name="alcance_periodo",
                            field=models.TextField(blank=True, default="")),
        migrations.AddConstraint(model_name="convocatoria", constraint=models.CheckConstraint(
            condition=Q(alcance_academico__in=["pendiente", "programas", "transversal"]),
            name="conv_alcance_academico",
        )),
    ]
