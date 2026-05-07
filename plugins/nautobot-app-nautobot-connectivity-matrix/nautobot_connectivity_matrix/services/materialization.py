"""Materialization helpers for unresolved planned devices."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MaterializationResult:
    """Result summary for explicit missing-device creation."""

    created_devices: list[str] = field(default_factory=list)
    reused_devices: list[str] = field(default_factory=list)
    created_interfaces: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def collect_unresolved_device_names(batch) -> list[str]:
    """Return sorted unresolved names referenced by rows in a batch."""
    names = set()
    for plan in batch.connection_plans.all():
        if not plan.device_a and plan.device_a_name:
            names.add(plan.device_a_name.strip())
        if not plan.device_b and plan.device_b_name:
            names.add(plan.device_b_name.strip())
    return sorted(name for name in names if name)


def missing_batch_defaults(batch) -> list[str]:
    """Return required defaults missing from a batch before materialization."""
    required = ("location", "default_device_role")
    return [field_name for field_name in required if not getattr(batch, field_name, None)]


def materialize_missing_devices(batch) -> MaterializationResult:
    """Create unresolved devices and named interfaces using batch defaults."""
    from nautobot.dcim.models import Device
    from nautobot.extras.models import Status

    from .interface_finalization import finalize_device_interfaces

    result = MaterializationResult()
    missing = missing_batch_defaults(batch)
    if missing:
        result.errors.append(f"Missing batch defaults: {', '.join(missing)}")
        return result

    device_type = batch.default_device_type or _get_or_create_generic_device_type()
    device_status = batch.default_device_status or Status.objects.filter(name__iexact="Planned").first()
    if not device_status:
        result.errors.append("Missing batch default device status and no 'Planned' status exists.")
        return result

    for name in collect_unresolved_device_names(batch):
        device, created = Device.objects.get_or_create(
            name=name,
            defaults={
                "device_type": device_type,
                "role": batch.default_device_role,
                "platform": batch.default_platform,
                "status": device_status,
                "tenant": batch.tenant,
                "location": batch.location,
            },
        )
        if created:
            result.created_devices.append(name)
        else:
            result.reused_devices.append(name)

        finalization = finalize_device_interfaces(device, status=device_status)
        result.created_interfaces.extend(finalization.created_interfaces)
        result.errors.extend(finalization.errors)

        for plan in batch.connection_plans.filter(device_a__isnull=True, device_a_name=name):
            plan.device_a = device
            interface = _ensure_interface(device, plan.interface_a_name, result, status=device_status)
            if interface:
                plan.interface_a = interface
                plan.interface_a_name = ""
            plan.device_a_name = ""
            plan.save()
        for plan in batch.connection_plans.filter(device_b__isnull=True, device_b_name=name):
            plan.device_b = device
            interface = _ensure_interface(device, plan.interface_b_name, result, status=device_status)
            if interface:
                plan.interface_b = interface
                plan.interface_b_name = ""
            plan.device_b_name = ""
            plan.save()

    return result


def _get_or_create_generic_device_type():
    """Return a generic device type for free-text planned devices."""
    from nautobot.dcim.models import DeviceType, Manufacturer

    manufacturer, _ = Manufacturer.objects.get_or_create(name="Generic")
    device_type, _ = DeviceType.objects.get_or_create(
        manufacturer=manufacturer,
        model="Generic Planned Device",
    )
    return device_type


def _ensure_interface(device, interface_name: str, result: MaterializationResult, *, status=None):
    """Create or reuse a named interface with a best-effort concrete type."""
    if not interface_name:
        return None

    from nautobot.dcim.models import Interface
    from .interface_finalization import infer_interface_type_from_name, normalize_device_interface_types, default_interface_status

    interface_status = default_interface_status(status or getattr(device, "status", None))
    interface, created = Interface.objects.get_or_create(
        device=device,
        name=interface_name,
        defaults={"type": infer_interface_type_from_name(interface_name), "status": interface_status},
    )
    if created:
        result.created_interfaces.append(f"{device.name}:{interface_name}")
    else:
        normalize_device_interface_types(device)
    return interface
