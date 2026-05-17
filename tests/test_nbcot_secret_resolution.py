"""Focused tests for NBCOT shared secret resolver integration."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from nbcot.cisco.client import CiscoSettings


class NBCOTSecretResolutionTest(TestCase):
    """Validate NBCOT uses the shared resolver for env and Vault fallback."""

    def setUp(self):
        """Preserve process environment for each test."""
        self._old_env = os.environ.copy()
        os.environ.clear()

    def tearDown(self):
        """Restore process environment after each test."""
        os.environ.clear()
        os.environ.update(self._old_env)

    def test_load_uses_shared_resolver_when_plugin_config_missing_credentials(self):
        """NBCOT should delegate env-to-Vault fallback to SecretResolver."""
        resolver = MagicMock()
        resolver.resolve_cisco_api_credentials.return_value = {
            "client_id": "resolver-client-id",
            "client_secret": "resolver-client-secret",
        }
        plugin_settings = SimpleNamespace(
            PLUGINS_CONFIG={
                "nbcot": {
                    "graphql_endpoint": "https://example.invalid/graphql",
                }
            }
        )

        with patch("nbcot.cisco.client.settings", plugin_settings), patch(
            "nbcot.cisco.client.SecretResolver.from_env", return_value=resolver
        ) as from_env:
            settings_obj = CiscoSettings.load()

        from_env.assert_called_once()
        resolver.resolve_cisco_api_credentials.assert_called_once()
        self.assertEqual(settings_obj.client_id, "resolver-client-id")
        self.assertEqual(settings_obj.client_secret, "resolver-client-secret")

    def test_load_keeps_plugin_config_credentials_before_resolver(self):
        """Plugin-configured credentials should keep highest precedence."""
        plugin_settings = SimpleNamespace(
            PLUGINS_CONFIG={
                "nbcot": {
                    "client_id": "plugin-client-id",
                    "client_secret": "plugin-client-secret",
                    "graphql_endpoint": "https://example.invalid/graphql",
                }
            }
        )

        with patch("nbcot.cisco.client.settings", plugin_settings), patch(
            "nbcot.cisco.client.SecretResolver.from_env"
        ) as from_env:
            settings_obj = CiscoSettings.load()

        from_env.assert_not_called()
        self.assertEqual(settings_obj.client_id, "plugin-client-id")
        self.assertEqual(settings_obj.client_secret, "plugin-client-secret")
