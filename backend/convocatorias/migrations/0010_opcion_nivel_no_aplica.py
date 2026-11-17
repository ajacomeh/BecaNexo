from django.db import migrations, models
from django.db.models import Q


NIVELES_OPCION = (
    'bachillerato', 'grado', 'especializacion', 'maestria', 'doctorado', 'no_aplica',
)


class Migration(migrations.Migration):
    dependencies = [('convocatorias', '0009_opcion_modalidad_hibrida')]

    operations = [
        migrations.RemoveConstraint(model_name='opcionestudio', name='opcion_nivel'),
        migrations.AlterField(model_name='opcionestudio', name='nivel',
            field=models.CharField(max_length=30, choices=[
                ('bachillerato', 'Bachillerato'), ('grado', 'Tercer nivel / grado'),
                ('especializacion', 'Especialización'), ('maestria', 'Maestría'),
                ('doctorado', 'Doctorado'), ('no_aplica', 'No aplica (educación continua)'),
            ])),
        migrations.AddConstraint(model_name='opcionestudio',
            constraint=models.CheckConstraint(condition=Q(nivel__in=NIVELES_OPCION), name='opcion_nivel')),
    ]
