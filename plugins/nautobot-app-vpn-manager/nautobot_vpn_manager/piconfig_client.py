"""Client helpers for the piconfig Nautobot integration API."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

DEFAULT_WORKER_ONLINE_TTL_SECONDS = 15 * 60
REMOTE_WORKER_QUEUE_PREFIX = "remote-worker-"
LEGACY_VPN_QUEUE_PREFIX = "vpn-"


class PiconfigApiError(RuntimeError):
    """Normalized piconfig integration API error."""


class PiconfigConfigurationError(PiconfigApiError):
    """Raised when required piconfig client settings are missing."""


@dataclass(frozen=True)
class PiconfigClientConfig:
    """Connection settings for piconfig's Nautobot integration API."""

    base_url: str
    client_cert: str = ""
    client_key: str = ""
    ca_bundle: str = ""
    verify: bool = True
    timeout: int = 30


def _normalize_tenant_slug(value: str) -> str:
    value = (value or "").strip().lower()
    for prefix in (REMOTE_WORKER_QUEUE_PREFIX, LEGACY_VPN_QUEUE_PREFIX):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-_")
    return value


def queue_names_for_tenant_slugs(tenant_slugs: list[str]) -> list[str]:
    """Return remote-worker Celery queue names for tenant slugs."""

    queues = []
    for tenant_slug in tenant_slugs:
        normalized = _normalize_tenant_slug(tenant_slug)
        if normalized:
            queues.append(f"{REMOTE_WORKER_QUEUE_PREFIX}{normalized}")
    return queues


def tenant_slugs_from_assignment_input(raw_value: str) -> list[str]:
    """Parse tenant slugs, remote-worker-* queues, or legacy vpn-* aliases into tenant slugs."""

    tenant_slugs: list[str] = []
    seen = set()
    for item in (raw_value or "").split(","):
        tenant_slug = _normalize_tenant_slug(item)
        if tenant_slug and tenant_slug not in seen:
            tenant_slugs.append(tenant_slug)
            seen.add(tenant_slug)
    return tenant_slugs


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _heartbeat_age_seconds(worker: dict[str, Any], last_seen: Any, now: datetime) -> int | None:
    explicit_age = worker.get("heartbeat_age_seconds", worker.get("heartbeatAgeSeconds"))
    if explicit_age is not None:
        try:
            return max(0, int(explicit_age))
        except (TypeError, ValueError):
            return None

    last_seen_dt = _parse_datetime(last_seen)
    if last_seen_dt is None:
        return None
    return max(0, int((now.astimezone(timezone.utc) - last_seen_dt).total_seconds()))


def _worker_status(*, is_enabled: bool, heartbeat_age_seconds: int | None, online_ttl_seconds: int) -> tuple[str, bool]:
    if not is_enabled:
        return "disabled", False
    if heartbeat_age_seconds is None:
        return "unknown", False
    if heartbeat_age_seconds <= online_ttl_seconds:
        return "online", True
    return "offline", False


def normalize_worker_payload(
    worker: dict[str, Any],
    *,
    now: datetime | None = None,
    online_ttl_seconds: int = DEFAULT_WORKER_ONLINE_TTL_SECONDS,
) -> dict[str, Any]:
    """Adapt piconfig's worker record shape to the dashboard's worker shape."""

    hostname = worker.get("hostname") or worker.get("hostName") or ""
    tenant_slugs = list(worker.get("tenant_slugs") or worker.get("tenantSlugs") or [])
    queue_names = queue_names_for_tenant_slugs(tenant_slugs)
    last_seen = worker.get("last_seen") or worker.get("lastSeen")
    is_enabled = bool(worker.get("is_enabled", worker.get("isEnabled", True)))
    heartbeat_age_seconds = _heartbeat_age_seconds(worker, last_seen, now or datetime.now(timezone.utc))
    status, is_online = _worker_status(
        is_enabled=is_enabled,
        heartbeat_age_seconds=heartbeat_age_seconds,
        online_ttl_seconds=online_ttl_seconds,
    )

    return {
        "worker_id": hostname,
        "hostname": hostname,
        "celery_node_name": worker.get("celery_node_name") or worker.get("celeryNodeName") or "",
        "ip_address": worker.get("ip_address") or worker.get("ipAddress") or "",
        "platform": worker.get("worker_kind") or worker.get("workerKind") or "",
        "software_version": worker.get("version") or "",
        "last_heartbeat": last_seen,
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "registered_at": worker.get("first_seen") or worker.get("firstSeen"),
        "last_assignment": worker.get("assignment_updated_at") or worker.get("assignmentUpdatedAt"),
        "assignment_status": "assigned" if tenant_slugs else "idle",
        "advertised_queues": queue_names,
        "desired_queues": queue_names,
        "current_queues": queue_names,
        "tenant_slugs": tenant_slugs,
        "assignment_version": worker.get("assignment_version", worker.get("assignmentVersion", 0)),
        "needs_restart": False,
        "stale": not is_online,
        "status": status,
        "is_online": is_online,
    }


def _error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if isinstance(payload, dict):
        for key in ("error", "detail", "message"):
            if payload.get(key):
                return str(payload[key])
    return response.text or f"{response.status_code} {response.reason}"


class PiconfigClient:
    """Small requests wrapper for the piconfig Nautobot integration API."""

    def __init__(self, config: PiconfigClientConfig):
        self.config = config

    def _cert_arg(self) -> str | tuple[str, str] | None:
        if not self.config.client_cert:
            return None
        if self.config.client_key:
            return (self.config.client_cert, self.config.client_key)
        return self.config.client_cert

    def _verify_arg(self) -> bool | str:
        return self.config.ca_bundle or self.config.verify

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.config.base_url:
            raise PiconfigConfigurationError("PICONFIG_API_URL is not configured for Nautobot remote workers")

        session = requests.Session()
        session.trust_env = False
        response = session.request(
            method=method,
            url=f"{self.config.base_url.rstrip('/')}{path}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=self.config.timeout,
            cert=self._cert_arg(),
            verify=self._verify_arg(),
        )
        if not response.ok:
            raise PiconfigApiError(_error_message(response))
        return response.json()

    def list_workers(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/integrations/nautobot/v1/workers/")
        return [normalize_worker_payload(worker) for worker in payload.get("results", [])]

    def set_worker_tenants(self, hostname: str, tenant_slugs: list[str]) -> dict[str, Any]:
        payload = self._request(
            "PUT",
            f"/api/integrations/nautobot/v1/workers/{quote(hostname, safe='')}/tenants/",
            {"tenant_slugs": tenant_slugs},
        )
        return normalize_worker_payload(payload)
