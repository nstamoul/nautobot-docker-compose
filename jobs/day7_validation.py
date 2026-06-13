"""Local SHMS data-quality jobs replacing orphaned wyze day7 records."""

from nautobot.apps.jobs import BooleanVar, Job, ObjectVar, register_jobs
from nautobot.dcim.models import Device, Location


def _resolve_locations(location, include_descendants):
    """Return a queryset containing the selected location and optional descendants."""
    if not include_descendants:
        return Location.objects.filter(pk=location.pk)

    for method_name in ("descendants", "get_descendants"):
        method = getattr(location, method_name, None)
        if not callable(method):
            continue

        try:
            descendants = method(include_self=True)
        except TypeError:
            descendants = method()

        if hasattr(descendants, "values_list"):
            location_ids = list(descendants.values_list("pk", flat=True))
        else:
            location_ids = [item.pk for item in descendants]

        if location.pk not in location_ids:
            location_ids.insert(0, location.pk)
        return Location.objects.filter(pk__in=location_ids)

    return Location.objects.filter(pk=location.pk)


class _BaseValidationJob(Job):
    """Common scaffolding for location-scoped validation jobs."""

    location = ObjectVar(
        model=Location,
        required=True,
        query_params={"content_type": "dcim.device"},
        description="Validate devices assigned to this location.",
    )
    include_descendants = BooleanVar(
        default=True,
        description="Also validate devices in child locations.",
    )

    class Meta:
        has_sensitive_variables = False
        grouping = "Data Quality Jobs Collection"
        soft_time_limit = 300
        time_limit = 600

    validation_label = ""

    def get_target_devices(self, location, include_descendants):
        """Build the device queryset for the selected location scope."""
        locations = _resolve_locations(location, include_descendants)
        return Device.objects.filter(location__in=locations).distinct().order_by("name")

    def is_invalid(self, device):
        """Return True when a device fails the validation."""
        raise NotImplementedError

    def failure_message(self, device):
        """Describe the validation failure for an individual device."""
        raise NotImplementedError

    def run(self, location, include_descendants, *args, **kwargs):
        """Execute the validation and fail the job when violations exist."""
        devices = list(self.get_target_devices(location, include_descendants))
        self.logger.info(
            "Validating %s across %s device(s) in location %s%s.",
            self.validation_label,
            len(devices),
            location.name,
            " and descendants" if include_descendants else "",
        )

        failures = []
        for device in devices:
            if not self.is_invalid(device):
                continue
            failures.append(device)
            self.logger.error(self.failure_message(device))

        if failures:
            raise RuntimeError(
                f"{len(failures)} of {len(devices)} device(s) failed validation for {self.validation_label}."
            )

        self.logger.info(
            "Validation passed for %s. Checked %s device(s).",
            self.validation_label,
            len(devices),
        )


class VerifyPlatform(_BaseValidationJob):
    """Check that devices have a platform assigned."""

    validation_label = "platform assignment"

    class Meta(_BaseValidationJob.Meta):
        name = "Check Platform is defined"
        description = "Check Platform is defined for devices in selected location"
        grouping = "Data Quality Jobs Collection"
        has_sensitive_variables = False
        soft_time_limit = 300
        time_limit = 600

    def is_invalid(self, device):
        return device.platform is None

    def failure_message(self, device):
        return f"Device {device.name} has no platform assigned."


class VerifySerialNumber(_BaseValidationJob):
    """Check that devices have serial numbers populated."""

    validation_label = "serial number presence"

    class Meta(_BaseValidationJob.Meta):
        name = "Check Serial Numbers"
        description = "Check Serial Numbers are defined for devices in selected location"
        grouping = "Data Quality Jobs Collection"
        has_sensitive_variables = False
        soft_time_limit = 300
        time_limit = 600

    def is_invalid(self, device):
        return not (device.serial or "").strip()

    def failure_message(self, device):
        return f"Device {device.name} has no serial number defined."


class VerifyPrimaryIP(_BaseValidationJob):
    """Check that devices have a primary IP assigned."""

    validation_label = "primary IP assignment"

    class Meta(_BaseValidationJob.Meta):
        name = "Verify Device has at selected location has Primary IP configured"
        description = "Verify Device has at selected location has Primary IP configured"
        grouping = "Data Quality Jobs Collection"
        has_sensitive_variables = False
        soft_time_limit = 300
        time_limit = 600

    def is_invalid(self, device):
        return device.primary_ip4 is None and device.primary_ip6 is None

    def failure_message(self, device):
        return f"Device {device.name} has no primary IPv4 or IPv6 address assigned."


jobs = [VerifyPlatform, VerifySerialNumber, VerifyPrimaryIP]
register_jobs(*jobs)
