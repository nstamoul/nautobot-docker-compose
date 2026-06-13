"""Shared SHMS secret resolution helpers."""

from .resolver import (
    CISCO_API_CLIENT_ID_ENV_NAMES,
    CISCO_API_CLIENT_SECRET_ENV_NAMES,
    CISCO_API_VAULT_KEYS_BY_FIELD,
    SHMS_STARTUP_SECRET_ENV_NAMES,
    SHMS_STARTUP_SECRET_KEYS_BY_ENV,
    SecretResolver,
    VaultClientConfig,
    VaultSecretRef,
)

__all__ = [
    "CISCO_API_CLIENT_ID_ENV_NAMES",
    "CISCO_API_CLIENT_SECRET_ENV_NAMES",
    "CISCO_API_VAULT_KEYS_BY_FIELD",
    "SHMS_STARTUP_SECRET_ENV_NAMES",
    "SHMS_STARTUP_SECRET_KEYS_BY_ENV",
    "SecretResolver",
    "VaultClientConfig",
    "VaultSecretRef",
]
