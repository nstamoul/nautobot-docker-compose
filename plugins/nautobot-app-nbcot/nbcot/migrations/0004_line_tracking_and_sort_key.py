# Generated manually for NBCOT line tracking and natural ordering.

from django.db import migrations, models


def populate_line_sort_keys(apps, _schema_editor):
    """Backfill natural sort keys for existing order lines."""
    CiscoOrderLine = apps.get_model("nbcot", "CiscoOrderLine")
    for line in CiscoOrderLine.objects.all().iterator():
        values = []
        for part in str(line.line_number or "").split("."):
            if not part:
                continue
            try:
                values.append(f"{int(part):08d}")
            except ValueError:
                values.append(f"~{part}")
        line.line_sort_key = ".".join(values)
        line.save(update_fields=["line_sort_key"])


class Migration(migrations.Migration):
    """Add item-level tracking and natural line ordering."""

    dependencies = [
        ("nbcot", "0003_ciscoorder_environment"),
    ]

    operations = [
        migrations.AddField(
            model_name="ciscoorderline",
            name="is_tracked",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="ciscoorderline",
            name="line_sort_key",
            field=models.CharField(blank=True, editable=False, max_length=255),
        ),
        migrations.RunPython(populate_line_sort_keys, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="ciscoorderline",
            options={
                "ordering": ["order__order_number", "line_sort_key", "line_key"],
                "verbose_name": "Cisco order line",
                "verbose_name_plural": "Cisco order lines",
            },
        ),
    ]
