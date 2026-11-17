from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('rastreo', '0014_candidato_indice')]

    operations = [
        migrations.AlterField(
            model_name='fuente',
            name='frecuencia_min',
            field=models.PositiveIntegerField(default=720),
        ),
    ]
