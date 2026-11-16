from django.db import migrations, models
from django.db.models import Q


MODALIDADES = ('presencial', 'virtual', 'semipresencial', 'hibrida')


class Migration(migrations.Migration):
    dependencies = [
        ('perfiles', '0003_preferencia_modalidad_hibrida'),
        ('convocatorias', '0008_publicacion_sin_oferente'),
    ]

    operations = [
        migrations.RemoveConstraint(model_name='opcionestudio', name='opcion_modalidad'),
        migrations.AlterField(model_name='opcionestudio', name='modalidad',
            field=models.CharField(max_length=20, choices=[
                ('presencial', 'Presencial'), ('virtual', 'Virtual'),
                ('semipresencial', 'Semipresencial'), ('hibrida', 'Híbrida')])),
        migrations.AddConstraint(model_name='opcionestudio',
            constraint=models.CheckConstraint(condition=Q(modalidad__in=MODALIDADES),
                                              name='opcion_modalidad')),
    ]
