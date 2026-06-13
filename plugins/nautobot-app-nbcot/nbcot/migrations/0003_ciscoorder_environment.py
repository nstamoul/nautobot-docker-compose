"""Add Cisco environment to tracked orders."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add environment field to CiscoOrder."""

    dependencies = [
        ("nbcot", "0002_alter_ciscoorderupdate_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="ciscoorder",
            name="environment",
            field=models.CharField(
                choices=[("poe", "POE"), ("prod", "PROD"), ("uat", "UAT")],
                default="poe",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="ciscoorder",
            name="order_number",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterUniqueTogether(
            name="ciscoorder",
            unique_together={("environment", "order_number")},
        ),
    ]
