"""Django tables for the Connectivity Matrix Diagram app."""

import django_tables2 as tables

from nautobot.apps.tables import BaseTable, ButtonsColumn, ToggleColumn

from .models import ConnectionPlanBatch, ConnectionPlan


class ConnectionPlanBatchTable(BaseTable):
    """Table for listing connection plan batches."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    tenant = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    status = tables.Column()
    connection_count = tables.Column(verbose_name="Connections")
    validated_count = tables.Column(verbose_name="Validated")
    executed_count = tables.Column(verbose_name="Executed")
    actions = ButtonsColumn(ConnectionPlanBatch)

    class Meta(BaseTable.Meta):
        model = ConnectionPlanBatch
        fields = [
            "pk",
            "name",
            "tenant",
            "location",
            "status",
            "connection_count",
            "validated_count",
            "executed_count",
            "created",
            "actions",
        ]
        default_columns = [
            "pk",
            "name",
            "tenant",
            "location",
            "status",
            "connection_count",
            "actions",
        ]


class ConnectionPlanTable(BaseTable):
    """Table for listing connection plans within a batch."""

    pk = ToggleColumn()
    device_a_display = tables.Column(verbose_name="Device A")
    interface_a_display = tables.Column(verbose_name="Interface A")
    sfp_a = tables.Column(verbose_name="SFP A")
    medium = tables.Column()
    speed = tables.Column()
    device_b_display = tables.Column(verbose_name="Device B")
    interface_b_display = tables.Column(verbose_name="Interface B")
    sfp_b = tables.Column(verbose_name="SFP B")
    status = tables.Column()

    class Meta(BaseTable.Meta):
        model = ConnectionPlan
        fields = [
            "pk",
            "device_a_display",
            "interface_a_display",
            "sfp_a",
            "medium",
            "speed",
            "device_b_display",
            "interface_b_display",
            "sfp_b",
            "status",
        ]
