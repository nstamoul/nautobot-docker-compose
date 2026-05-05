# Generated manually for the online workbench redesign.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Add online workbench defaults and row metadata."""

    dependencies = [
        ("dcim", "__first__"),
        ("extras", "__first__"),
        ("nautobot_connectivity_matrix", "0005_align_primarymodel_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="connectionplanbatch",
            name="default_device_role",
            field=models.ForeignKey(
                blank=True,
                help_text="Role to use when materializing unresolved device names",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="connection_plan_batches_as_default",
                to="extras.role",
            ),
        ),
        migrations.AddField(
            model_name="connectionplanbatch",
            name="default_device_status",
            field=models.ForeignKey(
                blank=True,
                help_text="Status to use when materializing unresolved device names",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="connection_plan_batches_as_default",
                to="extras.status",
            ),
        ),
        migrations.AddField(
            model_name="connectionplanbatch",
            name="default_device_type",
            field=models.ForeignKey(
                blank=True,
                help_text="Device type to use when materializing unresolved device names",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="connection_plan_batches_as_default",
                to="dcim.devicetype",
            ),
        ),
        migrations.AddField(
            model_name="connectionplanbatch",
            name="default_platform",
            field=models.ForeignKey(
                blank=True,
                help_text="Platform to use when materializing unresolved device names",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="connection_plan_batches_as_default",
                to="dcim.platform",
            ),
        ),
        migrations.AddField(
            model_name="connectionplan",
            name="row_color",
            field=models.CharField(blank=True, help_text="Visual row marker color as #rrggbb", max_length=7),
        ),
        migrations.AddField(
            model_name="connectionplan",
            name="validation_warnings",
            field=models.JSONField(blank=True, default=list, help_text="List of non-blocking validation warning messages"),
        ),
    ]
