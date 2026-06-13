"""
Monkey patch for nautobot-device-onboarding to fix Interface multi-tenant collision.

This patch addresses the problem where Interface.objects.get(device__name=X, name=Y)
returns multiple interfaces in multi-tenant environments where device names are duplicated
across different tenants/locations.

Issue: The diffsync models use device__name as an identifier, which is not unique in
multi-tenant Nautobot instances. When querying Interface.objects.get(device__name="switch1",
name="Gi0/1"), it raises MultipleObjectsReturned if two devices named "switch1" exist
in different tenants/locations, both with an interface "Gi0/1".

Fix: This patch wraps Interface.objects.get() calls in the diffsync update() methods to:
1. Catch MultipleObjectsReturned exceptions
2. Filter to interfaces whose devices match the job's location/tenant filters
3. Return the first matching interface from the filtered set

The patch modifies these diffsync model classes:
- SyncNetworkDataTaggedVlansToInterface (line 307)
- SyncNetworkDataUnTaggedVlanToInterface (line 408)
- SyncNetworkDataLagToInterface (line 496)
- SyncNetworkDataVrfToInterface (line 614)
"""

import logging
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.db.models import Q

LOGGER = logging.getLogger(__name__)

# Store references to original update methods
_ORIGINAL_METHODS = {}


def _safe_interface_get(adapter, device_name, interface_name):
    """
    Safely get an Interface, handling multi-tenant collisions.

    Args:
        adapter: The diffsync adapter with job context
        device_name: Name of the device
        interface_name: Name of the interface

    Returns:
        Interface object or raises ObjectDoesNotExist

    Raises:
        ObjectDoesNotExist: If no interface found
        MultipleObjectsReturned: If collision cannot be resolved
    """
    from nautobot.dcim.models import Device, Interface

    job = adapter.job

    if hasattr(job, "devices_to_load") and job.devices_to_load is not None:
        candidate_devices = Device.objects.filter(
            name=device_name, pk__in=job.devices_to_load.values("pk")
        )

        if candidate_devices.exists():
            device = candidate_devices.order_by("pk").first()
            try:
                return device.all_interfaces.get(name=interface_name)
            except MultipleObjectsReturned:
                narrowed = Interface.objects.filter(
                    Q(device=device, name=interface_name)
                    | Q(parent=device, name=interface_name)
                ).order_by("pk")
                if narrowed.exists():
                    return narrowed.first()
                raise ObjectDoesNotExist(
                    f"No Interface for in-scope device='{device_name}', name='{interface_name}'"
                )
            except ObjectDoesNotExist:
                raise

    try:
        # Try normal get
        return Interface.objects.get(device__name=device_name, name=interface_name)
    except MultipleObjectsReturned:
        LOGGER.warning(
            "MultipleObjectsReturned for Interface(device__name='%s', name='%s') - attempting to resolve with job's device scope",
            device_name,
            interface_name,
        )

        # Get the job's devices_to_load queryset - this contains the EXACT devices being synced
        if not hasattr(job, "devices_to_load") or job.devices_to_load is None:
            LOGGER.error(
                "Job does not have devices_to_load attribute - cannot resolve collision"
            )
            raise ObjectDoesNotExist(
                f"Cannot resolve Interface collision for device__name='{device_name}', name='{interface_name}' - no device scope"
            )

        # Filter to interfaces belonging ONLY to devices in the job's scope
        filters = {
            "device__in": job.devices_to_load,
            "device__name": device_name,
            "name": interface_name,
        }

        matching = Interface.objects.filter(**filters)
        count = matching.count()

        if count == 0:
            LOGGER.error(
                "No Interface found in job's device scope for device='%s', interface='%s'",
                device_name,
                interface_name,
            )
            raise ObjectDoesNotExist(
                f"No Interface with device__name='{device_name}', name='{interface_name}' found in job's device scope"
            )
        elif count == 1:
            interface = matching.first()
            LOGGER.info(
                "✓ Resolved Interface collision: device='%s', interface='%s', location='%s', tenant='%s'",
                device_name,
                interface_name,
                interface.device.location.name if interface.device.location else None,
                interface.device.tenant.name if interface.device.tenant else None,
            )
            return interface
        else:
            # Still multiple - this shouldn't happen if devices_to_load is correct, but take first
            interface = matching.first()
            LOGGER.warning(
                "Still %d interfaces in job scope after filtering - using first: device='%s', interface='%s', location='%s'",
                count,
                device_name,
                interface_name,
                interface.device.location.name if interface.device.location else None,
            )
            return interface


def _patched_tagged_vlans_update(self, attrs):
    """Patched update method for SyncNetworkDataTaggedVlansToInterface."""
    from diffsync.exceptions import ObjectNotUpdated
    from django.core.exceptions import ValidationError

    try:
        # Use safe get instead of direct Interface.objects.get()
        interface = _safe_interface_get(
            self.adapter,
            self.get_identifiers()["device__name"],
            self.get_identifiers()["name"],
        )
    except ObjectDoesNotExist as err:
        self.adapter.job.logger.error(
            f"Failed to update tagged vlans, an interface with identifiers: [{self.get_identifiers()}] was not found."
        )
        raise ObjectNotUpdated(err)

    if attrs.get("tagged_vlans"):
        interface.tagged_vlans.clear()
        for network_vlan in attrs["tagged_vlans"]:
            self._get_and_assign_tagged_vlan(
                self.adapter,
                network_vlan,
                interface,
                diff_method_type="update",
            )
        try:
            interface.validated_save()
        except ValidationError as err:
            self.adapter.job.logger.error(
                f"Failed to assign tagged vlans {attrs['tagged_vlans']} "
                f"to interface: [{interface}] on device: [{interface.parent}], {err}"
            )
            raise ObjectNotUpdated(err)

    if not attrs.get("tagged_vlans"):
        interface.tagged_vlans.clear()
        try:
            interface.validated_save()
        except ValidationError as err:
            self.adapter.job.logger.error(
                f"Failed to remove tagged vlans from interface: [{interface}] on device: [{interface.parent}], {err}"
            )
            raise ObjectNotUpdated(err)

    return super(type(self), self).update(attrs)


def _patched_untagged_vlan_update(self, attrs):
    """Patched update method for SyncNetworkDataUntaggedVlanToInterface."""
    from diffsync.exceptions import ObjectNotUpdated
    from django.core.exceptions import ValidationError

    try:
        interface = _safe_interface_get(
            self.adapter,
            self.get_identifiers()["device__name"],
            self.get_identifiers()["name"],
        )
    except ObjectDoesNotExist as err:
        self.adapter.job.logger.error(
            f"Failed to update untagged vlan, an interface with identifiers: [{self.get_identifiers()}] was not found."
        )
        raise ObjectNotUpdated(err)

    if attrs.get("untagged_vlan"):
        self._get_and_assign_untagged_vlan(
            self.adapter,
            attrs,
            interface,
            diff_method_type="update",
        )
        try:
            interface.validated_save()
        except ValidationError as err:
            self.adapter.job.logger.error(
                f"Failed to assign untagged vlan {attrs['untagged_vlan']} "
                f"to interface: [{interface}] on device: [{interface.parent}], {err}"
            )
            raise ObjectNotUpdated(err)

    if not attrs.get("untagged_vlan"):
        interface.untagged_vlan = None
        try:
            interface.validated_save()
        except ValidationError as err:
            self.adapter.job.logger.error(
                f"Failed to remove untagged vlan from {interface} on {interface.parent}, {err}"
            )
            raise ObjectNotUpdated(err)

    return super(type(self), self).update(attrs)


def _patched_lag_update(self, attrs):
    """Patched update method for SyncNetworkDataLagToInterface."""
    from diffsync.exceptions import ObjectNotUpdated
    from django.core.exceptions import ValidationError
    from nautobot.dcim.models import Interface

    try:
        interface = _safe_interface_get(
            self.adapter,
            self.get_identifiers()["device__name"],
            self.get_identifiers()["name"],
        )
    except ObjectDoesNotExist as err:
        self.adapter.job.logger.error(
            f"Failed to update lag, an interface with identifiers: [{self.get_identifiers()}] was not found."
        )
        raise ObjectNotUpdated(err)

    lag_name = attrs.get("lag__interface__name") or attrs.get("lag")

    if lag_name:
        lag_attrs = {"lag__interface__name": lag_name}
        self._get_and_assign_lag(
            self.adapter,
            lag_attrs,
            interface,
            diff_method_type="update",
        )
        try:
            interface.validated_save()
        except ValidationError as err:
            self.adapter.job.logger.error(
                f"Failed to assign lag: [{lag_name}] "
                f"to interface: [{interface}] on device: [{interface.parent}], {err}"
            )
            raise ObjectNotUpdated(err)

    if not lag_name:
        interface.lag = None
        try:
            interface.validated_save()
        except ValidationError as err:
            self.adapter.job.logger.error(
                f"Failed to remove lag from interface: [{interface}] on device: [{interface.parent}], {err}"
            )
            raise ObjectNotUpdated(err)

    return super(type(self), self).update(attrs)


def _patched_vrf_update(self, attrs):
    """Patched update method for SyncNetworkDataVrfToInterface."""
    from diffsync.exceptions import ObjectNotUpdated
    from django.core.exceptions import ValidationError

    try:
        interface = _safe_interface_get(
            self.adapter,
            self.get_identifiers()["device__name"],
            self.get_identifiers()["name"],
        )
    except ObjectDoesNotExist as err:
        self.adapter.job.logger.error(
            f"Failed to update vrf, an interface with identifiers: [{self.get_identifiers()}] was not found."
        )
        raise ObjectNotUpdated(err)

    if attrs.get("vrf"):
        # Assign a vrf to an interface
        self._get_and_assign_vrf(
            self.adapter, attrs, interface, diff_method_type="update"
        )
        try:
            interface.validated_save()
        except ValidationError as err:
            self.adapter.job.logger.error(
                f"Failed to assign vrf: [{attrs['vrf']}] "
                f"to interface: [{interface}] on device: [{interface.parent}], {err}"
            )
            raise ObjectNotUpdated(err)

    if not attrs.get("vrf"):
        interface.vrf = None
        try:
            interface.validated_save()
        except ValidationError as err:
            self.adapter.job.logger.error(
                f"Failed to remove vrf from interface: [{interface}] on device: [{interface.parent}], {err}"
            )
            raise ObjectNotUpdated(err)

    return super(type(self), self).update(attrs)


def apply_interface_multi_tenant_patch():
    """
    Apply the Interface multi-tenant collision patch to nautobot_device_onboarding.

    This patches the update() methods of the diffsync models that query interfaces.

    Returns:
        bool: True if patch was applied successfully, False otherwise
    """
    global _ORIGINAL_METHODS

    try:
        from nautobot_device_onboarding.diffsync.models import sync_network_data_models

        # Check if already patched
        if any(
            hasattr(method, "_multi_tenant_patched")
            for method in (
                sync_network_data_models.SyncNetworkDataTaggedVlansToInterface.update,
                sync_network_data_models.SyncNetworkDataUnTaggedVlanToInterface.update,
                sync_network_data_models.SyncNetworkDataLagToInterface.update,
                sync_network_data_models.SyncNetworkDataVrfToInterface.update,
            )
        ):
            LOGGER.debug("Interface multi-tenant patch already applied")
            return True

        # Store original methods
        _ORIGINAL_METHODS["tagged_vlans"] = (
            sync_network_data_models.SyncNetworkDataTaggedVlansToInterface.update
        )
        _ORIGINAL_METHODS["untagged_vlan"] = (
            sync_network_data_models.SyncNetworkDataUnTaggedVlanToInterface.update
        )
        _ORIGINAL_METHODS["lag"] = (
            sync_network_data_models.SyncNetworkDataLagToInterface.update
        )
        _ORIGINAL_METHODS["vrf"] = (
            sync_network_data_models.SyncNetworkDataVrfToInterface.update
        )

        # Apply patches
        sync_network_data_models.SyncNetworkDataTaggedVlansToInterface.update = (
            _patched_tagged_vlans_update
        )
        sync_network_data_models.SyncNetworkDataUnTaggedVlanToInterface.update = (
            _patched_untagged_vlan_update
        )
        sync_network_data_models.SyncNetworkDataLagToInterface.update = (
            _patched_lag_update
        )
        sync_network_data_models.SyncNetworkDataVrfToInterface.update = (
            _patched_vrf_update
        )

        # Mark as patched
        setattr(_patched_tagged_vlans_update, "_multi_tenant_patched", True)
        setattr(_patched_untagged_vlan_update, "_multi_tenant_patched", True)
        setattr(_patched_lag_update, "_multi_tenant_patched", True)
        setattr(_patched_vrf_update, "_multi_tenant_patched", True)

        LOGGER.info(
            "✓ Successfully applied Interface multi-tenant collision patch to diffsync models"
        )
        return True

    except Exception as exc:
        LOGGER.error(
            "Failed to apply Interface multi-tenant patch: %s", exc, exc_info=True
        )
        return False


def remove_interface_multi_tenant_patch():
    """
    Remove the Interface multi-tenant collision patch and restore original behavior.

    Returns:
        bool: True if patch was removed successfully, False otherwise
    """
    try:
        from nautobot_device_onboarding.diffsync.models import sync_network_data_models

        if all(
            not hasattr(method, "_multi_tenant_patched")
            for method in (
                sync_network_data_models.SyncNetworkDataTaggedVlansToInterface.update,
                sync_network_data_models.SyncNetworkDataUnTaggedVlanToInterface.update,
                sync_network_data_models.SyncNetworkDataLagToInterface.update,
                sync_network_data_models.SyncNetworkDataVrfToInterface.update,
            )
        ):
            LOGGER.debug("Interface multi-tenant patch not currently applied")
            return True

        # Restore original methods
        if _ORIGINAL_METHODS:
            sync_network_data_models.SyncNetworkDataTaggedVlansToInterface.update = (
                _ORIGINAL_METHODS["tagged_vlans"]
            )
            sync_network_data_models.SyncNetworkDataUnTaggedVlanToInterface.update = (
                _ORIGINAL_METHODS["untagged_vlan"]
            )
            sync_network_data_models.SyncNetworkDataLagToInterface.update = (
                _ORIGINAL_METHODS["lag"]
            )
            sync_network_data_models.SyncNetworkDataVrfToInterface.update = (
                _ORIGINAL_METHODS["vrf"]
            )

        LOGGER.info("Successfully removed Interface multi-tenant patch")
        return True

    except Exception as exc:
        LOGGER.error(
            "Failed to remove Interface multi-tenant patch: %s", exc, exc_info=True
        )
        return False
