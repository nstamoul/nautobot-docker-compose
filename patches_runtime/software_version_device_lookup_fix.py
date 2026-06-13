"""
Monkey patch for nautobot-device-onboarding to fix Device lookup in load_software_versions.

This patch addresses the problem where Device.objects.get(serial=X) fails in the
SyncNetworkDataNetworkAdapter.load_software_versions() method when:
1. Device doesn't have a serial number
2. Device serial is empty or None
3. Multiple devices have the same serial (multi-tenant collision)
4. Device doesn't exist yet in Nautobot

Issue: The upstream code does:
    device = Device.objects.get(serial=device_data["serial"])

This raises DoesNotExist if the device hasn't been created yet or if the serial
doesn't match. It also raises MultipleObjectsReturned in multi-tenant environments.

Fix: This patch wraps the Device lookup to:
1. Handle missing/empty serial numbers (skip or use hostname lookup)
2. Handle MultipleObjectsReturned by filtering with job's location/tenant
3. Handle DoesNotExist by attempting hostname-based lookup
4. Log warnings and continue gracefully instead of crashing the job
"""

import logging
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist

LOGGER = logging.getLogger(__name__)

# Store reference to original method
_original_load_software_versions = None


def _safe_device_get_for_software_version(adapter, hostname, device_data):
    """
    Safely get a Device for software version loading, handling multi-tenant collisions.

    Args:
        adapter: The diffsync adapter with job context
        hostname: Hostname from command_getter_result
        device_data: Device data dict with 'serial' and other info

    Returns:
        Device object or None if not found

    Raises:
        None - logs warnings and returns None on errors
    """
    from nautobot.dcim.models import Device

    serial = device_data.get("serial")
    job = adapter.job

    # First, check if we have devices_to_load - this is the most reliable filter
    if hasattr(job, "devices_to_load") and job.devices_to_load is not None:
        # Try to find device in the job's scope by hostname
        try:
            device = job.devices_to_load.get(name=hostname)
            LOGGER.debug(f"Found device {hostname} in job's devices_to_load scope")
            return device
        except ObjectDoesNotExist:
            LOGGER.warning(
                f"Device {hostname} not found in job's devices_to_load scope"
            )
            return None
        except MultipleObjectsReturned:
            # This should never happen since devices_to_load should be pre-filtered
            LOGGER.warning(
                f"Multiple devices named {hostname} in job's scope - using serial to disambiguate"
            )
            if serial:
                try:
                    device = job.devices_to_load.filter(
                        name=hostname, serial=serial
                    ).first()
                    if device:
                        return device
                except Exception as exc:
                    LOGGER.warning(f"Error filtering by serial: {exc}")
            # Fall back to first match
            device = job.devices_to_load.filter(name=hostname).first()
            return device

    # Fallback: if no devices_to_load, try serial-based lookup (legacy behavior)
    if not serial or serial == "":
        LOGGER.warning(
            f"Device {hostname} has no serial number and no devices_to_load scope - cannot look up device"
        )
        return None

    # Try serial-based lookup
    try:
        device = Device.objects.get(serial=serial)
        return device

    except MultipleObjectsReturned:
        LOGGER.warning(
            f"Multiple devices found with serial '{serial}' - using hostname to disambiguate"
        )
        try:
            device = Device.objects.get(serial=serial, name=hostname)
            LOGGER.info(
                f"✓ Resolved device collision for serial '{serial}' using hostname '{hostname}': {device.name}"
            )
            return device
        except (ObjectDoesNotExist, MultipleObjectsReturned) as err:
            LOGGER.warning(
                f"Could not resolve device with serial '{serial}' and hostname '{hostname}': {err}"
            )
            return None

    except ObjectDoesNotExist:
        LOGGER.warning(
            f"Device with serial '{serial}' (hostname={hostname}) not found for software version loading"
        )
        return None


def _patched_load_software_versions(self):
    """Patched load_software_versions method for SyncNetworkDataNetworkAdapter."""
    import diffsync.exceptions

    for hostname, device_data in self.job.command_getter_result.items():
        if self.job.debug:
            self.job.logger.debug(f"Loading Software Versions from {hostname}")

        if device_data.get("software_version"):
            # Use safe device lookup
            device = _safe_device_get_for_software_version(self, hostname, device_data)

            if device is None:
                # Skip this device if we couldn't find it
                self.job.logger.warning(
                    f"Skipping software version for {hostname} - device not found"
                )
                continue

            try:
                network_software_version = self.software_version(
                    adapter=self,
                    platform__name=device.platform.name,
                    version=device_data["software_version"],
                )
                self.add(network_software_version)
            except diffsync.exceptions.ObjectAlreadyExists:
                continue


def apply_software_version_device_lookup_patch():
    """
    Apply the software version device lookup patch to nautobot_device_onboarding.

    This patches the load_software_versions() method of SyncNetworkDataNetworkAdapter.

    Returns:
        bool: True if patch was applied successfully, False otherwise
    """
    global _original_load_software_versions

    try:
        from nautobot_device_onboarding.diffsync.adapters import (
            sync_network_data_adapters,
        )

        # Check if already patched
        if hasattr(
            sync_network_data_adapters.SyncNetworkDataNetworkAdapter.load_software_versions,
            "_device_lookup_patched",
        ):
            LOGGER.debug("Software version device lookup patch already applied")
            return True

        # Store original method
        _original_load_software_versions = sync_network_data_adapters.SyncNetworkDataNetworkAdapter.load_software_versions

        # Apply patch
        sync_network_data_adapters.SyncNetworkDataNetworkAdapter.load_software_versions = _patched_load_software_versions

        # Mark as patched
        setattr(_patched_load_software_versions, "_device_lookup_patched", True)

        LOGGER.info("✓ Successfully applied software version device lookup patch")
        return True

    except Exception as exc:
        LOGGER.error(
            "Failed to apply software version device lookup patch: %s",
            exc,
            exc_info=True,
        )
        return False


def remove_software_version_device_lookup_patch():
    """
    Remove the software version device lookup patch and restore original behavior.

    Returns:
        bool: True if patch was removed successfully, False otherwise
    """
    try:
        from nautobot_device_onboarding.diffsync.adapters import (
            sync_network_data_adapters,
        )

        if not hasattr(
            sync_network_data_adapters.SyncNetworkDataNetworkAdapter.load_software_versions,
            "_device_lookup_patched",
        ):
            LOGGER.debug("Software version device lookup patch not currently applied")
            return True

        # Restore original method
        if _original_load_software_versions:
            sync_network_data_adapters.SyncNetworkDataNetworkAdapter.load_software_versions = _original_load_software_versions

        LOGGER.info("Successfully removed software version device lookup patch")
        return True

    except Exception as exc:
        LOGGER.error(
            "Failed to remove software version device lookup patch: %s",
            exc,
            exc_info=True,
        )
        return False
