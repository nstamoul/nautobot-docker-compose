"""Interface creation and normalization helpers used after materialization.

The module-template rendering and type inference are intentionally aligned with
the existing ``Populate Interfaces from Module Templates`` and
``Normalize Device Interface Types`` jobs, but are exposed as regular service
functions so online materialization can finish devices immediately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InterfaceFinalizationResult:
    """Summary of interface work performed for one or more devices."""

    created_interfaces: list[str] = field(default_factory=list)
    updated_interfaces: list[str] = field(default_factory=list)
    deleted_interfaces: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def replace_first_number(value: str, replacement: str) -> str:
    """Replace the first numeric run in an interface template name."""
    if not value or not replacement:
        return value
    return re.sub(r"(\d+)", str(replacement), value, count=1)


def cleanup_interface_name(value: str) -> str:
    """Normalize interface names by removing duplicate separators and spaces."""
    value = (value or "").strip()
    value = re.sub(r"/{2,}", "/", value)
    value = re.sub(r"\s+", "", value)
    return value


def forced_interface_type_from_name(interface_name: str) -> Optional[str]:
    """Return a forced Nautobot interface type for virtual/special names."""
    name_lower = (interface_name or "").lower()
    if not name_lower:
        return None

    if "." in interface_name or (":" in interface_name and not name_lower.startswith("vlan")):
        return "virtual"

    if (
        name_lower.startswith("virtual-access")
        or name_lower.startswith("virtual-template")
        or name_lower.startswith("loopback")
        or name_lower.startswith("vlan")
        or name_lower.startswith("tunnel")
        or name_lower.startswith("nve")
        or name_lower.startswith("bvi")
        or name_lower.startswith("nvi")
        or name_lower.startswith("null")
        or name_lower.startswith("dialer")
    ):
        return "virtual"

    if name_lower.startswith("cellular") or name_lower.startswith("wwan") or "lte" in name_lower:
        return "lte"

    if name_lower.startswith("embedded-service-engine") or name_lower.startswith("service-engine"):
        return "other"

    return None


def infer_interface_type_from_name(interface_name: str) -> str:
    """Infer a Nautobot interface type from common network interface names."""
    if not interface_name:
        return "other"

    name_lower = interface_name.lower()
    forced_type = forced_interface_type_from_name(interface_name)
    if forced_type:
        return forced_type

    if any(pattern in name_lower for pattern in ["mgmt", "management", "me0", "fxp0", "em0"]):
        return "1000base-t"
    if name_lower.startswith("hundredgig") or name_lower.startswith("hu"):
        return "100gbase-x-qsfp28"
    if name_lower.startswith("fortygig") or name_lower.startswith("fo"):
        return "40gbase-x-qsfpp"
    if name_lower.startswith("fastethernet") or name_lower.startswith("fa"):
        return "100base-tx"
    if name_lower.startswith("twentyfivegig") or name_lower.startswith("tf"):
        return "25gbase-x-sfp28"
    if name_lower.startswith(("tengig", "tenge", "xge")) or "10ge" in name_lower:
        return "10gbase-x-sfpp"
    if name_lower.startswith("te") and not name_lower.startswith("tunnel") and "fast" not in name_lower:
        return "10gbase-x-sfpp"
    if (
        "lag" in name_lower
        or "bond" in name_lower
        or name_lower.startswith("port-channel")
        or re.match(r"^po\d+", name_lower)
        or re.match(r"^ae\d+", name_lower)
    ):
        return "lag"
    if (
        name_lower.startswith("gigabitethernet")
        or name_lower.startswith("gi")
        or name_lower.startswith("ge")
        or name_lower.startswith("eth")
        or "vmnic" in name_lower
    ):
        return "1000base-t"
    if name_lower.startswith("e") and len(name_lower) >= 2 and (name_lower[1].isdigit() or name_lower[1] == "m"):
        return "1000base-t"

    return "other"


def default_interface_status(preferred_status=None):
    """Return a valid interface status, preferring the supplied status if valid."""
    from nautobot.dcim.models import Interface
    from nautobot.extras.models import Status

    statuses = Status.objects.get_for_model(Interface)
    if preferred_status and statuses.filter(pk=getattr(preferred_status, "pk", preferred_status)).exists():
        return preferred_status
    return statuses.filter(name__iexact="Active").first() or statuses.first()


def render_module_interface_name(template, module, *, member_position: str | None = None) -> str:
    """Render a module interface template for a stack member/module bay.

    Stack templates in this environment commonly use names like
    ``TwentyFiveGigE1/{module}/1`` where the first numeric run is the stack
    member and ``{module}`` is the network-module slot, normally ``1``.
    """
    raw_name = template.name or template.label or ""
    module_slot = getattr(module, "name", "") or "1"
    rendered = raw_name.replace("{module}", str(module_slot)).replace("<module>", str(module_slot))
    rendered = rendered.replace("{{module}}", str(module_slot))
    if member_position:
        rendered = replace_first_number(rendered, str(member_position))
    return cleanup_interface_name(rendered)


def ensure_device_type_interfaces(device, device_type=None, *, member_position=None, status=None, result=None):
    """Create or update interfaces from a device type's interface templates."""
    from nautobot.dcim.models import Interface

    result = result or InterfaceFinalizationResult()
    device_type = device_type or getattr(device, "device_type", None)
    if not device_type:
        return result

    interface_status = default_interface_status(status or getattr(device, "status", None))
    for template in device_type.interface_templates.all():
        name = cleanup_interface_name(replace_first_number(template.name, str(member_position))) if member_position else template.name
        if not name:
            continue

        interface, created = Interface.objects.get_or_create(
            device=device,
            name=name,
            defaults={
                "label": template.label or "",
                "type": template.type,
                "mgmt_only": template.mgmt_only,
                "description": template.description,
                "status": interface_status,
            },
        )
        changed = False
        for attr, value in (
            ("type", template.type),
            ("mgmt_only", template.mgmt_only),
            ("description", template.description),
        ):
            if value is not None and getattr(interface, attr) != value:
                setattr(interface, attr, value)
                changed = True
        if template.label and interface.label != template.label:
            interface.label = template.label
            changed = True
        if interface_status and interface.status_id != interface_status.pk:
            interface.status = interface_status
            changed = True
        if changed:
            interface.validated_save()
            result.updated_interfaces.append(f"{device.name}:{name}")
        if created:
            result.created_interfaces.append(f"{device.name}:{name}")
    return result


def populate_module_interfaces_for_device(device, *, status=None, result=None, prune_stale: bool = False):
    """Create or update interfaces for all installed modules on a device."""
    from nautobot.dcim.models import Interface, Module

    result = result or InterfaceFinalizationResult()
    interface_status = default_interface_status(status or getattr(device, "status", None))
    modules = Module.objects.filter(parent_module_bay__parent_device=device).select_related(
        "module_type", "parent_module_bay"
    ).prefetch_related("module_type__interface_templates")

    for module in modules:
        bay = getattr(module, "parent_module_bay", None)
        member_position = getattr(bay, "position", "") or "".join(re.findall(r"\d+", getattr(bay, "name", "") or ""))
        desired_names = set()
        for template in module.module_type.interface_templates.all():
            name = render_module_interface_name(template, module, member_position=str(member_position or "") or None)
            if not name:
                continue
            desired_names.add(name)

            interface = Interface.objects.filter(module=module, name=name).first()
            if not interface:
                interface = Interface.objects.filter(device=device, name=name).first()

            if interface:
                changed = False
                if interface.module_id != module.pk:
                    interface.module = module
                    changed = True
                if interface.device_id:
                    interface.device = None
                    changed = True
                for attr, value in (
                    ("type", template.type),
                    ("mgmt_only", template.mgmt_only),
                    ("description", template.description),
                ):
                    if value is not None and getattr(interface, attr) != value:
                        setattr(interface, attr, value)
                        changed = True
                if template.label and interface.label != template.label:
                    interface.label = template.label
                    changed = True
                if interface_status and interface.status_id != interface_status.pk:
                    interface.status = interface_status
                    changed = True
                if changed:
                    interface.validated_save()
                    result.updated_interfaces.append(f"{device.name}:{name}")
                continue

            interface = Interface(
                module=module,
                name=name,
                label=template.label or "",
                type=template.type,
                mgmt_only=template.mgmt_only,
                description=template.description,
                status=interface_status,
            )
            interface.validated_save()
            result.created_interfaces.append(f"{device.name}:{name}")

        if prune_stale and desired_names:
            stale_interfaces = Interface.objects.filter(module=module).exclude(name__in=desired_names)
            for stale_interface in stale_interfaces:
                if stale_interface.cable_id:
                    result.errors.append(
                        f"Skipped deleting cabled stale module interface {device.name}:{stale_interface.name}"
                    )
                    continue
                deleted_name = stale_interface.name
                stale_interface.delete()
                result.deleted_interfaces.append(f"{device.name}:{deleted_name}")

    return result


def set_device_interface_status(device, status, *, result=None):
    """Set all concrete device and installed-module interfaces to the requested status."""
    from nautobot.dcim.models import Interface

    result = result or InterfaceFinalizationResult()
    if not status:
        return result

    querysets = [
        Interface.objects.filter(device=device).exclude(status=status),
        Interface.objects.filter(module__parent_module_bay__parent_device=device).exclude(status=status),
    ]
    for queryset in querysets:
        for interface in queryset:
            interface.status = status
            interface.validated_save()
            result.updated_interfaces.append(f"{device.name}:{interface.name}")
    return result


def normalize_device_interface_types(device, *, result=None):
    """Normalize concrete device interface types from templates/name patterns."""
    from nautobot.dcim.models import InterfaceTemplate

    result = result or InterfaceFinalizationResult()
    for interface in device.interfaces.all().select_related("device", "device__device_type"):
        new_type = forced_interface_type_from_name(interface.name)
        if not new_type and device.device_type_id:
            template = InterfaceTemplate.objects.filter(device_type=device.device_type, name=interface.name).first()
            if template and template.type:
                new_type = template.type.lower()
        if not new_type:
            new_type = infer_interface_type_from_name(interface.name)

        if new_type and interface.type != new_type:
            interface.type = new_type
            interface.validated_save()
            result.updated_interfaces.append(f"{device.name}:{interface.name}")

    return result


def finalize_device_interfaces(device, *, status=None, result=None):
    """Run all post-materialization interface creation and normalization steps."""
    result = result or InterfaceFinalizationResult()
    ensure_device_type_interfaces(device, status=status, result=result)
    populate_module_interfaces_for_device(device, status=status, result=result)
    normalize_device_interface_types(device, result=result)
    set_device_interface_status(device, status, result=result)
    return result
