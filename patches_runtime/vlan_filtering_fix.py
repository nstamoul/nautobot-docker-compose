"""
Monkey patch for nautobot-app-device-onboarding to fix VLAN filtering issue.

This patch addresses the problem where the upstream get_vlan_data() function creates
VLANs for ALL VLANs in trunk allowed ranges, even if those VLANs don't actually
exist in the switch's VLAN database.

Issue: When a trunk interface has 'switchport trunk allowed vlan 1-4094', the
upstream code creates all 4094 VLANs in Nautobot, even if only a handful actually
exist on the device.

Fix: This patch modifies get_vlan_data() to filter the expanded VLAN IDs against
the actual VLAN database (vlan_mapping) before creating VLAN entries.

See: docs/vlan_sync_issue_analysis.md for detailed analysis
"""

import logging

LOGGER = logging.getLogger(__name__)

# Store reference to original function (will be set when patch is applied)
_ORIGINAL_GET_VLAN_DATA = None
_jinja_filters = None


def _patched_get_vlan_data(item, vlan_mapping, tag_type):
    """
    Fixed version of get_vlan_data that filters trunk VLANs against actual VLAN database.

    This function delegates to the original implementation for all cases except
    tagged VLANs, where it adds filtering logic to only include VLANs that actually
    exist in the switch's VLAN database.

    Args:
        item: Interface data from command parser
        vlan_mapping: Dictionary mapping VLAN IDs to names (from 'show vlan')
        tag_type: Either "tagged" or "untagged"

    Returns:
        List of VLAN dictionaries with 'id' and 'name' keys
    """
    global _jinja_filters

    # Lazy imports inside function to avoid circular import
    from itertools import chain
    from netutils.vlan import vlanconfig_to_list

    LOGGER.info("🔧 PATCHED get_vlan_data CALLED with tag_type=%s", tag_type)

    # For non-tagged cases, use original implementation
    if tag_type != "tagged":
        return _ORIGINAL_GET_VLAN_DATA(item, vlan_mapping, tag_type)

    # Handle tagged VLANs with filtering
    current_item = item

    # Safety checks from original implementation
    if isinstance(vlan_mapping, list):
        LOGGER.debug(
            "Unable to format, vlan dict not returned: vlan_mapping %s",
            vlan_mapping
        )
        return []

    if isinstance(item, list) and len(item) == 1:
        current_item = item[0]

    # Get interface mode (from original implementation)
    try:
        int_mode = _jinja_filters.interface_mode_logic(item)
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Failed to determine interface mode: %s", exc)
        return []

    # Handle special cases
    if int_mode == "tagged-all":
        return []

    if int_mode == "access":
        return []

    # Process trunk VLANs with filtering
    if not current_item or not int_mode:
        return []

    try:
        # Get trunk VLAN configuration
        trunking_vlans_raw = current_item.get("trunking_vlans")
        if not trunking_vlans_raw:
            return []

        # Ensure we have a list
        if not isinstance(trunking_vlans_raw, list):
            trunk_vlans = [trunking_vlans_raw]
        else:
            trunk_vlans = trunking_vlans_raw

        # Expand all VLAN ranges
        expanded_vids = list(
            chain.from_iterable(
                [vlanconfig_to_list(vlan_stanza) for vlan_stanza in trunk_vlans]
            )
        )

        # CRITICAL FIX: Filter expanded VLANs against actual VLAN database
        # Only include VLANs that exist in vlan_mapping (i.e., were found in 'show vlan')
        filtered_vlans = [
            {
                "id": str(vid),
                "name": vlan_mapping[str(vid)]
            }
            for vid in expanded_vids
            if str(vid) in vlan_mapping  # <-- This is the fix!
        ]

        filtered_count = len(filtered_vlans)
        total_count = len(expanded_vids)
        LOGGER.info(
            "🔧 VLAN FILTERING: %d VLANs exist in VLAN database out of %d allowed on trunk",
            filtered_count,
            total_count
        )

        return filtered_vlans

    except Exception as exc:  # pragma: no cover
        LOGGER.error(
            "Error processing tagged VLANs for item %s: %s",
            current_item,
            exc,
            exc_info=True
        )
        return []


def apply_vlan_filtering_patch():
    """
    Apply the VLAN filtering patch to nautobot_device_onboarding.jinja_filters module.

    This function should be called early in the job initialization, before any
    network data is synced.

    Returns:
        bool: True if patch was applied successfully, False otherwise
    """
    global _ORIGINAL_GET_VLAN_DATA, _jinja_filters

    try:
        # Import jinja_filters HERE to avoid circular import at module load time
        from nautobot_device_onboarding import jinja_filters
        _jinja_filters = jinja_filters

        # Check if already patched
        if hasattr(jinja_filters.get_vlan_data, '_vlan_filtering_patched'):
            LOGGER.debug("VLAN filtering patch already applied")
            return True

        # Store original function
        _ORIGINAL_GET_VLAN_DATA = jinja_filters.get_vlan_data

        # Apply the patch
        jinja_filters.get_vlan_data = _patched_get_vlan_data

        # Mark as patched to avoid double-patching
        _patched_get_vlan_data._vlan_filtering_patched = True
        _patched_get_vlan_data._original_function = _ORIGINAL_GET_VLAN_DATA

        LOGGER.info("Successfully applied VLAN filtering patch to jinja_filters.get_vlan_data")
        return True

    except Exception as exc:  # pragma: no cover
        LOGGER.error(
            "Failed to apply VLAN filtering patch: %s",
            exc,
            exc_info=True
        )
        return False


def remove_vlan_filtering_patch():
    """
    Remove the VLAN filtering patch and restore original behavior.

    This is primarily useful for testing or if the upstream library fixes the issue.

    Returns:
        bool: True if patch was removed successfully, False otherwise
    """
    try:
        from nautobot_device_onboarding import jinja_filters

        if not hasattr(jinja_filters.get_vlan_data, '_vlan_filtering_patched'):
            LOGGER.debug("VLAN filtering patch not currently applied")
            return True

        # Restore original function
        if _ORIGINAL_GET_VLAN_DATA:
            jinja_filters.get_vlan_data = _ORIGINAL_GET_VLAN_DATA

        LOGGER.info("Successfully removed VLAN filtering patch")
        return True

    except Exception as exc:  # pragma: no cover
        LOGGER.error(
            "Failed to remove VLAN filtering patch: %s",
            exc,
            exc_info=True
        )
        return False
