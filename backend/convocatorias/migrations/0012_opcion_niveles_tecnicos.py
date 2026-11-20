from django.db import migrations, models
from django.db.models import Q


NIVELES_OPCION = (
    'bachillerato', 'grado', 'especializacion', 'maestria', 'doctorado',
    'tecnico_superior', 'tecnologico_superior', 'maestria_tecnologica', 'no_aplica',
)


class Migration(migrations.Migration):
    """Amplía solo el catálogo de niveles de las opciones de estudio (MAE_OPCION_ESTUDIO).

    Los datos existentes no cambian: únicamente se admiten tres valores nuevos. Los perfiles y
    las preferencias de postulantes conservan su catálogo de niveles actual.
    """
    dependencies = [('convocatorias', '0011_alcance_academico')]

    operations = [
        migrations.RemoveConstraint(model_name='opcionestudio', name='opcion_nivel'),
        migrations.AlterField(model_name='opcionestudio', name='nivel',
            field=models.CharField(max_length=30, choices=[
                ('bachillerato', 'Bachillerato'), ('grado', 'Tercer nivel / grado'),
                ('especializacion', 'Especialización'), ('maestria', 'Maestría'),
                ('doctorado', 'Doctorado'), ('tecnico_superior', 'Técnico superior'),
                ('tecnologico_superior', 'Tecnológico superior'), ('maestria_tecnologica', 'Maestría tecnológica'),
                ('no_aplica', 'No aplica (educación continua)'),
            ])),
        migrations.AddConstraint(model_name='opcionestudio',
            constraint=models.CheckConstraint(condition=Q(nivel__in=NIVELES_OPCION), name='opcion_nivel')),
    ]
