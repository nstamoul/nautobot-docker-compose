"""
Nautobot startup hook to apply VLAN filtering patch.

This file should be executed by Nautobot at startup by adding to nautobot_config.py:

    import sys
    sys.path.insert(0, '/opt/nautobot/git/shms_nautobot_jobs_repo/patches')
    from nautobot_startup_hook import apply_patches
    apply_patches()

Or by adding this to the container's startup script.
"""

import logging

LOGGER = logging.getLogger(__name__)


def _defer_patch_until_runtime(apply_func, patch_name):
    try:
        from celery.signals import worker_process_init
        from django.db.backends.signals import connection_created
        from django.core.signals import request_started
    except Exception as exc:
        LOGGER.warning(
            "Could not register deferred patch hook for %s: %s", patch_name, exc
        )
        return False

    uid_base = f"nautobot_patch_defer_{patch_name}"

    def _runner(*args, **kwargs):
        try:
            if apply_func():
                LOGGER.info("✓ %s patch applied from deferred runtime hook", patch_name)
        except Exception as exc:
            LOGGER.warning(
                "Deferred patch apply failed for %s: %s",
                patch_name,
                exc,
                exc_info=True,
            )

    request_started.connect(_runner, dispatch_uid=f"{uid_base}_request")
    worker_process_init.connect(_runner, weak=False)
    connection_created.connect(_runner, dispatch_uid=f"{uid_base}_db")
    LOGGER.info("Deferred %s patch until runtime signals", patch_name)
    return True


def apply_patches():
    """Apply all necessary patches at Nautobot startup."""
    success = True

    # Apply VLAN filtering patch
    try:
        from vlan_filtering_fix import apply_vlan_filtering_patch

        if apply_vlan_filtering_patch():
            print("✓✓✓ VLAN filtering patch applied at Nautobot startup ✓✓✓")
            LOGGER.info(
                "✓ VLAN filtering patch applied successfully at Nautobot startup"
            )
        else:
            print("✗✗✗ VLAN filtering patch FAILED to apply ✗✗✗")
            LOGGER.warning("✗ VLAN filtering patch failed to apply")
            success = False
    except Exception as exc:
        print(f"✗✗✗ Error applying VLAN filtering patch: {exc} ✗✗✗")
        LOGGER.error("Error applying VLAN filtering patch: %s", exc, exc_info=True)
        success = False

    # Apply Interface multi-tenant collision patch
    try:
        from dynamic_jobs_app_config_fix import apply_dynamic_jobs_app_config_fix

        if apply_dynamic_jobs_app_config_fix():
            print("✓✓✓ Dynamic jobs app-config fix applied at Nautobot startup ✓✓✓")
            LOGGER.info("✓ Dynamic jobs app-config fix applied successfully at Nautobot startup")
        else:
            print("✗✗✗ Dynamic jobs app-config fix FAILED to apply ✗✗✗")
            LOGGER.warning("✗ Dynamic jobs app-config fix failed to apply")
            success = False
    except Exception as exc:
        print(f"✗✗✗ Error applying dynamic jobs app-config fix: {exc} ✗✗✗")
        LOGGER.error("Error applying dynamic jobs app-config fix: %s", exc, exc_info=True)
        success = False

    try:
        from interface_multi_tenant_fix import apply_interface_multi_tenant_patch

        if apply_interface_multi_tenant_patch():
            print(
                "✓✓✓ Interface multi-tenant collision patch applied at Nautobot startup ✓✓✓"
            )
            LOGGER.info(
                "✓ Interface multi-tenant collision patch applied successfully at Nautobot startup"
            )
        else:
            if _defer_patch_until_runtime(
                apply_interface_multi_tenant_patch,
                "interface_multi_tenant",
            ):
                print(
                    "~~~ Interface multi-tenant collision patch deferred until runtime ~~~"
                )
            else:
                print("✗✗✗ Interface multi-tenant collision patch FAILED to apply ✗✗✗")
                LOGGER.warning(
                    "✗ Interface multi-tenant collision patch failed to apply"
                )
                success = False
    except Exception as exc:
        print(f"✗✗✗ Error applying Interface multi-tenant collision patch: {exc} ✗✗✗")
        LOGGER.error(
            "Error applying Interface multi-tenant collision patch: %s",
            exc,
            exc_info=True,
        )
        success = False

    try:
        from welcome_wizard_import_filename_uniqueness_fix import (
            apply_welcome_wizard_import_filename_uniqueness_patch,
        )

        if apply_welcome_wizard_import_filename_uniqueness_patch():
            print(
                "✓✓✓ Welcome Wizard filename uniqueness patch applied at Nautobot startup ✓✓✓"
            )
            LOGGER.info(
                "✓ Welcome Wizard filename uniqueness patch applied successfully at Nautobot startup"
            )
        else:
            if _defer_patch_until_runtime(
                apply_welcome_wizard_import_filename_uniqueness_patch,
                "welcome_wizard_filename_uniqueness",
            ):
                print(
                    "~~~ Welcome Wizard filename uniqueness patch deferred until runtime ~~~"
                )
            else:
                print(
                    "✗✗✗ Welcome Wizard filename uniqueness patch FAILED to apply ✗✗✗"
                )
                LOGGER.warning(
                    "✗ Welcome Wizard filename uniqueness patch failed to apply"
                )
                success = False
    except Exception as exc:
        print(f"✗✗✗ Error applying Welcome Wizard filename uniqueness patch: {exc} ✗✗✗")
        LOGGER.error(
            "Error applying Welcome Wizard filename uniqueness patch: %s",
            exc,
            exc_info=True,
        )
        success = False

    try:
        from vault_secret_provider_registry_fix import (
            apply_vault_secret_provider_registry_fix,
        )

        if apply_vault_secret_provider_registry_fix():
            print(
                "✓✓✓ Vault secret provider registry patch applied at Nautobot startup ✓✓✓"
            )
            LOGGER.info(
                "✓ Vault secret provider registry patch applied successfully at Nautobot startup"
            )
        else:
            if _defer_patch_until_runtime(
                apply_vault_secret_provider_registry_fix,
                "vault_secret_provider_registry",
            ):
                print(
                    "~~~ Vault secret provider registry patch deferred until runtime ~~~"
                )
            else:
                print(
                    "✗✗✗ Vault secret provider registry patch FAILED to apply ✗✗✗"
                )
                LOGGER.warning(
                    "✗ Vault secret provider registry patch failed to apply"
                )
                success = False
    except Exception as exc:
        print(f"✗✗✗ Error applying Vault secret provider registry patch: {exc} ✗✗✗")
        LOGGER.error(
            "Error applying Vault secret provider registry patch: %s",
            exc,
            exc_info=True,
        )
        success = False

    try:
        from ldap_superuser_staff_fix import apply_ldap_superuser_staff_fix

        if apply_ldap_superuser_staff_fix():
            print("✓✓✓ LDAP superuser staff patch applied at Nautobot startup ✓✓✓")
            LOGGER.info("✓ LDAP superuser staff patch applied successfully at Nautobot startup")
        else:
            if _defer_patch_until_runtime(
                apply_ldap_superuser_staff_fix,
                "ldap_superuser_staff",
            ):
                print("~~~ LDAP superuser staff patch deferred until runtime ~~~")
            else:
                print("✗✗✗ LDAP superuser staff patch FAILED to apply ✗✗✗")
                LOGGER.warning("✗ LDAP superuser staff patch failed to apply")
                success = False
    except Exception as exc:
        print(f"✗✗✗ Error applying LDAP superuser staff patch: {exc} ✗✗✗")
        LOGGER.error(
            "Error applying LDAP superuser staff patch: %s",
            exc,
            exc_info=True,
        )
        success = False

    try:
        from meraki_ssot_adapter_fix import apply_meraki_ssot_adapter_fix

        if apply_meraki_ssot_adapter_fix():
            print("✓✓✓ Meraki SSoT adapter patch applied at Nautobot startup ✓✓✓")
            LOGGER.info("✓ Meraki SSoT adapter patch applied successfully at Nautobot startup")
        else:
            if _defer_patch_until_runtime(
                apply_meraki_ssot_adapter_fix,
                "meraki_ssot_adapter",
            ):
                print("~~~ Meraki SSoT adapter patch deferred until runtime ~~~")
            else:
                print("✗✗✗ Meraki SSoT adapter patch FAILED to apply ✗✗✗")
                LOGGER.warning("✗ Meraki SSoT adapter patch failed to apply")
                success = False
    except Exception as exc:
        print(f"✗✗✗ Error applying Meraki SSoT adapter patch: {exc} ✗✗✗")
        LOGGER.error(
            "Error applying Meraki SSoT adapter patch: %s",
            exc,
            exc_info=True,
        )
        success = False

    return success


if __name__ == "__main__":
    # Allow running directly for testing
    apply_patches()
