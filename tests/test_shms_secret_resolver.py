"""Tests for SHMS shared secret resolution."""

from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import MagicMock

from shms_secret_resolver import SecretResolver, VaultSecretRef


class FakeResponse:
    """Minimal response object for resolver tests."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        """Return the configured JSON payload."""
        return self._payload

    def raise_for_status(self):
        """Raise on HTTP error status."""
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class SecretResolverTest(TestCase):
    """Validate resolver precedence and Vault auth behavior."""

    def setUp(self):
        """Preserve process environment for each test."""
        self._old_env = os.environ.copy()
        os.environ.clear()

    def tearDown(self):
        """Restore process environment after each test."""
        os.environ.clear()
        os.environ.update(self._old_env)

    def test_resolve_value_prefers_env_without_vault_request(self):
        """Environment values should win and avoid Vault I/O."""
        os.environ["PRIMARY_SECRET"] = "from-env"
        http_session = MagicMock()

        resolver = SecretResolver.from_env(http_session=http_session)
        value = resolver.resolve_value(
            env_names=("PRIMARY_SECRET",),
            vault=VaultSecretRef(mount="kv", path="app/secret", keys=("password",)),
        )

        self.assertEqual(value, "from-env")
        http_session.get.assert_not_called()
        http_session.post.assert_not_called()

    def test_resolve_value_reads_kv_v2_with_legacy_token_fallback(self):
        """Token auth should read Vault KV v2 using SHMS env aliases."""
        os.environ.update(
            {
                "HASHICORP_VAULT_URL": "https://vault.example.invalid",
                "HASHICORP_VAULT_TOKEN": "legacy-token",
                "HASHICORP_VAULT_NAMESPACE": "admin/shms",
                "REQUESTS_CA_BUNDLE": "/certs/ca.crt",
                "VAULT_AUTH_METHOD": "token",
            }
        )
        http_session = MagicMock()
        http_session.get.return_value = FakeResponse({"data": {"data": {"password": "from-vault"}}})

        resolver = SecretResolver.from_env(http_session=http_session)
        value = resolver.resolve_value(
            env_names=("MISSING_SECRET",),
            vault=VaultSecretRef(mount="kv", path="app/secret", keys=("password",)),
        )

        self.assertEqual(value, "from-vault")
        http_session.get.assert_called_once()
        _, kwargs = http_session.get.call_args
        self.assertEqual(kwargs["headers"]["X-Vault-Token"], "legacy-token")
        self.assertEqual(kwargs["headers"]["X-Vault-Namespace"], "admin/shms")
        self.assertEqual(kwargs["verify"], "/certs/ca.crt")

    def test_resolve_value_logs_in_with_cert_auth_before_reading_secret(self):
        """Cert auth should login with client certificate material and use the returned token."""
        os.environ.update(
            {
                "VAULT_ADDR": "https://vault.example.invalid",
                "VAULT_AUTH_METHOD": "cert",
                "VAULT_CERT_ROLE": "shms-nbcot",
                "VAULT_CLIENT_CERT": "/certs/client.crt",
                "VAULT_CLIENT_KEY": "/certs/client.key",
                "VAULT_CACERT": "/certs/ca.crt",
            }
        )
        http_session = MagicMock()
        http_session.post.return_value = FakeResponse({"auth": {"client_token": "short-token", "lease_duration": 900}})
        http_session.get.return_value = FakeResponse({"data": {"data": {"password": "from-vault"}}})

        resolver = SecretResolver.from_env(http_session=http_session)
        value = resolver.resolve_value(
            env_names=("MISSING_SECRET",),
            vault=VaultSecretRef(mount="kv", path="app/secret", keys=("password",)),
        )

        self.assertEqual(value, "from-vault")
        http_session.post.assert_called_once_with(
            "https://vault.example.invalid/v1/auth/cert/login",
            json={"name": "shms-nbcot"},
            cert=("/certs/client.crt", "/certs/client.key"),
            verify="/certs/ca.crt",
            timeout=15,
        )
        _, kwargs = http_session.get.call_args
        self.assertEqual(kwargs["headers"]["X-Vault-Token"], "short-token")

    def test_resolve_mapping_supports_vault_key_aliases(self):
        """Mappings should fill missing values from Vault aliases without overwriting env values."""
        os.environ.update(
            {
                "NBCOT_CLIENT_ID": "env-client-id",
                "VAULT_ADDR": "https://vault.example.invalid",
                "VAULT_TOKEN": "legacy-token",
            }
        )
        http_session = MagicMock()
        http_session.get.return_value = FakeResponse(
            {"data": {"data": {"API_TOKEN_CLIENT_ID": "vault-client-id", "API_TOKEN_CLIENT_PASS": "vault-secret"}}}
        )

        resolver = SecretResolver.from_env(http_session=http_session)
        values = resolver.resolve_mapping(
            env_names_by_field={
                "client_id": ("NBCOT_CLIENT_ID", "CISCO_MODERN_API_CLIENT_ID", "API_TOKEN_CLIENT_ID"),
                "client_secret": ("NBCOT_CLIENT_SECRET", "CISCO_MODERN_API_SECRET", "API_TOKEN_CLIENT_PASS"),
            },
            vault=VaultSecretRef(mount="kv", path="CISCO_API_CONSOLE"),
            vault_keys_by_field={
                "client_id": ("CISCO_MODERN_API_CLIENT_ID", "API_TOKEN_CLIENT_ID"),
                "client_secret": ("CISCO_MODERN_API_SECRET", "API_TOKEN_CLIENT_PASS"),
            },
        )

        self.assertEqual(values, {"client_id": "env-client-id", "client_secret": "vault-secret"})

    def test_populate_env_from_vault_fills_only_missing_values(self):
        """Startup population should preserve explicit env values and fill missing ones from Vault."""
        os.environ.update(
            {
                "EXISTING_SECRET": "from-env",
                "VAULT_ADDR": "https://vault.example.invalid",
                "VAULT_TOKEN": "legacy-token",
            }
        )
        http_session = MagicMock()
        http_session.get.return_value = FakeResponse(
            {"data": {"data": {"EXISTING_SECRET": "from-vault", "MISSING_ALIAS": "vault-missing"}}}
        )

        resolver = SecretResolver.from_env(http_session=http_session)
        populated = resolver.populate_env_from_vault(
            env_names=("EXISTING_SECRET", "MISSING_SECRET"),
            vault=VaultSecretRef(mount="kv", path="nautobot/shms/app"),
            keys_by_env={"MISSING_SECRET": ("MISSING_ALIAS", "MISSING_SECRET")},
        )

        self.assertEqual(populated, ["MISSING_SECRET"])
        self.assertEqual(os.environ["EXISTING_SECRET"], "from-env")
        self.assertEqual(os.environ["MISSING_SECRET"], "vault-missing")
