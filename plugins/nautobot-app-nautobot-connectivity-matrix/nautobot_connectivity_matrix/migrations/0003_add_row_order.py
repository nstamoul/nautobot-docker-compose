from django.db import migrations, models


def populate_row_order(apps, schema_editor):
    ConnectionPlanBatch = apps.get_model("nautobot_connectivity_matrix", "ConnectionPlanBatch")
    ConnectionPlan = apps.get_model("nautobot_connectivity_matrix", "ConnectionPlan")

    for batch in ConnectionPlanBatch.objects.all().iterator():
        plans = ConnectionPlan.objects.filter(batch_id=batch.pk).order_by("created", "pk")
        for idx, plan in enumerate(plans.iterator(), start=1):
            ConnectionPlan.objects.filter(pk=plan.pk).update(row_order=idx)


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_connectivity_matrix", "0002_add_custom_field_data"),
    ]

    operations = [
        migrations.AddField(
            model_name="connectionplan",
            name="row_order",
            field=models.PositiveIntegerField(
                default=0,
                db_index=True,
                help_text="Display order for this row within its batch",
            ),
        ),
        migrations.RunPython(populate_row_order, migrations.RunPython.noop),
    ]
