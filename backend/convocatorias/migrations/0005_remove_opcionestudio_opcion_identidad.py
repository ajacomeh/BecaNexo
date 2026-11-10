from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("convocatorias", "0004_remove_beneficio_beneficio_tope_literal_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="opcionestudio",
            name="opcion_identidad",
        ),
    ]
