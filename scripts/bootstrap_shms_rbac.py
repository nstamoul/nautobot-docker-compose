"""Bootstrap SHMS AD-backed composite RBAC groups and object permissions.

Run this inside Nautobot's Django context, for example:

    nautobot-server shell --command "exec(open('/opt/nautobot/scripts/bootstrap_shms_rbac.py').read())"
"""

import re

from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from nautobot.tenancy.models import Tenant
from nautobot.users.models import ObjectPermission


FLAG_GROUPS = [
    "NB-LOGIN",
    "NB-STAFF",
    "NB-SUPERUSERS",
]

TENANT_CONSTRAINED_MODELS = {
    "nonops": [
        ("dcim", "device", "tenant__name"),
        ("dcim", "inventoryitem", "device__tenant__name"),
        ("nautobot_device_lifecycle_mgmt", "devicehardwarenoticeresult", "device__tenant__name"),
        ("nautobot_device_lifecycle_mgmt", "devicesoftwarevalidationresult", "device__tenant__name"),
        ("nautobot_device_lifecycle_mgmt", "inventoryitemsoftwarevalidationresult", "inventory_item__device__tenant__name"),
    ],
    "ops": [
        ("dcim", "device", "tenant__name"),
        ("dcim", "interface", "device__tenant__name"),
        ("dcim", "cable", "tenant__name"),
        ("dcim", "inventoryitem", "device__tenant__name"),
        ("dcim", "controller", "tenant__name"),
        ("dcim", "controllermanageddevicegroup", "controller__tenant__name"),
        ("ipam", "ipaddress", "tenant__name"),
        ("ipam", "prefix", "tenant__name"),
        ("ipam", "vlan", "tenant__name"),
        ("ipam", "vrf", "tenant__name"),
        ("ipam", "service", "ip_addresses__tenant__name"),
        ("circuits", "circuit", "tenant__name"),
        ("circuits", "circuittermination", "circuit__tenant__name"),
        ("virtualization", "virtualmachine", "tenant__name"),
        ("virtualization", "vminterface", "virtual_machine__tenant__name"),
    ],
}

ACTIONS_BY_ACCESS = {
    "USERS": ["view"],
    "ADMINS": ["view", "add", "change"],
}

DESCRIPTION_BY_DOMAIN = {
    "ops": "Operational tenant-scoped access",
    "nonops": "Non-operational tenant-scoped access",
}


def tenant_key(name):
    """Create a deterministic AD/Nautobot-safe tenant key."""
    normalized = name.upper().strip()
    normalized = re.sub(r"[^A-Z0-9]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "UNKNOWN"


def resolve_content_types(model_specs):
    """Resolve existing content types, logging missing models without aborting."""
    resolved = []
    for app_label, model, tenant_path in model_specs:
        try:
            ct = ContentType.objects.get(app_label=app_label, model=model)
        except ContentType.DoesNotExist:
            print(f"WARNING missing content type: {app_label}.{model}")
            continue
        resolved.append((ct, tenant_path, app_label, model))
    return resolved


@transaction.atomic
def ensure_flag_groups():
    for group_name in FLAG_GROUPS:
        group, created = Group.objects.get_or_create(name=group_name)
        print(("Created" if created else "Existing"), "flag group", group.name)


@transaction.atomic
def ensure_entitlement_groups_and_permissions():
    for tenant in Tenant.objects.order_by("name"):
        key = tenant_key(tenant.name)
        for domain, model_specs in TENANT_CONSTRAINED_MODELS.items():
            resolved_specs = resolve_content_types(model_specs)
            if not resolved_specs:
                print(f"WARNING no content types resolved for domain {domain}, tenant {tenant.name}")
                continue

            for access_level, actions in ACTIONS_BY_ACCESS.items():
                group_name = f"NB-{key}-{domain.upper()}-{access_level}"
                group, created = Group.objects.get_or_create(name=group_name)
                print(("Created" if created else "Existing"), "entitlement group", group.name)

                # Clean up legacy composite permissions created by the old bootstrap logic.
                legacy_perm_name = f"{tenant.name} {domain.upper()} {access_level}"
                legacy_qs = ObjectPermission.objects.filter(name=legacy_perm_name)
                if legacy_qs.exists():
                    count = legacy_qs.count()
                    legacy_qs.delete()
                    print("Deleted", count, "legacy composite permission(s)", legacy_perm_name)

                for ct, tenant_path, app_label, model in resolved_specs:
                    perm_name = f"{tenant.name} {domain.upper()} {access_level} {app_label}.{model}"
                    permission, created = ObjectPermission.objects.update_or_create(
                        name=perm_name,
                        defaults={
                            "description": (
                                f"{DESCRIPTION_BY_DOMAIN[domain]} for tenant {tenant.name} "
                                f"({access_level.lower()}) on {app_label}.{model}."
                            ),
                            "enabled": True,
                            "actions": actions,
                            "constraints": {tenant_path: tenant.name},
                        },
                    )
                    permission.object_types.set([ct])
                    permission.groups.set([group])
                    print(("Created" if created else "Updated"), "object permission", permission.name)


ensure_flag_groups()
ensure_entitlement_groups_and_permissions()
