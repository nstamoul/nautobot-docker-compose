"""Models for the Connectivity Matrix Diagram app."""

from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.db.models import Max

from nautobot.apps.models import PrimaryModel
from nautobot.dcim.models import Cable


# Choices for connection attributes
MEDIUM_CHOICES = [
    ("RJ45", "RJ45/Copper"),
    ("SMF", "Singlemode Fiber"),
    ("MMF", "Multimode Fiber"),
    ("DAC", "Direct Attach Copper"),
    ("AOC", "Active Optical Cable"),
    ("STACK", "Stack Cable"),
    ("WIRELESS", "Wireless"),
]

SPEED_CHOICES = [
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
]

PLAN_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("validated", "Validated"),
    ("approved", "Approved"),
    ("executed", "Executed"),
    ("conflict", "Conflict"),
    ("failed", "Failed"),
]

BATCH_STATUS_CHOICES = [
    ("pending", "Pending Review"),
    ("approved", "Approved"),
    ("executing", "Executing"),
    ("completed", "Completed"),
    ("partial", "Partially Completed"),
]


class ConnectionPlanBatch(PrimaryModel):
    """
    Groups multiple ConnectionPlans for bulk operations.

    Represents a planning session, Excel import, or set of related connections.
    """

    # Nautobot v3 uses natural keys/slugs in core templates; define one explicitly for this model.
    natural_key_field_names = ("name",)

    name = models.CharField(
        max_length=100,
        help_text="Name for this batch of connection plans"
    )
    description = models.TextField(
        blank=True,
        help_text="Description or notes about this batch"
    )

    # Scoping filters
    tenant = models.ForeignKey(
        to="tenancy.Tenant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_plan_batches",
        help_text="Tenant scope for this batch"
    )
    location = models.ForeignKey(
        to="dcim.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_plan_batches",
        help_text="Location scope for this batch"
    )
    default_device_type = models.ForeignKey(
        to="dcim.DeviceType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_plan_batches_as_default",
        help_text="Device type to use when materializing unresolved device names",
    )
    default_device_role = models.ForeignKey(
        to="extras.Role",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_plan_batches_as_default",
        help_text="Role to use when materializing unresolved device names",
    )
    default_platform = models.ForeignKey(
        to="dcim.Platform",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_plan_batches_as_default",
        help_text="Platform to use when materializing unresolved device names",
    )
    default_device_status = models.ForeignKey(
        to="extras.Status",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_plan_batches_as_default",
        help_text="Status to use when materializing unresolved device names",
    )

    # Workflow status
    status = models.CharField(
        max_length=20,
        choices=BATCH_STATUS_CHOICES,
        default="pending",
        help_text="Current workflow status"
    )

    class Meta:
        verbose_name = "Connection Plan Batch"
        verbose_name_plural = "Connection Plan Batches"
        ordering = ["-created"]

    def __str__(self):
        return self.name

    @property
    def connection_count(self):
        """Return the number of connection plans in this batch."""
        return self.connection_plans.count()

    @property
    def validated_count(self):
        """Return the number of validated connection plans."""
        return self.connection_plans.filter(status="validated").count()

    @property
    def executed_count(self):
        """Return the number of executed connection plans."""
        return self.connection_plans.filter(status="executed").count()


class ConnectionPlan(PrimaryModel):
    """
    Represents a planned cable connection before actual Cable creation.

    Each row in the spreadsheet UI corresponds to one ConnectionPlan.
    Supports both FK references to existing devices/interfaces and
    override text fields for planning connections to not-yet-created devices.
    """

    # Batch grouping
    batch = models.ForeignKey(
        to=ConnectionPlanBatch,
        on_delete=models.CASCADE,
        related_name="connection_plans",
        help_text="Batch this plan belongs to"
    )
    row_order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Display order for this row within its batch",
    )

    # Source endpoint - Device A
    device_a = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_plans_as_a",
        help_text="Source device (from Nautobot)"
    )
    device_a_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Override: device name if not in Nautobot"
    )
    interface_a = models.ForeignKey(
        to="dcim.Interface",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_plans_as_a",
        help_text="Source interface (from Nautobot)"
    )
    interface_a_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Override: interface name if not in Nautobot"
    )
    sfp_a = models.CharField(
        max_length=100,
        blank=True,
        help_text="SFP/transceiver type for source"
    )

    # Destination endpoint - Device B
    device_b = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_plans_as_b",
        help_text="Destination device (from Nautobot)"
    )
    device_b_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Override: device name if not in Nautobot"
    )
    interface_b = models.ForeignKey(
        to="dcim.Interface",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connection_plans_as_b",
        help_text="Destination interface (from Nautobot)"
    )
    interface_b_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Override: interface name if not in Nautobot"
    )
    sfp_b = models.CharField(
        max_length=100,
        blank=True,
        help_text="SFP/transceiver type for destination"
    )

    # Connection attributes
    medium = models.CharField(
        max_length=50,
        choices=MEDIUM_CHOICES,
        default="RJ45",
        help_text="Cable medium type"
    )
    speed = models.CharField(
        max_length=20,
        choices=SPEED_CHOICES,
        default="1G",
        help_text="Connection speed"
    )

    # Workflow status
    status = models.CharField(
        max_length=20,
        choices=PLAN_STATUS_CHOICES,
        default="draft",
        help_text="Current workflow status"
    )
    validation_errors = models.JSONField(
        default=list,
        blank=True,
        help_text="List of validation error messages"
    )
    validation_warnings = models.JSONField(
        default=list,
        blank=True,
        help_text="List of non-blocking validation warning messages",
    )

    # Link to created cable after execution
    created_cable = models.ForeignKey(
        to=Cable,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_connection_plan",
        help_text="Cable created from this plan"
    )

    # Notes
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this connection"
    )
    row_color = models.CharField(
        max_length=7,
        blank=True,
        help_text="Visual row marker color as #rrggbb",
    )

    class Meta:
        verbose_name = "Connection Plan"
        verbose_name_plural = "Connection Plans"
        ordering = ["batch", "row_order", "created"]

    def __str__(self):
        a_dev = self.device_a.name if self.device_a else self.device_a_name or "?"
        a_int = self.interface_a.name if self.interface_a else self.interface_a_name or "?"
        b_dev = self.device_b.name if self.device_b else self.device_b_name or "?"
        b_int = self.interface_b.name if self.interface_b else self.interface_b_name or "?"
        return f"{a_dev}:{a_int} <-> {b_dev}:{b_int}"

    def save(self, *args, **kwargs):
        if self._state.adding and self.batch_id and not self.row_order:
            with transaction.atomic():
                max_order = (
                    ConnectionPlan.objects.filter(batch_id=self.batch_id)
                    .aggregate(max_val=Max("row_order"))
                    .get("max_val")
                    or 0
                )
                self.row_order = max_order + 1
                return super().save(*args, **kwargs)

        return super().save(*args, **kwargs)

    @property
    def device_a_display(self):
        """Return display name for device A."""
        if self.device_a:
            return self.device_a.name
        return self.device_a_name or ""

    @property
    def device_b_display(self):
        """Return display name for device B."""
        if self.device_b:
            return self.device_b.name
        return self.device_b_name or ""

    @property
    def interface_a_display(self):
        """Return display name for interface A."""
        if self.interface_a:
            return self.interface_a.name
        return self.interface_a_name or ""

    @property
    def interface_b_display(self):
        """Return display name for interface B."""
        if self.interface_b:
            return self.interface_b.name
        return self.interface_b_name or ""

    def swap_endpoints(self):
        """Swap A/B endpoint fields while preserving row metadata and notes."""
        from .services.row_actions import swap_plan_endpoints

        swap_plan_endpoints(self)

    def validate_connection(self):
        """
        Validate this connection plan and update status.

        Returns:
            list: List of error messages (empty if valid)
        """
        from .services.validation import collect_row_reserved_interface_ids, validate_plan_row

        plan_rows = ConnectionPlan.objects.filter(batch=self.batch)
        reserved_interface_ids = collect_row_reserved_interface_ids(plan_rows, current_plan_id=self.pk)
        result = validate_plan_row(self, reserved_interface_ids=reserved_interface_ids)
        errors = result.blockers

        # Update status based on validation
        self.validation_errors = errors
        self.validation_warnings = result.warnings
        if errors:
            self.status = "conflict"
        elif self.status == "draft" or self.status == "conflict":
            self.status = "validated"

        return errors

    def execute(self):
        """
        Create a Cable in Nautobot from this connection plan.

        Returns:
            Cable: The created cable, or None if execution failed
        """
        if self.status != "approved":
            raise ValidationError("Can only execute approved plans")

        if not self.interface_a or not self.interface_b:
            raise ValidationError("Both interfaces must reference Nautobot objects to execute")

        try:
            from nautobot.extras.models import Status

            # Get or create Connected status
            connected_status = Status.objects.filter(name="Connected").first()

            cable = Cable.objects.create(
                termination_a=self.interface_a,
                termination_b=self.interface_b,
                status=connected_status,
                label=f"{self.speed} | {self.interface_a.name} <-> {self.interface_b.name}",
            )

            self.created_cable = cable
            self.status = "executed"
            self.save()
            return cable

        except Exception as e:
            self.status = "failed"
            self.validation_errors = [str(e)]
            self.save()
            raise
