"""Cisco Commerce API client utilities."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import requests
from django.conf import settings

from nbcot.constants import DEFAULT_TOKEN_URL, ENVIRONMENT_ENDPOINTS

from .exceptions import CiscoAuthenticationError, CiscoGraphQLError, NBCOTConfigurationError
from .queries import (
    DEFAULT_ORDER_DETAILS_QUERY,
    DEFAULT_SEARCH_QUERY,
    DEFAULT_SUBSCRIPTION_DETAILS_QUERY,
    DEFAULT_SUBSCRIPTION_SEARCH_QUERY,
)

SEARCH_KEY_MAP = {
    "order_number": "SALES_ORDER_ID",
    "customer_po_number": "PURCHASE_ORDER_ID",
    "account_name": "END_CUSTOMER_NAME",
    "account_number": "END_CUSTOMER_NUMBER",
    "status": "ORDER_STATUS",
}

CCWR_PARTY_TYPE_MAP = {
    "end_customer_name": "END_CUSTOMER",
    "end_customer_site_id": "INSTALL_SITE",
    "bill_to_id": "BILL_TO",
}


def _first_env(*names: str) -> str:
    """Return the first non-empty environment variable from names."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def _load_vault_credentials() -> tuple[str, str]:
    """Resolve Cisco OAuth credentials from the configured Vault KV secret."""
    vault_url = os.getenv("HASHICORP_VAULT_URL")
    vault_token = os.getenv("HASHICORP_VAULT_TOKEN")
    if not vault_url or not vault_token:
        return "", ""

    vault_mount = os.getenv("CISCO_API_VAULT_MOUNT", "kv").strip("/")
    vault_path = os.getenv("CISCO_API_VAULT_PATH", "CISCO_API_CONSOLE").strip("/")
    vault_namespace = os.getenv("HASHICORP_VAULT_NAMESPACE") or os.getenv("VAULT_NAMESPACE")

    headers = {"X-Vault-Token": vault_token}
    if vault_namespace:
        headers["X-Vault-Namespace"] = vault_namespace

    verify = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE") or True
    response = requests.get(
        f"{vault_url.rstrip('/')}/v1/{vault_mount}/data/{vault_path}",
        headers=headers,
        verify=verify,
        timeout=15,
    )
    response.raise_for_status()
    secret_data = response.json().get("data", {}).get("data", {})
    return (
        secret_data.get("CISCO_MODERN_API_CLIENT_ID") or secret_data.get("API_TOKEN_CLIENT_ID") or "",
        secret_data.get("CISCO_MODERN_API_SECRET") or secret_data.get("API_TOKEN_CLIENT_PASS") or "",
    )


def _resolve_client_credentials(config: dict[str, Any]) -> tuple[str, str]:
    """Resolve Cisco OAuth credentials from plugin config, environment, then Vault."""
    client_id = (
        config.get("client_id")
        or _first_env("CISCO_MODERN_API_CLIENT_ID", "NBCOT_CLIENT_ID", "API_TOKEN_CLIENT_ID")
    )
    client_secret = (
        config.get("client_secret")
        or _first_env("CISCO_MODERN_API_SECRET", "NBCOT_CLIENT_SECRET", "API_TOKEN_CLIENT_PASS")
    )
    if client_id and client_secret:
        return client_id, client_secret

    vault_client_id, vault_client_secret = _load_vault_credentials()
    return client_id or vault_client_id, client_secret or vault_client_secret


@dataclass
class CiscoSettings:
    """Resolved plugin settings."""

    environment: str
    token_url: str
    graphql_endpoint: str
    client_id: str
    client_secret: str
    tracked_order_refresh_interval_minutes: int
    enable_event_consumer: bool
    search_query_document: str
    order_details_query_document: str
    subscription_search_query_document: str
    subscription_details_query_document: str

    @classmethod
    def load(cls, environment_override: str | None = None) -> "CiscoSettings":
        """Resolve settings from Nautobot plugin config."""
        config = settings.PLUGINS_CONFIG.get("nbcot", {})
        configured_environment = str(config.get("environment", "prod")).lower()
        environment = (environment_override or configured_environment).lower()
        configured_endpoint = config.get("graphql_endpoint")
        graphql_endpoint = (
            ENVIRONMENT_ENDPOINTS.get(environment)
            if environment_override
            else configured_endpoint or ENVIRONMENT_ENDPOINTS.get(environment)
        )
        token_url = config.get("token_url") or DEFAULT_TOKEN_URL
        client_id, client_secret = _resolve_client_credentials(config)
        return cls(
            environment=environment,
            token_url=token_url,
            graphql_endpoint=graphql_endpoint or "",
            client_id=client_id,
            client_secret=client_secret,
            tracked_order_refresh_interval_minutes=int(config.get("tracked_order_refresh_interval_minutes", 60)),
            enable_event_consumer=bool(config.get("enable_event_consumer", False)),
            search_query_document=config.get("search_query_document", "") or DEFAULT_SEARCH_QUERY,
            order_details_query_document=config.get("order_details_query_document", "") or DEFAULT_ORDER_DETAILS_QUERY,
            subscription_search_query_document=config.get("subscription_search_query_document", "")
            or DEFAULT_SUBSCRIPTION_SEARCH_QUERY,
            subscription_details_query_document=config.get("subscription_details_query_document", "")
            or DEFAULT_SUBSCRIPTION_DETAILS_QUERY,
        )

    def validate(self):
        """Validate minimum settings needed to call Cisco."""
        missing = []
        if not self.client_id:
            missing.append("client_id")
        if not self.client_secret:
            missing.append("client_secret")
        if not self.graphql_endpoint:
            missing.append("graphql_endpoint")
        if missing:
            raise NBCOTConfigurationError(
                "NBCOT plugin settings are incomplete. Configure: " + ", ".join(sorted(missing))
            )


class CiscoGraphQLClient:
    """Tiny OAuth2 + GraphQL client for Cisco Commerce."""

    def __init__(
        self,
        http_session: requests.Session | None = None,
        plugin_settings: CiscoSettings | None = None,
        environment_override: str | None = None,
    ):
        """Initialize client state."""
        self.settings = plugin_settings or CiscoSettings.load(environment_override=environment_override)
        self.settings.validate()
        self.http_session = http_session or requests.Session()
        self._access_token = None
        self._access_token_expires_at = None

    def _token_is_valid(self) -> bool:
        """Check cached token expiry."""
        return bool(
            self._access_token
            and self._access_token_expires_at
            and datetime.utcnow() < self._access_token_expires_at
        )

    def get_access_token(self) -> str:
        """Retrieve or reuse an OAuth access token."""
        if self._token_is_valid():
            return self._access_token

        response = self.http_session.post(
            self.settings.token_url,
            data={"grant_type": "client_credentials"},
            auth=(self.settings.client_id, self.settings.client_secret),
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if response.status_code >= 400:
            raise CiscoAuthenticationError(
                f"Token request failed with status {response.status_code}: {response.text[:500]}"
            )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise CiscoAuthenticationError("Token response did not include access_token.")

        expires_in = int(payload.get("expires_in", 3600))
        self._access_token = token
        self._access_token_expires_at = datetime.utcnow() + timedelta(seconds=max(expires_in - 30, 0))
        return token

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL operation and return its data payload."""
        response = self.http_session.post(
            self.settings.graphql_endpoint,
            json={"query": query, "variables": variables or {}},
            headers={
                "Authorization": f"Bearer {self.get_access_token()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise CiscoGraphQLError(f"GraphQL request failed with status {response.status_code}: {response.text[:500]}")

        payload = response.json()
        if payload.get("errors"):
            raise CiscoGraphQLError(self._format_graphql_errors(payload["errors"]))
        return payload.get("data", {})

    @staticmethod
    def _extract_messages(result: dict[str, Any]) -> list[str]:
        messages = []
        for message in result.get("messages") or []:
            description = message.get("description") or message.get("message") or message.get("code")
            if description:
                messages.append(str(description))
        return messages

    @staticmethod
    def _format_graphql_errors(errors: list[dict[str, Any]]) -> str:
        messages = []
        for error in errors:
            for message in (error.get("extensions") or {}).get("messages") or []:
                description = message.get("description") or message.get("message") or message.get("code")
                if description:
                    messages.append(str(description))
            if not messages and error.get("message"):
                messages.append(str(error["message"]))
        return "; ".join(messages) if messages else str(errors)

    @staticmethod
    def _build_order_search_input(filters: dict[str, Any], page_size: int = 20) -> dict[str, Any]:
        criteria = []
        for key, value in filters.items():
            search_key = SEARCH_KEY_MAP.get(key)
            if not search_key or value in (None, ""):
                continue
            criteria.append({"orderSearchKey": search_key, "orderSearchValue": str(value)})
        return {
            "orderSearchCriteria": criteria,
            "sortByOrderCharacteristics": "CREATION_DATE",
            "pagination": {"page": 1, "pageSize": page_size, "sortOrder": "DESC"},
        }

    @staticmethod
    def _build_subscription_search_input(filters: dict[str, Any], include_exact_id: bool = False) -> dict[str, Any]:
        criteria = [
            {
                "mySubscriptionSearchKey": "FROM_DATE",
                "mySubscriptionSearchValue": str(filters.get("from_date") or "2022-01-01"),
            },
            {
                "mySubscriptionSearchKey": "TO_DATE",
                "mySubscriptionSearchValue": str(filters.get("to_date") or "2035-12-31"),
            },
        ]
        parties = []
        for key, party_type in CCWR_PARTY_TYPE_MAP.items():
            value = filters.get(key)
            if not value:
                continue
            party = {"type": party_type}
            if key.endswith("_name"):
                party["name"] = str(value)
            else:
                party["id"] = str(value)
            parties.append(party)

        payload: dict[str, Any] = {
            "mySubscriptionSearchCriteria": criteria,
            "pagination": {"page": 1, "pageSize": int(filters.get("page_size") or 20), "sortOrder": "DESC"},
        }
        if parties:
            payload["party"] = parties
        if filters.get("status"):
            payload["status"] = [str(filters["status"]).upper()]
        if include_exact_id and filters.get("subscription_identifier"):
            payload["mySubscriptionIds"] = [str(filters["subscription_identifier"]).strip()]
        return payload

    def search_orders(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        """Run the configured search operation."""
        data = self.execute(self.settings.search_query_document, {"input": self._build_order_search_input(filters)})
        result = data.get("searchOrder") or {}
        messages = self._extract_messages(result)
        if result.get("businessStatus") == "FAILURE" and messages:
            raise CiscoGraphQLError("; ".join(messages))
        objects = result.get("objects") or result.get("items") or result.get("results") or []
        return objects or []

    def get_order_details(self, order_number: str) -> dict[str, Any]:
        """Run the configured detail operation."""
        search_input = self._build_order_search_input({"order_number": order_number}, page_size=1)
        data = self.execute(self.settings.order_details_query_document, {"input": search_input})
        result = data.get("getOrderDetails") or {}
        messages = self._extract_messages(result)
        if result.get("businessStatus") == "FAILURE" and messages:
            raise CiscoGraphQLError("; ".join(messages))
        objects = result.get("objects") or []
        return objects[0] if objects else {}

    def search_subscriptions(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        """Run the configured CCW-R subscription search operation."""
        variables = {"input": self._build_subscription_search_input(filters)}
        data = self.execute(self.settings.subscription_search_query_document, variables)
        result = data.get("searchSubscription") or {}
        messages = self._extract_messages(result)
        if result.get("businessStatus") == "FAILURE" and messages:
            raise CiscoGraphQLError("; ".join(messages))
        return result.get("objects") or []

    def get_subscription_details(self, filters: dict[str, Any]) -> dict[str, Any]:
        """Run the configured CCW-R subscription detail operation."""
        variables = {"input": self._build_subscription_search_input(filters, include_exact_id=True)}
        data = self.execute(self.settings.subscription_details_query_document, variables)
        result = data.get("getSubscriptionDetails") or {}
        messages = self._extract_messages(result)
        if result.get("businessStatus") == "FAILURE" and messages:
            raise CiscoGraphQLError("; ".join(messages))
        objects = result.get("objects") or []
        return objects[0] if objects else {}
