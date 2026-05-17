"""Models for NBCOT."""

from django.db import models
from django.utils import timezone
from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
from nautobot.apps.models import BaseModel, PrimaryModel, extras_features

from nbcot.choices import CiscoEnvironmentChoices, ChangeSourceChoices, OrderUpdateTypeChoices, SyncStatusChoices
from nbcot.cisco.line_items import line_number_sort_value


@extras_features("custom_links", "custom_validators", "export_templates", "graphql", "webhooks")
class CiscoOrder(PrimaryModel):  # pylint: disable=too-many-ancestors
    """Tracked Cisco order state stored in Nautobot."""

    order_number = models.CharField(max_length=CHARFIELD_MAX_LENGTH)
    environment = models.CharField(max_length=16, choices=CiscoEnvironmentChoices, default=CiscoEnvironmentChoices.POE)
    customer_po_number = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    account_name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    account_number = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    status = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    status_detail = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    lifecycle_state = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    is_tracked = models.BooleanField(default=True)
    open_exception_count = models.PositiveIntegerField(default=0)
    requested_delivery_date = models.DateField(null=True, blank=True)
    promised_delivery_date = models.DateField(null=True, blank=True)
    estimated_delivery_date = models.DateField(null=True, blank=True)
    ordered_at = models.DateTimeField(null=True, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(
        max_length=32,
        choices=SyncStatusChoices,
        default=SyncStatusChoices.PENDING,
    )
    last_sync_message = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        """Meta class."""

        ordering = ["-last_synced_at", "order_number"]
        unique_together = ("environment", "order_number")
        verbose_name = "Cisco order"
        verbose_name_plural = "Cisco orders"

    def __str__(self):
        """Stringify instance."""
        return self.order_number


class CiscoOrderLine(BaseModel):
    """Current normalized line-level state for a tracked Cisco order."""

    order = models.ForeignKey(CiscoOrder, on_delete=models.CASCADE, related_name="lines")
    line_key = models.CharField(max_length=CHARFIELD_MAX_LENGTH)
    line_number = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    line_sort_key = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True, editable=False)
    sku = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    description = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    shipment_status = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    is_tracked = models.BooleanField(default=False)
    quantity_ordered = models.PositiveIntegerField(default=0)
    quantity_fulfilled = models.PositiveIntegerField(default=0)
    quantity_backordered = models.PositiveIntegerField(default=0)
    promised_delivery_date = models.DateField(null=True, blank=True)
    estimated_delivery_date = models.DateField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        """Meta class."""

        ordering = ["order__order_number", "line_sort_key", "line_key"]
        unique_together = ("order", "line_key")
        verbose_name = "Cisco order line"
        verbose_name_plural = "Cisco order lines"

    def save(self, *args, **kwargs):
        """Set the sortable line key before saving."""
        self.line_sort_key = line_number_sort_value(self.line_number)
        super().save(*args, **kwargs)

    def __str__(self):
        """Stringify instance."""
        label = self.line_number or self.line_key
        return f"{self.order.order_number} line {label}"


class CiscoOrderUpdate(BaseModel):
    """Append-only change log entry for a tracked Cisco order."""

    order = models.ForeignKey(CiscoOrder, on_delete=models.CASCADE, related_name="updates")
    update_type = models.CharField(max_length=32, choices=OrderUpdateTypeChoices)
    source = models.CharField(max_length=16, choices=ChangeSourceChoices, default=ChangeSourceChoices.POLL)
    summary = models.CharField(max_length=255)
    occurred_at = models.DateTimeField(default=timezone.now)
    details = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        """Meta class."""

        ordering = ["-occurred_at", "-id"]
        verbose_name = "Cisco order update"
        verbose_name_plural = "Cisco order updates"

    def __str__(self):
        """Stringify instance."""
        return f"{self.order.order_number} {self.update_type} @ {self.occurred_at.isoformat()}"
