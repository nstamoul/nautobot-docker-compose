"""Initial migration for nautobot_connectivity_matrix."""

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Initial migration creating ConnectionPlanBatch and ConnectionPlan models."""

    initial = True

    dependencies = [
        ("dcim", "__first__"),
        ("tenancy", "__first__"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConnectionPlanBatch",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "name",
                    models.CharField(
                        help_text="Name for this batch of connection plans",
                        max_length=100,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Description or notes about this batch",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending Review"),
                            ("approved", "Approved"),
                            ("executing", "Executing"),
                            ("completed", "Completed"),
                            ("partial", "Partially Completed"),
                        ],
                        default="pending",
                        help_text="Current workflow status",
                        max_length=20,
                    ),
                ),
                (
                    "location",
                    models.ForeignKey(
                        blank=True,
                        help_text="Location scope for this batch",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="connection_plan_batches",
                        to="dcim.location",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        help_text="Tenant scope for this batch",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="connection_plan_batches",
                        to="tenancy.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Connection Plan Batch",
                "verbose_name_plural": "Connection Plan Batches",
                "ordering": ["-created"],
            },
        ),
        migrations.CreateModel(
            name="ConnectionPlan",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "device_a_name",
                    models.CharField(
                        blank=True,
                        help_text="Override: device name if not in Nautobot",
                        max_length=100,
                    ),
                ),
                (
                    "interface_a_name",
                    models.CharField(
                        blank=True,
                        help_text="Override: interface name if not in Nautobot",
                        max_length=100,
                    ),
                ),
                (
                    "sfp_a",
                    models.CharField(
                        blank=True,
                        help_text="SFP/transceiver type for source",
                        max_length=100,
                    ),
                ),
                (
                    "device_b_name",
                    models.CharField(
                        blank=True,
                        help_text="Override: device name if not in Nautobot",
                        max_length=100,
                    ),
                ),
                (
                    "interface_b_name",
                    models.CharField(
                        blank=True,
                        help_text="Override: interface name if not in Nautobot",
                        max_length=100,
                    ),
                ),
                (
                    "sfp_b",
                    models.CharField(
                        blank=True,
                        help_text="SFP/transceiver type for destination",
                        max_length=100,
                    ),
                ),
                (
                    "medium",
                    models.CharField(
                        choices=[
                            ("RJ45", "RJ45/Copper"),
                            ("SMF", "Singlemode Fiber"),
                            ("MMF", "Multimode Fiber"),
                            ("DAC", "Direct Attach Copper"),
                            ("AOC", "Active Optical Cable"),
                            ("STACK", "Stack Cable"),
                            ("WIRELESS", "Wireless"),
                        ],
                        default="RJ45",
                        help_text="Cable medium type",
                        max_length=50,
                    ),
                ),
                (
                    "speed",
                    models.CharField(
                        choices=[
                            ("10M", "10 Mbps"),
                            ("100M", "100 Mbps"),
                            ("1G", "1 Gbps"),
                            ("2.5G", "2.5 Gbps"),
                            ("5G", "5 Gbps"),
                            ("10G", "10 Gbps"),
                            ("25G", "25 Gbps"),
                            ("40G", "40 Gbps"),
                            ("50G", "50 Gbps"),
                            ("100G", "100 Gbps"),
                            ("200G", "200 Gbps"),
                            ("400G", "400 Gbps"),
                        ],
                        default="1G",
                        help_text="Connection speed",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("validated", "Validated"),
                            ("approved", "Approved"),
                            ("executed", "Executed"),
                            ("conflict", "Conflict"),
                            ("failed", "Failed"),
                        ],
                        default="draft",
                        help_text="Current workflow status",
                        max_length=20,
                    ),
                ),
                (
                    "validation_errors",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of validation error messages",
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        help_text="Additional notes about this connection",
                    ),
                ),
                (
                    "batch",
                    models.ForeignKey(
                        help_text="Batch this plan belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="connection_plans",
                        to="nautobot_connectivity_matrix.connectionplanbatch",
                    ),
                ),
                (
                    "created_cable",
                    models.ForeignKey(
                        blank=True,
                        help_text="Cable created from this plan",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_connection_plan",
                        to="dcim.cable",
                    ),
                ),
                (
                    "device_a",
                    models.ForeignKey(
                        blank=True,
                        help_text="Source device (from Nautobot)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="connection_plans_as_a",
                        to="dcim.device",
                    ),
                ),
                (
                    "device_b",
                    models.ForeignKey(
                        blank=True,
                        help_text="Destination device (from Nautobot)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="connection_plans_as_b",
                        to="dcim.device",
                    ),
                ),
                (
                    "interface_a",
                    models.ForeignKey(
                        blank=True,
                        help_text="Source interface (from Nautobot)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="connection_plans_as_a",
                        to="dcim.interface",
                    ),
                ),
                (
                    "interface_b",
                    models.ForeignKey(
                        blank=True,
                        help_text="Destination interface (from Nautobot)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="connection_plans_as_b",
                        to="dcim.interface",
                    ),
                ),
            ],
            options={
                "verbose_name": "Connection Plan",
                "verbose_name_plural": "Connection Plans",
                "ordering": ["batch", "device_a__name", "interface_a__name"],
            },
        ),
    ]
