from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from django.db.models import Q, F


class Migration(migrations.Migration):
    dependencies = [('rastreo', '0013_acceso_metodo_parametros')]

    operations = [
        migrations.CreateModel(
            name='CandidatoIndice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url_normalizada', models.CharField(max_length=2048)),
                ('titulo_publico', models.CharField(max_length=200)),
                ('pagina', models.PositiveSmallIntegerField()),
                ('respuesta_sha256', models.CharField(max_length=64)),
                ('primera_deteccion', models.DateTimeField(default=django.utils.timezone.now)),
                ('ultima_deteccion', models.DateTimeField(default=django.utils.timezone.now)),
                ('fuente', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='rastreo.fuente')),
                ('ultima_ejecucion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='rastreo.ejecucion')),
            ],
            options={'db_table': 'TRA_CANDIDATO_INDICE'},
        ),
        migrations.AddConstraint('candidatoindice', models.UniqueConstraint(fields=('fuente', 'url_normalizada'), name='rast_candidato_indice_url')),
        migrations.AddConstraint('candidatoindice', models.CheckConstraint(condition=Q(ultima_deteccion__gte=F('primera_deteccion')), name='rast_candidato_indice_fecha')),
        migrations.AddConstraint('candidatoindice', models.CheckConstraint(condition=Q(pagina__gt=0, pagina__lte=12), name='rast_candidato_indice_pagina')),
        migrations.AddConstraint('candidatoindice', models.CheckConstraint(condition=Q(respuesta_sha256__regex=r'^[0-9a-f]{64}$'), name='rast_candidato_indice_hash')),
    ]
