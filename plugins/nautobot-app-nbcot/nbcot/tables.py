"""Tables for nbcot."""

import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from nautobot.apps.tables import BaseTable, ButtonsColumn, ToggleColumn

from nbcot import models


class CiscoOrderTable(BaseTable):
    """Table for tracked orders."""

    pk = ToggleColumn()
    order_number = tables.Column(linkify=True)
    environment = tables.Column()
    status = tables.Column()
    promised_delivery_date = tables.DateColumn()
    estimated_delivery_date = tables.DateColumn()
    last_synced_at = tables.DateTimeColumn(format="Y-m-d H:i:s")
    actions = tables.Column(empty_values=(), orderable=False)

    class Meta(BaseTable.Meta):
        """Meta attributes."""

        model = models.CiscoOrder
        fields = (
            "pk",
            "order_number",
            "environment",
            "customer_po_number",
            "account_name",
            "status",
            "open_exception_count",
            "is_tracked",
            "promised_delivery_date",
            "estimated_delivery_date",
            "last_synced_at",
        )

    def render_actions(self, record):
        """Render row action buttons."""
        refresh_url = reverse("plugins:nbcot:ciscoorder_refresh", kwargs={"pk": record.pk})
        toggle_url = reverse("plugins:nbcot:ciscoorder_toggle_tracking", kwargs={"pk": record.pk})
        toggle_label = "Untrack" if record.is_tracked else "Track"
        toggle_class = "btn-warning" if record.is_tracked else "btn-success"
        return format_html(
            '<a class="btn btn-xs btn-primary" href="{}">Refresh</a> '
            '<a class="btn btn-xs {}" href="{}">{}</a>',
            refresh_url,
            toggle_class,
            toggle_url,
            toggle_label,
        )


class CiscoOrderLineTable(BaseTable):
    """Table for order lines."""

    line_key = tables.Column(linkify=False, verbose_name="Line Key")
    promised_delivery_date = tables.DateColumn()
    estimated_delivery_date = tables.DateColumn()

    class Meta(BaseTable.Meta):
        """Meta attributes."""

        model = models.CiscoOrderLine
        fields = (
            "line_number",
            "sku",
            "description",
            "status",
            "shipment_status",
            "is_tracked",
            "quantity_ordered",
            "quantity_fulfilled",
            "quantity_backordered",
            "promised_delivery_date",
            "estimated_delivery_date",
        )
        default_columns = fields


class CiscoOrderUpdateTable(BaseTable):
    """Table for order updates."""

    occurred_at = tables.DateTimeColumn(format="Y-m-d H:i:s")

    class Meta(BaseTable.Meta):
        """Meta attributes."""

        model = models.CiscoOrderUpdate
        fields = ("occurred_at", "update_type", "source", "summary")
        default_columns = fields
