"""Align app migrations with Nautobot 3 PrimaryModel fields."""

import uuid

import django.core.serializers.json
import nautobot.core.models.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0142_remove_scheduledjob_approval_required"),
        ("nautobot_connectivity_matrix", "0004_fix_row_order_for_existing"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="connectionplan",
            options={
                "ordering": ["batch", "row_order", "created"],
                "verbose_name": "Connection Plan",
                "verbose_name_plural": "Connection Plans",
            },
        ),
        migrations.AddField(
            model_name="connectionplan",
            name="tags",
            field=nautobot.core.models.fields.TagsField(through="extras.TaggedItem", to="extras.Tag"),
        ),
        migrations.AddField(
            model_name="connectionplanbatch",
            name="tags",
            field=nautobot.core.models.fields.TagsField(through="extras.TaggedItem", to="extras.Tag"),
        ),
        migrations.AlterField(
            model_name="connectionplan",
            name="_custom_field_data",
            field=models.JSONField(blank=True, default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder),
        ),
        migrations.AlterField(
            model_name="connectionplan",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True),
        ),
        migrations.AlterField(
            model_name="connectionplanbatch",
            name="_custom_field_data",
            field=models.JSONField(blank=True, default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder),
        ),
        migrations.AlterField(
            model_name="connectionplanbatch",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True),
        ),
    ]
