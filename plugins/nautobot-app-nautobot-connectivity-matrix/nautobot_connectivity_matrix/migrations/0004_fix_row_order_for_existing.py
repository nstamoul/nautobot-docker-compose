from django.db import migrations


def fix_row_order(apps, schema_editor):
    ConnectionPlanBatch = apps.get_model("nautobot_connectivity_matrix", "ConnectionPlanBatch")
    ConnectionPlan = apps.get_model("nautobot_connectivity_matrix", "ConnectionPlan")

    for batch in ConnectionPlanBatch.objects.all().iterator():
        missing = ConnectionPlan.objects.filter(batch_id=batch.pk, row_order=0).order_by("created", "pk")
        if not missing.exists():
            continue

        current_max = (
            ConnectionPlan.objects.filter(batch_id=batch.pk)
            .exclude(row_order=0)
            .aggregate(m=__import__("django").db.models.Max("row_order"))
            .get("m")
            or 0
        )

        for idx, plan in enumerate(missing.iterator(), start=current_max + 1):
            ConnectionPlan.objects.filter(pk=plan.pk).update(row_order=idx)


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_connectivity_matrix", "0003_add_row_order"),
    ]

    operations = [
        migrations.RunPython(fix_row_order, migrations.RunPython.noop),
    ]
