from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('convocatorias', '0007_vinculo_borrador_automatico')]

    operations = [migrations.RemoveConstraint(model_name='convocatoria', name='conv_validada_oferente')]
