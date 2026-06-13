"""Add missing Nautobot custom field storage columns.

The initial cookiecutter-generated migration created the plugin models without the
`_custom_field_data` JSONField that Nautobot's `PrimaryModel` provides. Under
Nautobot 2.4.x, the runtime models include this field, so attempts to create
instances fail with:

    django.db.utils.ProgrammingError: column "_custom_field_data" ... does not exist
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add `_custom_field_data` to plugin models."""

    dependencies = [
        ("nautobot_connectivity_matrix", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="connectionplanbatch",
            name="_custom_field_data",
            field=models.JSONField(blank=True, db_column="_custom_field_data", default=dict),
        ),
        migrations.AddField(
            model_name="connectionplan",
            name="_custom_field_data",
            field=models.JSONField(blank=True, db_column="_custom_field_data", default=dict),
        ),
    ]
