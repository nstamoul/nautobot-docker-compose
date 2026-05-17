"""Runtime compatibility fixes for the Nautobot SSoT Meraki adapter.

The Nautobot 3.1 / nautobot-ssot 4.2.2 Meraki integration has two SHMS-impacting
issues:

* Tenant-scoped runs load every existing device for the tenant. Devices without a
  name can crash DiffSync target loading, and dict identifiers are safer across
  current DiffSync versions.
* Location Mapping is honored when network Locations are loaded, but device and
  prefix-location placement resolve the raw Meraki network name.
"""

import logging

LOGGER = logging.getLogger(__name__)

_original_resolve_location_name = None
_original_load_devices = None
_original_load_ports = None
_original_load_ipassignments = None


def _mapped_location_name(job, network_name, network_id=None):
    """Return the mapped Nautobot Location name for a Meraki network."""
    location_map = getattr(job, "location_map", None) or {}
    mapping = location_map.get(network_name)
    if mapping is None and network_id:
        mapping = location_map.get(network_id)
    if isinstance(mapping, dict) and mapping.get("name"):
        return mapping["name"]
    return network_name


def _patched_resolve_location_name(self, network_id):
    """Resolve device/prefix Location names using Meraki Location Mapping."""
    if getattr(self.job, "location", None):
        return self.job.location.name

    network_data = self.conn.network_map[network_id]
    network_name = network_data["name"]
    return _mapped_location_name(self.job, network_name, network_id=network_id)


def _patched_load_devices(self):
    """Load Nautobot target devices safely for tenant-scoped Meraki runs."""
    from diffsync.enum import DiffSyncModelFlags
    from diffsync.exceptions import ObjectNotFound
    from nautobot.dcim.models import Device

    if self.tenant:
        devices = Device.objects.filter(tenant=self.tenant)
    else:
        devices = Device.objects.filter(_custom_field_data__system_of_record="Meraki SSoT")

    for dev in devices:
        if not dev.name:
            LOGGER.debug(
                "Skipping unnamed Nautobot device %s during Meraki SSoT target load",
                dev.pk,
            )
            continue

        try:
            self.get(self.device, {"name": dev.name})
        except ObjectNotFound:
            self.device_map[dev.name] = dev.id
            self.port_map[dev.name] = {}
            new_dev = self.device(
                name=dev.name,
                controller_group=dev.controller_managed_device_group.name
                if dev.controller_managed_device_group
                else None,
                serial=dev.serial,
                status=dev.status.name,
                role=dev.role.name,
                model=dev.device_type.model,
                notes="",
                network=dev.location.name if dev.location else "",
                tenant=dev.tenant.name if dev.tenant else None,
                uuid=dev.id,
                version=dev.software_version.version if dev.software_version else None,
            )
            if dev.notes:
                note = dev.notes.last()
                new_dev.notes = note.note.rstrip()
            if self.tenant:
                new_dev.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            self.add(new_dev)


def _patched_load_ports(self):
    """Load Nautobot target ports safely for tenant-scoped Meraki runs."""
    from diffsync.enum import DiffSyncModelFlags
    from diffsync.exceptions import ObjectNotFound
    from nautobot.dcim.models import Interface

    if self.tenant:
        ports = Interface.objects.filter(device__tenant=self.tenant)
    else:
        ports = Interface.objects.filter(_custom_field_data__system_of_record="Meraki SSoT")

    for intf in ports:
        device_name = intf.device.name if intf.device else None
        if not device_name or not intf.name:
            LOGGER.debug(
                "Skipping interface %s during Meraki SSoT target load because its device or name is missing",
                intf.pk,
            )
            continue
        if device_name not in self.port_map:
            LOGGER.debug(
                "Skipping interface %s on %s because the device was not loaded into Meraki SSoT target state",
                intf.name,
                device_name,
            )
            continue

        try:
            self.get(self.port, {"name": intf.name, "device": device_name})
        except ObjectNotFound:
            self.port_map[device_name][intf.name] = intf.id
            new_port = self.port(
                name=intf.name,
                device=device_name,
                management=intf.mgmt_only,
                enabled=intf.enabled,
                port_type=intf.type,
                port_status=intf.status.name,
                tagging=bool(intf.mode != "access"),
                uuid=intf.id,
            )
            if self.tenant:
                new_port.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            self.add(new_port)
            dev = self.get(self.device, {"name": device_name})
            dev.add_child(new_port)


def _patched_load_ipassignments(self):
    """Load Nautobot target IP assignments safely for tenant-scoped Meraki runs."""
    from diffsync.enum import DiffSyncModelFlags
    from nautobot.ipam.models import IPAddressToInterface

    if self.tenant:
        mappings = IPAddressToInterface.objects.filter(ip_address__tenant=self.tenant)
    else:
        mappings = IPAddressToInterface.objects.filter(
            ip_address__custom_field_data__system_of_record="Meraki SSoT"
        )

    for ipassignment in mappings:
        interface = ipassignment.interface
        device_name = interface.device.name if interface and interface.device else None
        port_name = interface.name if interface else None
        if not device_name or not port_name:
            LOGGER.debug(
                "Skipping IP assignment %s during Meraki SSoT target load because device or interface name is missing",
                ipassignment.pk,
            )
            continue
        if device_name not in self.port_map or port_name not in self.port_map[device_name]:
            LOGGER.debug(
                "Skipping IP assignment %s for %s/%s because the port was not loaded into Meraki SSoT target state",
                ipassignment.pk,
                device_name,
                port_name,
            )
            continue

        if self.job.debug:
            self.job.logger.debug(
                f"Loading IPAssignment {ipassignment.ip_address.host} on {device_name} "
                f"port {port_name} in Namespace {ipassignment.ip_address.parent.namespace.name}"
            )
        new_map = self.ipassignment(
            address=str(ipassignment.ip_address.host),
            namespace=ipassignment.ip_address.parent.namespace.name,
            device=device_name,
            port=port_name,
            primary=len(ipassignment.ip_address.primary_ip4_for.all()) > 0
            or len(ipassignment.ip_address.primary_ip6_for.all()) > 0,
            uuid=ipassignment.id,
        )
        if self.tenant:
            new_map.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
        self.add(new_map)


def apply_meraki_ssot_adapter_fix():
    """Apply SHMS Meraki SSoT adapter compatibility patches."""
    global _original_resolve_location_name, _original_load_devices
    global _original_load_ports, _original_load_ipassignments

    try:
        from nautobot_ssot.integrations.meraki.diffsync.adapters import (
            meraki,
            nautobot,
        )

        if getattr(meraki.MerakiAdapter.resolve_location_name, "_shms_meraki_patched", False) and getattr(
            nautobot.NautobotAdapter.load_devices,
            "_shms_meraki_patched",
            False,
        ) and getattr(
            nautobot.NautobotAdapter.load_ports,
            "_shms_meraki_patched",
            False,
        ) and getattr(
            nautobot.NautobotAdapter.load_ipassignments,
            "_shms_meraki_patched",
            False,
        ):
            LOGGER.debug("Meraki SSoT adapter patch already applied")
            return True

        if not getattr(meraki.MerakiAdapter.resolve_location_name, "_shms_meraki_patched", False):
            _original_resolve_location_name = meraki.MerakiAdapter.resolve_location_name
            meraki.MerakiAdapter.resolve_location_name = _patched_resolve_location_name
            setattr(meraki.MerakiAdapter.resolve_location_name, "_shms_meraki_patched", True)

        if not getattr(nautobot.NautobotAdapter.load_devices, "_shms_meraki_patched", False):
            _original_load_devices = nautobot.NautobotAdapter.load_devices
            nautobot.NautobotAdapter.load_devices = _patched_load_devices
            setattr(nautobot.NautobotAdapter.load_devices, "_shms_meraki_patched", True)

        if not getattr(nautobot.NautobotAdapter.load_ports, "_shms_meraki_patched", False):
            _original_load_ports = nautobot.NautobotAdapter.load_ports
            nautobot.NautobotAdapter.load_ports = _patched_load_ports
            setattr(nautobot.NautobotAdapter.load_ports, "_shms_meraki_patched", True)

        if not getattr(nautobot.NautobotAdapter.load_ipassignments, "_shms_meraki_patched", False):
            _original_load_ipassignments = nautobot.NautobotAdapter.load_ipassignments
            nautobot.NautobotAdapter.load_ipassignments = _patched_load_ipassignments
            setattr(nautobot.NautobotAdapter.load_ipassignments, "_shms_meraki_patched", True)

        LOGGER.info("Applied Meraki SSoT adapter compatibility patch")
        return True
    except Exception as exc:
        LOGGER.error("Failed to apply Meraki SSoT adapter patch: %s", exc, exc_info=True)
        return False


def remove_meraki_ssot_adapter_fix():
    """Restore original Meraki SSoT adapter methods."""
    try:
        from nautobot_ssot.integrations.meraki.diffsync.adapters import (
            meraki,
            nautobot,
        )

        if _original_resolve_location_name:
            meraki.MerakiAdapter.resolve_location_name = _original_resolve_location_name
        if _original_load_devices:
            nautobot.NautobotAdapter.load_devices = _original_load_devices
        if _original_load_ports:
            nautobot.NautobotAdapter.load_ports = _original_load_ports
        if _original_load_ipassignments:
            nautobot.NautobotAdapter.load_ipassignments = _original_load_ipassignments
        return True
    except Exception as exc:
        LOGGER.error("Failed to remove Meraki SSoT adapter patch: %s", exc, exc_info=True)
        return False
