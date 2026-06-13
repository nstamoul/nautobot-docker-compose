# Generated manually for NBCOT Cisco order URL and serial attribute fields.

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add order URLs and extended serial attributes."""

    dependencies = [
        ("nbcot", "0006_order_metadata_archive_notifications"),
    ]

    operations = [
        migrations.AddField(
            model_name="ciscoorder",
            name="web_order_url",
            field=models.URLField(blank=True, max_length=1024),
        ),
        migrations.AddField(
            model_name="ciscoorder",
            name="cisco_sales_order_url",
            field=models.URLField(blank=True, max_length=1024),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="parent_serial_number",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="imei_number",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="license_key",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="cloud_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="contract_number",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
