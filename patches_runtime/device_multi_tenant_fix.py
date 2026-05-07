"""
Monkey patch for nautobot-device-onboarding to fix Device lookup in diffsync models.

This patch addresses the problem where Device queries by name return multiple devices
in multi-tenant environments where device names are duplicated across different tenants/locations.

Issue: The diffsync models use device name as an identifier, which is not unique in
multi-tenant Nautobot instances. When querying Device.objects.get(name="switch1"),
it raises MultipleObjectsReturned if two devices named "switch1" exist in different
tenants/locations.

Fix: This patch wraps both:
1. get_from_db() method of Device diffsync models
2. get_from_orm_cache() method of the adapter for Device lookups

Both catch MultipleObjectsReturned exceptions and filter to devices in the
job's devices_to_load scope to return the correct device.

The patch modifies the SyncNetworkDataDevice diffsync model class and the adapter.
"""

import logging
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist

LOGGER = logging.getLogger(__name__)

# Store reference to original methods
_original_device_get_from_db = None
_original_adapter_get_from_orm_cache = None


def _patched_device_get_from_db(self):
    """
    Patched get_from_db instance method for SyncNetworkDataDevice.

    Handles multi-tenant collisions when looking up devices by name.

    This wraps the original get_from_db() and catches MultipleObjectsReturned
    exceptions, using the job's devices_to_load scope to disambiguate.

    Args:
        self: The diffsync model instance
    """
    from diffsync.exceptions import ObjectCrudException

    # First try the original method
    try:
        if _original_device_get_from_db is None:
            raise ObjectCrudException("Original get_from_db method is not initialized")
        return _original_device_get_from_db(self)
    except ObjectCrudException as exc:
        # Check if the underlying error is MultipleObjectsReturned
        if "MultipleObjectsReturned" not in str(exc) and not isinstance(
            exc.__cause__, MultipleObjectsReturned
        ):
            # Not a multi-tenant collision, re-raise
            raise

        # Multi-tenant collision detected - use job's device scope to resolve
        LOGGER.warning(
            "MultipleObjectsReturned for Device(name='%s') - attempting to resolve with job's device scope",
            self.name,
        )

        job = self.adapter.job
        if not hasattr(job, "devices_to_load") or job.devices_to_load is None:
            LOGGER.error(
                "Job does not have devices_to_load attribute - cannot resolve collision for device '%s'",
                self.name,
            )
            raise ObjectCrudException(
                f"Cannot resolve Device collision for name='{self.name}' - no device scope"
            ) from exc

        # Filter to devices in the job's scope
        try:
            device = job.devices_to_load.get(name=self.name)
            LOGGER.info(
                "✓ Resolved Device collision: name='%s', pk='%s', location='%s', tenant='%s'",
                device.name,
                device.pk,
                device.location.name if device.location else None,
                device.tenant.name if device.tenant else None,
            )
            return device

        except ObjectDoesNotExist:
            LOGGER.error(
                "Device '%s' not found in job's devices_to_load scope", self.name
            )
            raise ObjectCrudException(
                f"Device with name='{self.name}' not found in job's device scope"
            ) from exc

        except MultipleObjectsReturned:
            # This should never happen since devices_to_load should be pre-filtered
            LOGGER.warning(
                "Multiple devices named '%s' even in job's scope - using first",
                self.name,
            )
            device = job.devices_to_load.filter(name=self.name).first()
            if device:
                LOGGER.info(
                    "Using first match: pk='%s', location='%s', tenant='%s'",
                    device.pk,
                    device.location.name if device.location else None,
                    device.tenant.name if device.tenant else None,
                )
                return device
            else:
                raise ObjectCrudException(
                    f"Device with name='{self.name}' query returned None"
                ) from exc


def _patched_adapter_get_from_orm_cache(self, parameters, model_class):
    """
    Patched get_from_orm_cache method for the adapter.

    Handles multi-tenant collisions when looking up objects by non-unique identifiers:
    - Device lookups by name
    - Interface lookups by device name + interface name
    - IPAddress lookups by host

    Args:
        self: The adapter instance
        parameters: Dict with model lookup parameters
        model_class: The Django model class being looked up
    """
    from nautobot.dcim.models import Device, Interface
    from nautobot.ipam.models import IPAddress

    # Try the original method first
    try:
        if _original_adapter_get_from_orm_cache is None:
            raise ObjectDoesNotExist(
                "Original adapter cache lookup method is not initialized"
            )
        return _original_adapter_get_from_orm_cache(self, parameters, model_class)
    except MultipleObjectsReturned:
        # Multi-tenant collision detected - handle based on model type

        # Get the job's device scope
        job = self.job
        if not hasattr(job, "devices_to_load") or job.devices_to_load is None:
            LOGGER.error(
                "Job does not have devices_to_load - cannot resolve %s collision",
                model_class.__name__,
            )
            raise

        # Handle Device lookups
        if model_class == Device:
            device_name = parameters.get("name")
            if not device_name:
                raise

            LOGGER.warning(
                "MultipleObjectsReturned for Device(name='%s') - resolving with job scope",
                device_name,
            )

            device = job.devices_to_load.filter(name=device_name).first()
            if device:
                LOGGER.info("✓ Resolved Device: %s (pk=%s)", device.name, device.pk)
                return device
            raise

        # Handle Interface lookups
        elif model_class == Interface:
            device_name = parameters.get("device__name")
            interface_name = parameters.get("name")

            if not device_name or not interface_name:
                raise

            LOGGER.warning(
                "MultipleObjectsReturned for Interface(device='%s', name='%s') - resolving with job scope",
                device_name,
                interface_name,
            )

            # Get the device from job scope first
            device = job.devices_to_load.filter(name=device_name).first()
            if not device:
                raise

            # Now get the interface for that specific device
            interface = Interface.objects.filter(
                device=device, name=interface_name
            ).first()
            if interface:
                LOGGER.info(
                    "✓ Resolved Interface: %s on %s (pk=%s)",
                    interface.name,
                    device.name,
                    interface.pk,
                )
                return interface
            raise

        # Handle IPAddress lookups
        elif model_class == IPAddress:
            ip_host = parameters.get("host")

            if not ip_host:
                raise

            LOGGER.warning(
                "MultipleObjectsReturned for IPAddress(host='%s') - resolving with job scope",
                ip_host,
            )

            # Get IP addresses that are assigned to interfaces on devices in job scope
            # Use the IPAddressToInterface through model
            from nautobot.ipam.models import IPAddressToInterface

            device_pks = list(job.devices_to_load.values_list("pk", flat=True))

            # Find IP address assignments to interfaces on our devices
            ip_assignment = (
                IPAddressToInterface.objects.filter(
                    interface__device__pk__in=device_pks, ip_address__host=ip_host
                )
                .select_related("ip_address")
                .first()
            )

            if ip_assignment:
                LOGGER.info(
                    "✓ Resolved IPAddress: %s (pk=%s)",
                    ip_host,
                    ip_assignment.ip_address.pk,
                )
                return ip_assignment.ip_address

            # Fallback: try to get IP in the job's namespace (if specified)
            # This handles cases where IP might not be assigned yet
            namespace = getattr(job, "namespace", None)
            if namespace:
                ip_addr = IPAddress.objects.filter(
                    host=ip_host, parent__namespace=namespace
                ).first()
                if ip_addr:
                    LOGGER.info(
                        "✓ Resolved IPAddress (namespace fallback): %s in namespace %s (pk=%s)",
                        ip_host,
                        namespace.name,
                        ip_addr.pk,
                    )
                    return ip_addr

            # Final fallback: try to get any IP with that host
            # This is a last resort and may not be correct in multi-tenant environments
            LOGGER.warning(
                "No namespace specified or IP not found in namespace - using any IP with host %s",
                ip_host,
            )
            ip_addr = IPAddress.objects.filter(host=ip_host).first()
            if ip_addr:
                LOGGER.info(
                    "✓ Resolved IPAddress (any-namespace fallback): %s (pk=%s)",
                    ip_host,
                    ip_addr.pk,
                )
                return ip_addr

            raise

        # For other models, just re-raise
        else:
            raise


def apply_device_multi_tenant_patch():
    """
    Apply the multi-tenant collision patch to nautobot_device_onboarding.

    This patches:
    1. get_from_db() instance method of SyncNetworkDataDevice
    2. get_from_orm_cache() method of the NautobotAdapter
       - Handles Device, Interface, and IPAddress lookups

    Returns:
        bool: True if patch was applied successfully, False otherwise
    """
    global _original_device_get_from_db, _original_adapter_get_from_orm_cache

    try:
        from nautobot_device_onboarding.diffsync.models import sync_network_data_models
        from nautobot_device_onboarding.diffsync.adapters import (
            sync_network_data_adapters,
        )

        # Check if already patched
        if hasattr(
            sync_network_data_models.SyncNetworkDataDevice.get_from_db,
            "_device_multi_tenant_patched",
        ) or hasattr(
            sync_network_data_adapters.SyncNetworkDataNautobotAdapter.get_from_orm_cache,
            "_adapter_multi_tenant_patched",
        ):
            LOGGER.debug("Device multi-tenant patch already applied")
            return True

        # Patch 1: Device model get_from_db() method
        _original_device_get_from_db = (
            sync_network_data_models.SyncNetworkDataDevice.get_from_db
        )
        sync_network_data_models.SyncNetworkDataDevice.get_from_db = (
            _patched_device_get_from_db
        )
        setattr(_patched_device_get_from_db, "_device_multi_tenant_patched", True)

        # Patch 2: Adapter get_from_orm_cache() method
        _original_adapter_get_from_orm_cache = (
            sync_network_data_adapters.SyncNetworkDataNautobotAdapter.get_from_orm_cache
        )
        sync_network_data_adapters.SyncNetworkDataNautobotAdapter.get_from_orm_cache = (
            _patched_adapter_get_from_orm_cache
        )
        setattr(
            _patched_adapter_get_from_orm_cache, "_adapter_multi_tenant_patched", True
        )

        LOGGER.info(
            "✓ Successfully applied Device multi-tenant collision patch (model + adapter)"
        )
        return True

    except Exception as exc:
        LOGGER.error(
            "Failed to apply Device multi-tenant patch: %s", exc, exc_info=True
        )
        return False


def remove_device_multi_tenant_patch():
    """
    Remove the Device multi-tenant collision patch and restore original behavior.

    Returns:
        bool: True if patch was removed successfully, False otherwise
    """
    try:
        from nautobot_device_onboarding.diffsync.models import sync_network_data_models
        from nautobot_device_onboarding.diffsync.adapters import (
            sync_network_data_adapters,
        )

        if not hasattr(
            sync_network_data_models.SyncNetworkDataDevice.get_from_db,
            "_device_multi_tenant_patched",
        ) and not hasattr(
            sync_network_data_adapters.SyncNetworkDataNautobotAdapter.get_from_orm_cache,
            "_adapter_multi_tenant_patched",
        ):
            LOGGER.debug("Device multi-tenant patch not currently applied")
            return True

        # Restore original methods
        if _original_device_get_from_db:
            sync_network_data_models.SyncNetworkDataDevice.get_from_db = (
                _original_device_get_from_db
            )

        if _original_adapter_get_from_orm_cache:
            sync_network_data_adapters.SyncNetworkDataNautobotAdapter.get_from_orm_cache = _original_adapter_get_from_orm_cache

        LOGGER.info("Successfully removed Device multi-tenant patch (model + adapter)")
        return True

    except Exception as exc:
        LOGGER.error(
            "Failed to remove Device multi-tenant patch: %s", exc, exc_info=True
        )
        return False
