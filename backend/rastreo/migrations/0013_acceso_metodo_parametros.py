from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [('rastreo', '0012_permitir_rectificaciones_integracion')]

    operations = [
        migrations.AddField(
            model_name='acceso',
            name='metodo',
            field=models.CharField(default='GET', max_length=4),
        ),
        migrations.AddField(
            model_name='acceso',
            name='parametros_publicos',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name='acceso',
            constraint=models.CheckConstraint(
                condition=Q(metodo='GET', parametros_publicos__isnull=True)
                | Q(metodo='POST', parametros_publicos__isnull=False),
                name='rast_acceso_metodo',
            ),
        ),
    ]
