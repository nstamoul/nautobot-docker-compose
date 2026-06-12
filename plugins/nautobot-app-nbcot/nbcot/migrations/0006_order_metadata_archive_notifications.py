# Generated manually for NBCOT tracked order workflow fields.

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add local metadata, archive state, and notification targets to orders."""

    dependencies = [
        ("nbcot", "0005_ciscoorderline_logistics_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="ciscoorder",
            name="is_archived",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="ciscoorder",
            name="project_number",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ciscoorder",
            name="notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="ciscoorder",
            name="notification_recipients",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="ciscoorder",
            name="notification_teams_webhook_url",
            field=models.URLField(blank=True, max_length=1024),
        ),
    ]
