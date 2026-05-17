"""Environment and Vault-backed secret resolution."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Mapping, MutableMapping, Sequence

import requests

LOGGER = logging.getLogger(__name__)

SHMS_STARTUP_SECRET_ENV_NAMES = (
    "NAUTOBOT_AUTH_LDAP_BIND_PASSWORD",
    "NAUTOBOT_CREATE_SUPERUSER",
    "NAUTOBOT_DB_PASSWORD",
    "NAUTOBOT_MINIO_ACCESS_KEY",
    "NAUTOBOT_MINIO_SECRET_KEY",
    "NAUTOBOT_NAPALM_PASSWORD",
    "NAUTOBOT_NAPALM_USERNAME",
    "NAUTOBOT_REDIS_PASSWORD",
    "NAUTOBOT_SECRET_KEY",
    "NAUTOBOT_SUPERUSER_API_TOKEN",
    "NAUTOBOT_SUPERUSER_EMAIL",
    "NAUTOBOT_SUPERUSER_NAME",
    "NAUTOBOT_SUPERUSER_PASSWORD",
    "POSTGRES_PASSWORD",
    "PGPASSWORD",
    "CISCO_MODERN_API_CLIENT_ID",
    "CISCO_MODERN_API_SECRET",
    "VPN_CONTROL_API_KEY",
)

SHMS_STARTUP_SECRET_KEYS_BY_ENV = {
    "CISCO_MODERN_API_CLIENT_ID": ("CISCO_MODERN_API_CLIENT_ID", "API_TOKEN_CLIENT_ID"),
    "CISCO_MODERN_API_SECRET": ("CISCO_MODERN_API_SECRET", "API_TOKEN_CLIENT_PASS"),
}

CISCO_API_CLIENT_ID_ENV_NAMES = (
    "CISCO_MODERN_API_CLIENT_ID",
    "NBCOT_CLIENT_ID",
    "API_TOKEN_CLIENT_ID",
)
CISCO_API_CLIENT_SECRET_ENV_NAMES = (
    "CISCO_MODERN_API_SECRET",
    "NBCOT_CLIENT_SECRET",
    "API_TOKEN_CLIENT_PASS",
)
CISCO_API_VAULT_KEYS_BY_FIELD = {
    "client_id": ("CISCO_MODERN_API_CLIENT_ID", "API_TOKEN_CLIENT_ID"),
    "client_secret": ("CISCO_MODERN_API_SECRET", "API_TOKEN_CLIENT_PASS"),
}


def _first_nonempty(env: Mapping[str, str], *names: str) -> str:
    """Return the first non-empty value from the provided environment names."""
    for name in names:
        value = env.get(name)
        if value:
            return value
    return ""


@dataclass(frozen=True)
class VaultClientConfig:
    """Vault client settings derived from process environment."""

    url: str = ""
    auth_method: str = "token"
    token: str = ""
    namespace: str = ""
    ca_cert: str = ""
    client_cert: str = ""
    client_key: str = ""
    cert_role: str = ""
    cert_auth_mount: str = "cert"
    timeout: int = 15

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "VaultClientConfig":
        """Build Vault configuration from SHMS and Vault CLI environment aliases."""
        env = env if env is not None else os.environ
        return cls(
            url=_first_nonempty(env, "VAULT_ADDR", "HASHICORP_VAULT_URL"),
            auth_method=(env.get("VAULT_AUTH_METHOD") or "token").strip().lower(),
            token=_first_nonempty(env, "VAULT_TOKEN", "HASHICORP_VAULT_TOKEN"),
            namespace=_first_nonempty(env, "VAULT_NAMESPACE", "HASHICORP_VAULT_NAMESPACE"),
            ca_cert=_first_nonempty(env, "VAULT_CACERT", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"),
            client_cert=_first_nonempty(env, "VAULT_CLIENT_CERT", "HASHICORP_VAULT_CLIENT_CERT"),
            client_key=_first_nonempty(env, "VAULT_CLIENT_KEY", "HASHICORP_VAULT_CLIENT_KEY"),
            cert_role=_first_nonempty(env, "VAULT_CERT_ROLE", "HASHICORP_VAULT_CERT_ROLE"),
            cert_auth_mount=(env.get("VAULT_CERT_AUTH_MOUNT") or "cert").strip().strip("/") or "cert",
            timeout=int(env.get("VAULT_TIMEOUT", "15") or "15"),
        )

    @property
    def verify(self) -> str | bool:
        """Return the requests TLS verification setting."""
        return self.ca_cert or True


@dataclass(frozen=True)
class VaultSecretRef:
    """Reference to a Vault KV secret."""

    mount: str
    path: str
    keys: Sequence[str] = field(default_factory=tuple)
    kv_version: str = "v2"

    @property
    def normalized_mount(self) -> str:
        """Return mount without surrounding slashes."""
        return self.mount.strip("/")

    @property
    def normalized_path(self) -> str:
        """Return path without surrounding slashes."""
        return self.path.strip("/")


class SecretResolver:
    """Resolve secrets from env first, then Vault when configured."""

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        vault_config: VaultClientConfig | None = None,
        http_session: requests.Session | None = None,
        logger: logging.Logger | None = None,
    ):
        """Initialize resolver state."""
        self.env = env if env is not None else os.environ
        self.vault_config = vault_config or VaultClientConfig.from_env(self.env)
        self.http_session = http_session or requests.Session()
        self.logger = logger or LOGGER

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str] | None = None,
        http_session: requests.Session | None = None,
        logger: logging.Logger | None = None,
    ) -> "SecretResolver":
        """Create a resolver from process environment."""
        env = env if env is not None else os.environ
        return cls(
            env=env,
            vault_config=VaultClientConfig.from_env(env),
            http_session=http_session,
            logger=logger,
        )

    def resolve_value(
        self,
        *,
        env_names: Sequence[str] = (),
        vault: VaultSecretRef | None = None,
        keys: Sequence[str] = (),
    ) -> str:
        """Resolve one secret value from env or Vault."""
        env_value = _first_nonempty(self.env, *env_names)
        if env_value:
            self._log_source("env", env_names=env_names)
            return env_value

        if vault is None:
            self._log_source("unresolved", env_names=env_names)
            return ""

        secret_data = self._read_vault_secret(vault)
        for key in tuple(keys) or tuple(vault.keys):
            value = secret_data.get(key)
            if value:
                self._log_source(self._vault_source(), vault=vault, key=key)
                return str(value)

        self._log_source("unresolved", vault=vault)
        return ""

    def resolve_mapping(
        self,
        *,
        env_names_by_field: Mapping[str, Sequence[str]],
        vault: VaultSecretRef | None = None,
        vault_keys_by_field: Mapping[str, Sequence[str]] | None = None,
    ) -> dict[str, str]:
        """Resolve multiple fields while preserving env precedence per field."""
        values: dict[str, str] = {}
        unresolved_fields: list[str] = []
        for field_name, env_names in env_names_by_field.items():
            env_value = _first_nonempty(self.env, *env_names)
            if env_value:
                self._log_source("env", env_names=env_names, field=field_name)
                values[field_name] = env_value
            else:
                values[field_name] = ""
                unresolved_fields.append(field_name)

        if not unresolved_fields or vault is None:
            return values

        secret_data = self._read_vault_secret(vault)
        key_map = vault_keys_by_field or {}
        for field_name in unresolved_fields:
            for key in key_map.get(field_name, (field_name,)):
                value = secret_data.get(key)
                if value:
                    values[field_name] = str(value)
                    self._log_source(self._vault_source(), vault=vault, key=key, field=field_name)
                    break
            if not values[field_name]:
                self._log_source("unresolved", vault=vault, field=field_name)
        return values

    def resolve_cisco_api_credentials(
        self,
        *,
        vault_mount: str | None = None,
        vault_path: str | None = None,
        kv_version: str | None = None,
    ) -> dict[str, str]:
        """Resolve Cisco API OAuth credentials from env aliases, then Vault aliases."""
        mount = (vault_mount or self.env.get("CISCO_API_VAULT_MOUNT") or "kv").strip("/")
        path = (vault_path or self.env.get("CISCO_API_VAULT_PATH") or "CISCO_API_CONSOLE").strip("/")
        version = kv_version or self.env.get("CISCO_API_VAULT_KV_VERSION") or "v2"
        return self.resolve_mapping(
            env_names_by_field={
                "client_id": CISCO_API_CLIENT_ID_ENV_NAMES,
                "client_secret": CISCO_API_CLIENT_SECRET_ENV_NAMES,
            },
            vault=VaultSecretRef(mount=mount, path=path, kv_version=version),
            vault_keys_by_field=CISCO_API_VAULT_KEYS_BY_FIELD,
        )

    def populate_shms_startup_env(
        self,
        *,
        vault: VaultSecretRef,
        overwrite: bool = False,
    ) -> list[str]:
        """Populate the SHMS Nautobot startup secret env contract from Vault."""
        return self.populate_env_from_vault(
            env_names=SHMS_STARTUP_SECRET_ENV_NAMES,
            vault=vault,
            keys_by_env=SHMS_STARTUP_SECRET_KEYS_BY_ENV,
            overwrite=overwrite,
        )

    def populate_env_from_vault(
        self,
        *,
        env_names: Sequence[str],
        vault: VaultSecretRef,
        keys_by_env: Mapping[str, Sequence[str]] | None = None,
        overwrite: bool = False,
    ) -> list[str]:
        """Populate missing process environment values from one Vault secret.

        Returns the environment variable names that were populated. Values are never logged.
        """
        if not isinstance(self.env, MutableMapping):
            self.logger.info("Cannot populate immutable environment mapping from Vault.")
            return []

        missing_env_names = [name for name in env_names if overwrite or not self.env.get(name)]
        if not missing_env_names:
            return []

        secret_data = self._read_vault_secret(vault)
        populated: list[str] = []
        key_map = keys_by_env or {}
        for env_name in missing_env_names:
            candidate_keys = tuple(key_map.get(env_name, ())) + (env_name,)
            for key in candidate_keys:
                value = secret_data.get(key)
                if value:
                    self.env[env_name] = str(value)
                    populated.append(env_name)
                    self._log_source(self._vault_source(), vault=vault, key=key, field=env_name)
                    break
            if env_name not in populated:
                self._log_source("unresolved", vault=vault, field=env_name)
        return populated

    def _read_vault_secret(self, vault: VaultSecretRef) -> dict[str, object]:
        """Read a Vault KV secret payload."""
        config = self.vault_config
        if not config.url:
            return {}

        token = self._vault_token()
        if not token:
            return {}

        headers = {"X-Vault-Token": token}
        if config.namespace:
            headers["X-Vault-Namespace"] = config.namespace

        response = self.http_session.get(
            self._secret_url(vault),
            headers=headers,
            verify=config.verify,
            timeout=config.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if vault.kv_version == "v2":
            data = payload.get("data", {}).get("data", {})
        else:
            data = payload.get("data", {})
        return data if isinstance(data, dict) else {}

    def _vault_token(self) -> str:
        """Return an auth token for the current Vault read."""
        config = self.vault_config
        if config.auth_method == "cert":
            return self._cert_login()
        if config.auth_method in {"", "token"}:
            if config.token:
                self._log_source("vault-token")
            return config.token
        self.logger.info("Vault auth method %s is not enabled for secret resolution.", config.auth_method)
        return ""

    def _cert_login(self) -> str:
        """Login to Vault using client certificate auth and return an in-memory token."""
        config = self.vault_config
        if not (config.url and config.client_cert and config.client_key):
            self.logger.info("Vault cert auth is configured but client certificate material is incomplete.")
            return ""

        url = f"{config.url.rstrip('/')}/v1/auth/{config.cert_auth_mount}/login"
        body = {"name": config.cert_role} if config.cert_role else {}
        response = self.http_session.post(
            url,
            json=body,
            cert=(config.client_cert, config.client_key),
            verify=config.verify,
            timeout=config.timeout,
        )
        response.raise_for_status()
        token = response.json().get("auth", {}).get("client_token", "")
        if token:
            self._log_source("vault-cert")
        return token

    def _secret_url(self, vault: VaultSecretRef) -> str:
        """Build a Vault API URL for the requested secret."""
        config = self.vault_config
        if vault.kv_version == "v2":
            return f"{config.url.rstrip('/')}/v1/{vault.normalized_mount}/data/{vault.normalized_path}"
        return f"{config.url.rstrip('/')}/v1/{vault.normalized_mount}/{vault.normalized_path}"

    def _vault_source(self) -> str:
        """Return the configured Vault source name for logging."""
        return "vault-cert" if self.vault_config.auth_method == "cert" else "vault-token"

    def _log_source(
        self,
        source: str,
        *,
        env_names: Sequence[str] = (),
        vault: VaultSecretRef | None = None,
        key: str = "",
        field: str = "",
    ) -> None:
        """Log non-secret resolution metadata only."""
        details = []
        if field:
            details.append(f"field={field}")
        if env_names:
            details.append("env=" + ",".join(env_names))
        if vault is not None:
            details.append(f"vault={vault.normalized_mount}/{vault.normalized_path}")
        if key:
            details.append(f"key={key}")
        suffix = " (" + "; ".join(details) + ")" if details else ""
        self.logger.info("Resolved secret source: %s%s", source, suffix)
