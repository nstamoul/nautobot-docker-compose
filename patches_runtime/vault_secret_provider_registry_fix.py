"""Ensure Vault secret providers are registered in Nautobot's runtime registry."""

import logging

LOGGER = logging.getLogger(__name__)


def apply_vault_secret_provider_registry_fix():
    """
    Register providers published by nautobot_secrets_providers.

    Returns:
        bool: True once the HashiCorp Vault provider is present in the registry.
            False indicates Django apps are not ready yet and the caller should defer.
    """
    try:
        from django.apps import apps

        if not apps.ready:
            return False

        from nautobot.extras.registry import registry
        from nautobot.extras.secrets import register_secrets_provider
        import nautobot_secrets_providers.secrets as plugin_secrets

        for provider in plugin_secrets.secrets_providers:
            register_secrets_provider(provider)

        return "hashicorp-vault" in registry["secrets_providers"]
    except Exception as exc:
        LOGGER.warning(
            "Vault secret provider registry patch failed: %s",
            exc,
            exc_info=True,
        )
        return False
