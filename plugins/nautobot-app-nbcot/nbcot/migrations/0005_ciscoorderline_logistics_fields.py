# Generated manually for NBCOT line-level logistics fields.

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add serial, freight, and tracking fields to Cisco order lines."""

    dependencies = [
        ("nbcot", "0004_line_tracking_and_sort_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="ciscoorderline",
            name="actual_delivery_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="carrier",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="estimated_ship_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="instance_number",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="mac_address",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="proof_of_delivery_url",
            field=models.URLField(blank=True, max_length=1024),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="serial_number",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="ship_set",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="tracking_number",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="tracking_url",
            field=models.URLField(blank=True, max_length=1024),
        ),
    ]
