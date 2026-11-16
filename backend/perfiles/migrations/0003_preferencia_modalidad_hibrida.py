from django.db import migrations, models
from django.db.models import Q


MODALIDADES = ('presencial', 'virtual', 'semipresencial', 'hibrida')


class Migration(migrations.Migration):
    dependencies = [('perfiles', '0002_perfil_descripcion')]

    operations = [
        migrations.RemoveConstraint(model_name='preferencia', name='preferencia_modalidad'),
        migrations.AlterField(model_name='preferencia', name='modalidad',
            field=models.CharField(max_length=20, choices=[
                ('presencial', 'Presencial'), ('virtual', 'Virtual'),
                ('semipresencial', 'Semipresencial'), ('hibrida', 'Híbrida')])),
        migrations.AddConstraint(model_name='preferencia',
            constraint=models.CheckConstraint(condition=Q(modalidad__in=MODALIDADES),
                                              name='preferencia_modalidad')),
    ]
