"""FastAPI service providing a tenant-scoped HTTP wrapper around vpn.sh."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(os.getenv("VPN_PROJECT_ROOT", "/workspace")).resolve()
if not REPO_ROOT.exists():
    raise RuntimeError(
        "VPN Control API expects the Nautobot project to be available; "
        "mount it at /workspace or set VPN_PROJECT_ROOT."
    )


def _detect_host_repo_root(mount_path: Path) -> Path:
    """Best-effort detection of the host path backing the mounted repository."""
    override = os.getenv("VPN_PROJECT_ROOT_HOST")
    if override:
        return Path(override).resolve()

    container_id = os.getenv("HOSTNAME")
    if not container_id:
        return mount_path

    destination = str(mount_path)
    inspect_template = "{{range .Mounts}}{{if eq .Destination \"%s\"}}{{.Source}}{{end}}{{end}}" % (
        destination.replace("\\", "\\\\").replace('"', '\\"')
    )
    try:
        result = subprocess.run(
            ["docker", "inspect", container_id, "--format", inspect_template],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return mount_path

    host_path = result.stdout.strip()
    if host_path:
        host_path_obj = Path(host_path)
        if host_path_obj.exists():
            return host_path_obj.resolve()
    return mount_path


REPO_HOST_ROOT = _detect_host_repo_root(REPO_ROOT)
logger = logging.getLogger("uvicorn.error")
logger.info("Using repository root %s (host path %s)", REPO_ROOT, REPO_HOST_ROOT)

VPN_SCRIPT = REPO_ROOT / "vpn" / "vpn.sh"
ENV_DIR = REPO_ROOT / "environments"
HOST_ENV_DIR = REPO_HOST_ROOT / "environments"

VPN_COMPOSE_PROJECT_PREFIX = os.getenv("VPN_COMPOSE_PROJECT_PREFIX", "shms-vpn")
VPN_CONTAINER_PREFIX = os.getenv("VPN_CONTAINER_PREFIX", "shms-vpn")
VPN_WORKER_CONTAINER_PREFIX = os.getenv("VPN_WORKER_CONTAINER_PREFIX", "celery-worker-vpn")
VPN_WORKER_NAME_PREFIX = os.getenv("VPN_WORKER_NAME_PREFIX", "vpn-worker")
VPN_NODE_NAME = os.getenv("VPN_NODE_NAME", "nb-ha-01")
VPN_SERVICE_NAME = os.getenv("VPN_SERVICE_NAME", "vpn")
VPN_WORKER_SERVICE = os.getenv("VPN_WORKER_SVC", "celery_worker_vpn")
VPN_SERVICE_COMPOSE_FILE = os.getenv("VPN_SERVICE_COMPOSE_FILE", "docker-compose.shms-vpn.service.yml")
VPN_QUEUE_COMPOSE_FILE = os.getenv("VPN_QUEUE_COMPOSE_FILE", "docker-compose.shms-vpn.queue.yml")
VPN_HOST_QUEUE_COMPOSE_FILE = os.getenv("VPN_HOST_QUEUE_COMPOSE_FILE", "docker-compose.shms-vpn.host-worker.yml")
VPN_HOST_SLOT_STATE_FILE = Path(
    os.getenv("VPN_HOST_SLOT_STATE_FILE", str(ENV_DIR / "vpn_host_slots.json"))
).resolve()
CISCO_HOST_HELPER = Path(os.getenv("CISCO_HOST_HELPER", str(REPO_ROOT / "vpn" / "cisco_secure_client_host.sh"))).resolve()
REMOTE_WORKER_STATE_FILE = Path(
    os.getenv("VPN_REMOTE_WORKER_STATE_FILE", str(ENV_DIR / "vpn_remote_workers.json"))
).resolve()
REMOTE_WORKER_STALE_SECONDS = int(os.getenv("VPN_REMOTE_WORKER_STALE_SECONDS", "180"))
TENANT_QUEUE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9-]*[a-z0-9])?$")
REMOTE_WORKER_QUEUE_PREFIX = "remote-worker-"
LEGACY_VPN_QUEUE_PREFIX = "vpn-"

if not VPN_SCRIPT.exists():
    raise RuntimeError(f"Expected vpn script at {VPN_SCRIPT}, but it was not found.")


def _load_env_value(path: Path, key: str) -> Optional[str]:
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"')
    return None


API_KEY = os.getenv("VPN_CONTROL_API_KEY")
if not API_KEY:
    override_path = os.getenv("VPN_CONTROL_API_ENV_FILE")
    search_paths = []
    if override_path:
        search_paths.append(Path(override_path))
    search_paths.extend([ENV_DIR / "local.shms.env", ENV_DIR / "creds.shms.env"])
    for file_path in search_paths:
        value = _load_env_value(file_path, "VPN_CONTROL_API_KEY")
        if value:
            os.environ["VPN_CONTROL_API_KEY"] = value
            API_KEY = value
            break
API_KEY_HEADER = APIKeyHeader(name="X-VPN-Control", auto_error=False)


def require_api_key(api_key: Optional[str] = Depends(API_KEY_HEADER)) -> None:
    """Validate API key if VPN_CONTROL_API_KEY is configured."""
    if API_KEY is None:
        return
    if api_key != API_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _slot_slug(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    if value:
        return value
    digest = hashlib.sha1((value or "tenant").encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"tenant-{digest[:8]}"


@dataclass(frozen=True)
class SlotContext:
    customer: str
    slug: str
    queue_name: str
    project_name: str
    worker_name_prefix: str


@dataclass(frozen=True)
class VpnProfile:
    vpn_type: str = ""
    vpn_client: str = ""
    host: str = ""
    port: str = ""
    profile_name: str = ""
    usergroup: str = ""
    client_runtime: str = "container"
    worker_network_mode: str = "service-vpn"


def slot_context(customer: str) -> SlotContext:
    customer = customer.strip()
    if not customer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer cannot be empty")
    slug = _slot_slug(customer)
    return SlotContext(
        customer=customer,
        slug=slug,
        queue_name=f"vpn-{slug}",
        project_name=f"{VPN_COMPOSE_PROJECT_PREFIX}-{slug}",
        worker_name_prefix=f"{VPN_WORKER_NAME_PREFIX}-{VPN_NODE_NAME}-{slug}",
    )


def _vpn_secret_path(customer: str) -> str:
    return f"kv/{customer}/vpn"


def _metadata_custom_metadata(payload: dict[str, Any]) -> dict[str, str]:
    raw_metadata = payload.get("data", {}).get("custom_metadata") or payload.get("custom_metadata") or {}
    if not isinstance(raw_metadata, dict):
        return {}
    return {str(key): str(value) for key, value in raw_metadata.items() if value is not None}


def load_vault_vpn_metadata(context: SlotContext, *, env: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Read safe VPN profile metadata from Vault without reading secret data."""
    try:
        result = run_command(
            ["vault", "kv", "metadata", "get", "-format=json", _vpn_secret_path(context.customer)],
            env=env,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        logger.warning("Unable to read Vault VPN metadata for %s; falling back to runtime defaults.", context.customer)
        return {}

    try:
        return _metadata_custom_metadata(json.loads(result.stdout or "{}"))
    except json.JSONDecodeError:
        logger.warning("Vault VPN metadata for %s was not valid JSON.", context.customer)
        return {}


def _first_nonempty(*values: Optional[str]) -> str:
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return ""


def resolve_vpn_profile(
    context: SlotContext,
    *,
    env: Optional[dict[str, str]] = None,
    overrides: Optional[dict[str, Optional[str]]] = None,
) -> VpnProfile:
    """Resolve VPN type/client/runtime from Vault metadata and per-request overrides."""
    metadata = load_vault_vpn_metadata(context, env=env)
    overrides = overrides or {}

    vpn_type = _first_nonempty(overrides.get("vpn_type"), metadata.get("vpn_type"))
    vpn_client = _first_nonempty(overrides.get("vpn_client"), metadata.get("vpn_client"))
    if vpn_type == "cisco-anyconnect" and not vpn_client:
        vpn_client = "openconnect"

    client_runtime = _first_nonempty(overrides.get("client_runtime"), metadata.get("client_runtime"))
    if not client_runtime:
        client_runtime = "host" if vpn_client == "cisco-secure-client" else "container"

    worker_network_mode = _first_nonempty(
        overrides.get("worker_network_mode"),
        metadata.get("worker_network_mode"),
    )
    if not worker_network_mode:
        worker_network_mode = "host" if client_runtime == "host" else "service-vpn"

    return VpnProfile(
        vpn_type=vpn_type,
        vpn_client=vpn_client,
        host=_first_nonempty(overrides.get("host"), metadata.get("host")),
        port=_first_nonempty(overrides.get("port"), metadata.get("port")),
        profile_name=_first_nonempty(overrides.get("profile_name"), metadata.get("profile_name")),
        usergroup=_first_nonempty(overrides.get("usergroup"), metadata.get("usergroup")),
        client_runtime=client_runtime,
        worker_network_mode=worker_network_mode,
    )


def load_host_slot_state() -> dict[str, Any]:
    if not VPN_HOST_SLOT_STATE_FILE.exists():
        return {"slots": {}}
    try:
        payload = json.loads(VPN_HOST_SLOT_STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        logger.warning("Host VPN slot state file %s is unreadable; starting fresh.", VPN_HOST_SLOT_STATE_FILE)
        return {"slots": {}}
    slots = payload.get("slots")
    if not isinstance(slots, dict):
        return {"slots": {}}
    return {"slots": slots}


def save_host_slot_state(state: dict[str, Any]) -> None:
    VPN_HOST_SLOT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = VPN_HOST_SLOT_STATE_FILE.with_suffix(f"{VPN_HOST_SLOT_STATE_FILE.suffix}.tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp_path.replace(VPN_HOST_SLOT_STATE_FILE)


def record_host_slot(context: SlotContext, profile: VpnProfile) -> None:
    state = load_host_slot_state()
    slots = state.setdefault("slots", {})
    slots[context.slug] = {
        "customer": context.customer,
        "slot": context.slug,
        "queue_name": context.queue_name,
        "project_name": context.project_name,
        "worker_name_prefix": context.worker_name_prefix,
        "profile": asdict(profile),
        "updated_at": utcnow().isoformat(),
    }
    save_host_slot_state(state)


def delete_host_slot(context: SlotContext) -> None:
    state = load_host_slot_state()
    slots = state.setdefault("slots", {})
    if context.slug in slots:
        del slots[context.slug]
        save_host_slot_state(state)


def host_slot_contexts() -> list[SlotContext]:
    contexts: list[SlotContext] = []
    for record in load_host_slot_state().get("slots", {}).values():
        if not isinstance(record, dict):
            continue
        customer = str(record.get("customer") or "")
        slot = str(record.get("slot") or _slot_slug(customer))
        if not customer or not slot:
            continue
        contexts.append(
            SlotContext(
                customer=customer,
                slug=slot,
                queue_name=str(record.get("queue_name") or f"vpn-{slot}"),
                project_name=str(record.get("project_name") or f"{VPN_COMPOSE_PROJECT_PREFIX}-{slot}"),
                worker_name_prefix=str(
                    record.get("worker_name_prefix") or f"{VPN_WORKER_NAME_PREFIX}-{VPN_NODE_NAME}-{slot}"
                ),
            )
        )
    return contexts


def host_slot_profile(context: SlotContext) -> VpnProfile:
    record = load_host_slot_state().get("slots", {}).get(context.slug, {})
    raw_profile = record.get("profile") if isinstance(record, dict) else {}
    if not isinstance(raw_profile, dict):
        raw_profile = {}
    return VpnProfile(
        vpn_type=str(raw_profile.get("vpn_type") or "cisco-anyconnect"),
        vpn_client=str(raw_profile.get("vpn_client") or "cisco-secure-client"),
        host=str(raw_profile.get("host") or ""),
        port=str(raw_profile.get("port") or ""),
        profile_name=str(raw_profile.get("profile_name") or ""),
        usergroup=str(raw_profile.get("usergroup") or ""),
        client_runtime=str(raw_profile.get("client_runtime") or "host"),
        worker_network_mode=str(raw_profile.get("worker_network_mode") or "host"),
    )


def slot_env(context: SlotContext, *, passthrough: Optional[str] = None) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHON_VER", "")
    env.setdefault("NAUTOBOT_VERSION", "")
    env.setdefault("PYTHONPATH", "")
    env.setdefault("VPN_PROJECT_ROOT_HOST", str(REPO_HOST_ROOT))
    if not env.get("VAULT_ADDR") and env.get("HASHICORP_VAULT_URL"):
        env["VAULT_ADDR"] = env["HASHICORP_VAULT_URL"]
    if not env.get("VAULT_TOKEN") and env.get("HASHICORP_VAULT_TOKEN"):
        env["VAULT_TOKEN"] = env["HASHICORP_VAULT_TOKEN"]
    if not env.get("VAULT_NAMESPACE") and env.get("HASHICORP_VAULT_NAMESPACE"):
        env["VAULT_NAMESPACE"] = env["HASHICORP_VAULT_NAMESPACE"]
    if not env.get("VAULT_CACERT"):
        if env.get("REQUESTS_CA_BUNDLE"):
            env["VAULT_CACERT"] = env["REQUESTS_CA_BUNDLE"]
        elif env.get("SSL_CERT_FILE"):
            env["VAULT_CACERT"] = env["SSL_CERT_FILE"]
    env.update(
        {
            "CUSTOMER": context.customer,
            "VPN_QUEUE": context.queue_name,
            "VPN_COMPOSE_PROJECT": context.project_name,
            "VPN_WORKER_NAME_PREFIX": context.worker_name_prefix,
            "VPN_SLOT_SLUG": context.slug,
            "VPN_TENANT_NAME": context.customer,
            "VPN_USE_DEDICATED_WORKER": "true",
            "VPN_WORKER_SVC": VPN_WORKER_SERVICE,
            "VPN_SERVICE_COMPOSE_FILE": VPN_SERVICE_COMPOSE_FILE,
            "VPN_QUEUE_COMPOSE_FILE": VPN_QUEUE_COMPOSE_FILE,
        }
    )
    if passthrough:
        env["VPN_PASSTHROUGH_DOMAINS"] = passthrough
    return env


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class StartRequest(BaseModel):
    customer: str = Field(..., min_length=1, description="VPN customer / tenant profile name")
    worker_count: int = Field(1, ge=1, le=32, description="Desired number of workers bound to this tenant queue")
    vpn_type: Optional[str] = Field(None, description="Protocol/product family override, for example cisco-anyconnect")
    vpn_client: Optional[str] = Field(None, description="VPN client implementation override")
    profile_name: Optional[str] = Field(None, description="Official Cisco Secure Client profile alias override")
    usergroup: Optional[str] = Field(None, description="AnyConnect user group override")
    client_runtime: Optional[str] = Field(None, description="Runtime location override: container or host")
    worker_network_mode: Optional[str] = Field(None, description="Worker network mode override")
    otp: Optional[str] = Field(None, description="OTP/MFA code for providers that require it")
    authgroup: Optional[str] = Field(None, description="Authentication group / realm override")
    banner_response: Optional[str] = Field(
        None, description="Response for banner prompts (defaults to 'yes')"
    )
    extra_args: Optional[str] = Field(
        None, description="Additional flags passed to vpn.sh --extra-args"
    )
    passthrough: Optional[str] = Field(
        None, description="Value for VPN_PASSTHROUGH_DOMAINS during this start"
    )


class StopRequest(BaseModel):
    customer: Optional[str] = Field(
        None, description="Customer / tenant profile to stop. If omitted, stop the only running slot."
    )


class ScaleRequest(BaseModel):
    customer: str = Field(..., min_length=1, description="Customer / tenant profile to scale")
    worker_count: int = Field(..., ge=1, le=32, description="Desired number of workers bound to the tenant queue")


class StopResponse(BaseModel):
    status: str
    customer: Optional[str] = None
    slot: Optional[str] = None


class WorkerStatus(BaseModel):
    index: int
    name: str
    container_name: str
    running: bool
    status: str


class SlotStatus(BaseModel):
    customer: str
    slot: str
    queue_name: str
    project_name: str
    source_of_truth: str = "vault"
    vpn_type: Optional[str] = None
    vpn_client: Optional[str] = None
    client_runtime: Optional[str] = None
    worker_network_mode: Optional[str] = None
    desired_workers: int = 0
    running_workers: int = 0
    status: str
    vpn_running: bool
    worker_running: bool
    tunnel_interface: Optional[str] = None
    workers: list[WorkerStatus] = Field(default_factory=list)


class StatusResponse(BaseModel):
    vpn_running: bool
    customer: Optional[str] = None
    tunnel_interface: Optional[str] = None
    worker_running: bool
    slots: list[SlotStatus] = Field(default_factory=list)


class RemoteWorkerRegisterRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, description="Stable remote worker identity")
    hostname: str = Field(..., min_length=1, description="Machine hostname")
    software_version: Optional[str] = Field(None, description="Worker software version")
    platform: Optional[str] = Field(None, description="Worker runtime platform")
    capabilities: dict[str, Any] = Field(default_factory=dict, description="Advertised worker capabilities")
    advertised_queues: list[str] = Field(
        default_factory=list,
        description="Queues this worker is willing and able to consume",
    )
    current_queues: list[str] = Field(
        default_factory=list,
        description="Queues the worker is currently consuming",
    )
    status: str = Field("up", description="Worker self-reported status")


class RemoteWorkerHeartbeatRequest(BaseModel):
    hostname: Optional[str] = Field(None, description="Current machine hostname")
    software_version: Optional[str] = Field(None, description="Worker software version")
    platform: Optional[str] = Field(None, description="Worker runtime platform")
    capabilities: Optional[dict[str, Any]] = Field(None, description="Advertised worker capabilities")
    advertised_queues: Optional[list[str]] = Field(
        None,
        description="Queues this worker is willing and able to consume",
    )
    current_queues: Optional[list[str]] = Field(
        None,
        description="Queues the worker is currently consuming",
    )
    status: Optional[str] = Field(None, description="Worker self-reported status")


class RemoteWorkerAssignmentRequest(BaseModel):
    desired_queues: list[str] = Field(
        default_factory=list,
        description="Queues the worker should consume after restart/reconfiguration",
    )


class RemoteWorkerStatus(BaseModel):
    worker_id: str
    hostname: str
    software_version: Optional[str] = None
    platform: Optional[str] = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    advertised_queues: list[str] = Field(default_factory=list)
    desired_queues: list[str] = Field(default_factory=list)
    current_queues: list[str] = Field(default_factory=list)
    status: str
    assignment_status: str
    needs_restart: bool
    stale: bool
    heartbeat_age_seconds: Optional[int] = None
    registered_at: Optional[str] = None
    last_assignment: Optional[str] = None
    last_heartbeat: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_timestamp(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _queue_name_error(queue_name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Queue '{queue_name}' is not a valid SHMS remote worker queue name.",
    )


def _tenant_slug_from_queue_name(queue_name: str, *, allow_legacy_vpn_alias: bool) -> tuple[str, bool]:
    if queue_name.startswith(REMOTE_WORKER_QUEUE_PREFIX):
        slug = queue_name[len(REMOTE_WORKER_QUEUE_PREFIX) :]
        is_legacy = False
    elif allow_legacy_vpn_alias and queue_name.startswith(LEGACY_VPN_QUEUE_PREFIX):
        slug = queue_name[len(LEGACY_VPN_QUEUE_PREFIX) :]
        is_legacy = True
    else:
        raise _queue_name_error(queue_name)

    if not TENANT_QUEUE_SLUG_RE.fullmatch(slug):
        raise _queue_name_error(queue_name)
    return slug, is_legacy


def _remote_worker_queue_name(slug: str) -> str:
    return f"{REMOTE_WORKER_QUEUE_PREFIX}{slug}"


def normalize_remote_queue_names(
    values: Optional[list[str]],
    *,
    canonicalize_legacy_vpn_aliases: bool = True,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values or []:
        value = (raw_value or "").strip()
        if not value:
            continue
        slug, is_legacy = _tenant_slug_from_queue_name(
            value,
            allow_legacy_vpn_alias=True,
        )
        if is_legacy and canonicalize_legacy_vpn_aliases:
            value = _remote_worker_queue_name(slug)
        if value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def load_remote_worker_state() -> dict[str, Any]:
    if not REMOTE_WORKER_STATE_FILE.exists():
        return {"workers": {}}
    try:
        payload = json.loads(REMOTE_WORKER_STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        logger.warning("Remote worker state file %s is unreadable; starting fresh.", REMOTE_WORKER_STATE_FILE)
        return {"workers": {}}
    workers = payload.get("workers")
    if not isinstance(workers, dict):
        return {"workers": {}}
    return {"workers": workers}


def save_remote_worker_state(state: dict[str, Any]) -> None:
    REMOTE_WORKER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = REMOTE_WORKER_STATE_FILE.with_suffix(f"{REMOTE_WORKER_STATE_FILE.suffix}.tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp_path.replace(REMOTE_WORKER_STATE_FILE)


def _heartbeat_age(last_heartbeat: Optional[str]) -> Optional[int]:
    normalized = _normalize_timestamp(last_heartbeat)
    if normalized is None:
        return None
    timestamp = datetime.fromisoformat(normalized)
    return max(int((utcnow() - timestamp).total_seconds()), 0)


def build_remote_worker_status(worker_id: str, record: dict[str, Any]) -> RemoteWorkerStatus:
    desired_queues = normalize_remote_queue_names(record.get("desired_queues") or [])
    current_queues = normalize_remote_queue_names(
        record.get("current_queues") or [],
        canonicalize_legacy_vpn_aliases=False,
    )
    advertised_queues = normalize_remote_queue_names(record.get("advertised_queues") or [])
    heartbeat_age_seconds = _heartbeat_age(record.get("last_heartbeat"))
    stale = heartbeat_age_seconds is None or heartbeat_age_seconds > REMOTE_WORKER_STALE_SECONDS
    needs_restart = desired_queues != current_queues

    if stale:
        assignment_status = "stale"
    elif not desired_queues:
        assignment_status = "unassigned"
    elif needs_restart:
        assignment_status = "pending-restart"
    else:
        assignment_status = "assigned"

    return RemoteWorkerStatus(
        worker_id=worker_id,
        hostname=str(record.get("hostname") or worker_id),
        software_version=record.get("software_version"),
        platform=record.get("platform"),
        capabilities=dict(record.get("capabilities") or {}),
        advertised_queues=advertised_queues,
        desired_queues=desired_queues,
        current_queues=current_queues,
        status=str(record.get("status") or "unknown"),
        assignment_status=assignment_status,
        needs_restart=needs_restart,
        stale=stale,
        heartbeat_age_seconds=heartbeat_age_seconds,
        registered_at=_normalize_timestamp(record.get("registered_at")),
        last_assignment=_normalize_timestamp(record.get("last_assignment")),
        last_heartbeat=_normalize_timestamp(record.get("last_heartbeat")),
    )


def list_remote_workers() -> list[RemoteWorkerStatus]:
    state = load_remote_worker_state()
    workers = [
        build_remote_worker_status(worker_id, record)
        for worker_id, record in state.get("workers", {}).items()
    ]
    return sorted(workers, key=lambda worker: (worker.stale, worker.hostname.lower(), worker.worker_id.lower()))


def upsert_remote_worker(
    worker_id: str,
    *,
    hostname: Optional[str],
    software_version: Optional[str],
    platform: Optional[str],
    capabilities: Optional[dict[str, Any]],
    advertised_queues: Optional[list[str]],
    current_queues: Optional[list[str]],
    status_value: Optional[str],
) -> RemoteWorkerStatus:
    normalized_worker_id = worker_id.strip()
    if not normalized_worker_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="worker_id cannot be empty")

    state = load_remote_worker_state()
    workers = state.setdefault("workers", {})
    record = dict(workers.get(normalized_worker_id) or {})
    now = utcnow().isoformat()
    if not record:
        record["registered_at"] = now
        record["desired_queues"] = []

    if hostname:
        record["hostname"] = hostname.strip()
    if software_version is not None:
        record["software_version"] = software_version.strip() or None
    if platform is not None:
        record["platform"] = platform.strip() or None
    if capabilities is not None:
        record["capabilities"] = capabilities
    if advertised_queues is not None:
        record["advertised_queues"] = normalize_remote_queue_names(advertised_queues)
    if current_queues is not None:
        record["current_queues"] = normalize_remote_queue_names(
            current_queues,
            canonicalize_legacy_vpn_aliases=False,
        )
    if status_value is not None:
        record["status"] = status_value.strip() or "unknown"
    record["last_heartbeat"] = now

    workers[normalized_worker_id] = record
    save_remote_worker_state(state)
    return build_remote_worker_status(normalized_worker_id, record)


def set_remote_worker_assignment(worker_id: str, desired_queues: list[str]) -> RemoteWorkerStatus:
    normalized_worker_id = worker_id.strip()
    state = load_remote_worker_state()
    workers = state.setdefault("workers", {})
    record = workers.get(normalized_worker_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown remote worker '{worker_id}'.")

    desired = normalize_remote_queue_names(desired_queues)
    advertised = normalize_remote_queue_names(record.get("advertised_queues") or [])
    if advertised and any(queue_name not in set(advertised) for queue_name in desired):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Desired queues {desired} are not all advertised by worker '{worker_id}'. "
                f"Advertised queues: {advertised}"
            ),
        )

    record["desired_queues"] = desired
    record["last_assignment"] = utcnow().isoformat()
    workers[normalized_worker_id] = record
    save_remote_worker_state(state)
    return build_remote_worker_status(normalized_worker_id, record)


def run_command(
    cmd: list[str],
    *,
    env: Optional[dict[str, str]] = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command relative to the repository root."""
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        check=check,
        capture_output=capture,
        text=True,
    )
    return result


def compose_command(context: SlotContext, extra_files: list[str], args: list[str]) -> list[str]:
    """Generate a tenant-specific docker compose command."""
    command: list[str] = [
        "docker",
        "compose",
        "--project-name",
        context.project_name,
        "--project-directory",
        str(HOST_ENV_DIR),
    ]
    for compose_file in extra_files:
        command.extend(["-f", str((HOST_ENV_DIR / compose_file).resolve())])
    command.extend(args)
    return command


def list_service_containers(context: SlotContext, service: str) -> list[dict[str, object]]:
    """Return docker container metadata for a compose service within one tenant slot."""
    try:
        result = run_command(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"label=com.docker.compose.project={context.project_name}",
                "--filter",
                f"label=com.docker.compose.service={service}",
                "--format",
                "{{.ID}}|{{.Names}}|{{.Status}}|{{.Label \"com.docker.compose.container-number\"}}",
            ]
        )
    except subprocess.CalledProcessError:
        return []

    containers: list[dict[str, object]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        container_id, name, status_text, container_number = line.split("|", 3)
        running = status_text.startswith("Up ")
        try:
            index = int(container_number or "1")
        except ValueError:
            index = 1
        containers.append(
            {
                "id": container_id,
                "name": name,
                "status_text": status_text,
                "running": running,
                "index": index,
            }
        )
    return sorted(containers, key=lambda item: int(item["index"]))


def get_running_container_id(context: SlotContext, service: str) -> Optional[str]:
    """Return the running container ID for a compose service, if any."""
    for container in list_service_containers(context, service):
        if container["running"]:
            return str(container["id"])
    return None


def get_env_var(container_id: str, variable: str) -> Optional[str]:
    """Extract an environment variable value from a container."""
    try:
        result = run_command(
            [
                "docker",
                "inspect",
                "-f",
                f"{{{{range .Config.Env}}}}{{{{if eq (index (split . \"=\") 0) \"{variable}\"}}}}{{{{index (split . \"=\") 1}}}}{{{{end}}}}{{{{end}}}}",
                container_id,
            ],
        )
    except subprocess.CalledProcessError:
        return None
    value = result.stdout.strip()
    return value or None


def check_tunnel_interface(container_id: str) -> Optional[str]:
    """Detect active tunnel interface (ppp0, tun0, or wg0)."""
    for interface in ("ppp0", "tun0", "wg0"):
        try:
            run_command(["docker", "exec", container_id, "ip", "addr", "show", interface])
            return interface
        except subprocess.CalledProcessError:
            continue
    return None


def run_host_secure_client(
    context: SlotContext,
    profile: VpnProfile,
    action: str,
    *,
    banner_response: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    cmd = ["bash", str(CISCO_HOST_HELPER), action, context.customer]
    if profile.profile_name:
        cmd.extend(["--profile-name", profile.profile_name])
    if profile.usergroup:
        cmd.extend(["--usergroup", profile.usergroup])
    if banner_response:
        cmd.extend(["--banner-response", banner_response])
    return run_command(cmd, env=env, check=check)


def start_host_secure_client(
    context: SlotContext,
    profile: VpnProfile,
    *,
    banner_response: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
) -> None:
    try:
        run_host_secure_client(context, profile, "start", banner_response=banner_response, env=env)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Cisco Secure Client start failed", "stdout": exc.stdout, "stderr": exc.stderr},
        ) from exc
    record_host_slot(context, profile)


def stop_host_secure_client(context: SlotContext, *, env: Optional[dict[str, str]] = None) -> None:
    profile = host_slot_profile(context)
    try:
        run_host_secure_client(context, profile, "stop", env=env)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Cisco Secure Client stop failed", "stdout": exc.stdout, "stderr": exc.stderr},
        ) from exc
    delete_host_slot(context)


def host_secure_client_is_connected(context: SlotContext) -> bool:
    profile = host_slot_profile(context)
    try:
        result = run_host_secure_client(context, profile, "status", check=False)
    except (FileNotFoundError, OSError, subprocess.CalledProcessError):
        return False
    output = f"{result.stdout}\n{result.stderr}".lower()
    return "connected" in output and "disconnected" not in output


def slot_state(*, appliance_exists: bool, vpn_running: bool, desired_workers: int, running_workers: int) -> str:
    """Return a coarse slot status suitable for UI LEDs."""
    if vpn_running and desired_workers > 0 and running_workers >= desired_workers:
        return "up"
    if vpn_running or running_workers > 0:
        return "starting"
    if appliance_exists or desired_workers > 0:
        return "failed"
    return "down"


def get_status_for_context(context: SlotContext) -> SlotStatus:
    """Assemble current status for a tenant slot."""
    appliance_containers = list_service_containers(context, VPN_SERVICE_NAME)
    worker_containers = list_service_containers(context, VPN_WORKER_SERVICE)
    vpn_id = next((str(container["id"]) for container in appliance_containers if container["running"]), None)
    customer = context.customer
    tunnel_interface = None
    profile = host_slot_profile(context)
    host_slot_exists = context.slug in load_host_slot_state().get("slots", {})
    host_vpn_running = False
    if host_slot_exists:
        host_vpn_running = host_secure_client_is_connected(context)
        tunnel_interface = "cisco-secure-client" if host_vpn_running else None

    if vpn_id:
        customer = get_env_var(vpn_id, "CUSTOMER") or context.customer
        tunnel_interface = check_tunnel_interface(vpn_id)

    workers = [
        WorkerStatus(
            index=int(container["index"]),
            name=f"{context.worker_name_prefix}-{int(container['index']):02d}",
            container_name=str(container["name"]),
            running=bool(container["running"]),
            status="up" if bool(container["running"]) else "failed",
        )
        for container in worker_containers
    ]
    desired_workers = len(worker_containers)
    running_workers = sum(1 for worker in workers if worker.running)
    vpn_running = vpn_id is not None or host_vpn_running

    return SlotStatus(
        customer=customer,
        slot=context.slug,
        queue_name=context.queue_name,
        project_name=context.project_name,
        source_of_truth="vault",
        vpn_type=profile.vpn_type if host_slot_exists else None,
        vpn_client=profile.vpn_client if host_slot_exists else None,
        client_runtime=profile.client_runtime if host_slot_exists else None,
        worker_network_mode=profile.worker_network_mode if host_slot_exists else None,
        desired_workers=desired_workers,
        running_workers=running_workers,
        status=slot_state(
            appliance_exists=bool(appliance_containers) or host_slot_exists,
            vpn_running=vpn_running,
            desired_workers=desired_workers,
            running_workers=running_workers,
        ),
        vpn_running=vpn_running,
        worker_running=running_workers > 0,
        tunnel_interface=tunnel_interface,
        workers=workers,
    )


def _discover_running_contexts() -> list[SlotContext]:
    """Discover currently running VPN appliance slots from container labels."""
    contexts_by_slot = {context.slug: context for context in host_slot_contexts()}
    try:
        result = run_command(
            [
                "docker",
                "ps",
                "--filter",
                "label=vpn.controlled=true",
                "--filter",
                "label=vpn.role=appliance",
                "--format",
                "{{.Label \"vpn.customer\"}}|{{.Label \"vpn.slot\"}}|{{.Label \"vpn.queue\"}}|{{.Label \"com.docker.compose.project\"}}|{{.Names}}",
            ],
        )
    except subprocess.CalledProcessError:
        return list(contexts_by_slot.values())

    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        customer, slot, _queue_name, project_name, _vpn_container_name = line.split("|", 4)
        contexts_by_slot[slot] = (
            SlotContext(
                customer=customer,
                slug=slot,
                queue_name=f"vpn-{slot}",
                project_name=project_name or f"{VPN_COMPOSE_PROJECT_PREFIX}-{slot}",
                worker_name_prefix=f"{VPN_WORKER_NAME_PREFIX}-{VPN_NODE_NAME}-{slot}",
            )
        )
    return list(contexts_by_slot.values())


def get_status(customer: Optional[str] = None) -> StatusResponse:
    """Return either a single-slot status or an aggregate view."""
    if customer:
        slot = get_status_for_context(slot_context(customer))
        return StatusResponse(
            vpn_running=slot.vpn_running,
            customer=slot.customer,
            tunnel_interface=slot.tunnel_interface,
            worker_running=slot.worker_running,
            slots=[slot],
        )

    slots = [get_status_for_context(context) for context in _discover_running_contexts()]
    if len(slots) == 1:
        slot = slots[0]
        return StatusResponse(
            vpn_running=slot.vpn_running,
            customer=slot.customer,
            tunnel_interface=slot.tunnel_interface,
            worker_running=slot.worker_running,
            slots=slots,
        )

    return StatusResponse(
        vpn_running=any(slot.vpn_running for slot in slots),
        customer=None,
        tunnel_interface=None,
        worker_running=any(slot.worker_running for slot in slots),
        slots=slots,
    )


def ensure_worker_scale(
    context: SlotContext,
    *,
    desired_workers: int,
    passthrough: Optional[str] = None,
    worker_compose_file: Optional[str] = None,
) -> None:
    """Ensure the tenant-specific dedicated worker pool matches the desired scale."""
    desired_workers = max(1, desired_workers)
    env = slot_env(context, passthrough=passthrough)
    queue_compose_file = worker_compose_file or VPN_QUEUE_COMPOSE_FILE
    try:
        run_command(
            compose_command(
                context,
                [VPN_SERVICE_COMPOSE_FILE, queue_compose_file],
                [
                    "up",
                    "-d",
                    "--no-deps",
                    "--force-recreate",
                    "--scale",
                    f"{VPN_WORKER_SERVICE}={desired_workers}",
                    VPN_WORKER_SERVICE,
                ],
            ),
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to scale dedicated worker pool",
                "stdout": exc.stdout,
                "stderr": exc.stderr,
            },
        ) from exc


def resolve_stop_context(customer: Optional[str]) -> SlotContext:
    """Resolve which slot to stop when a customer was or was not provided."""
    if customer:
        return slot_context(customer)

    running = [slot for slot in _discover_running_contexts() if slot.customer]
    if len(running) == 1:
        return running[0]
    if not running:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No running VPN slots found")
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Multiple VPN slots are running; provide a customer to stop a specific slot.",
    )


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="VPN Control API",
    description="HTTP interface for controlling tenant-scoped vpn.sh from Nautobot jobs.",
    version="0.2.0",
)


@app.get("/healthz", dependencies=[Depends(require_api_key)])
def healthz() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "ok"})


@app.get("/slots", response_model=list[SlotStatus], dependencies=[Depends(require_api_key)])
def slots_endpoint() -> list[SlotStatus]:
    """Return all currently running tenant slots."""
    return [get_status_for_context(context) for context in _discover_running_contexts()]


@app.get("/status", response_model=StatusResponse, dependencies=[Depends(require_api_key)])
def status_endpoint(customer: Optional[str] = Query(default=None)) -> StatusResponse:
    """Return current VPN connection status for one customer or an aggregate view."""
    return get_status(customer=customer)


@app.get("/remote-workers", response_model=list[RemoteWorkerStatus], dependencies=[Depends(require_api_key)])
def remote_workers_endpoint() -> list[RemoteWorkerStatus]:
    """Return registered remote workers and their desired/current queue state."""
    return list_remote_workers()


@app.post("/remote-workers/register", response_model=RemoteWorkerStatus, dependencies=[Depends(require_api_key)])
def remote_worker_register_endpoint(payload: RemoteWorkerRegisterRequest) -> RemoteWorkerStatus:
    """Register a remote worker and return its desired queue assignment."""
    return upsert_remote_worker(
        payload.worker_id,
        hostname=payload.hostname,
        software_version=payload.software_version,
        platform=payload.platform,
        capabilities=payload.capabilities,
        advertised_queues=payload.advertised_queues,
        current_queues=payload.current_queues,
        status_value=payload.status,
    )


@app.post(
    "/remote-workers/{worker_id}/heartbeat",
    response_model=RemoteWorkerStatus,
    dependencies=[Depends(require_api_key)],
)
def remote_worker_heartbeat_endpoint(worker_id: str, payload: RemoteWorkerHeartbeatRequest) -> RemoteWorkerStatus:
    """Refresh remote worker heartbeat and return the desired queue assignment."""
    return upsert_remote_worker(
        worker_id,
        hostname=payload.hostname,
        software_version=payload.software_version,
        platform=payload.platform,
        capabilities=payload.capabilities,
        advertised_queues=payload.advertised_queues,
        current_queues=payload.current_queues,
        status_value=payload.status,
    )


@app.post(
    "/remote-workers/{worker_id}/assignment",
    response_model=RemoteWorkerStatus,
    dependencies=[Depends(require_api_key)],
)
def remote_worker_assignment_endpoint(worker_id: str, payload: RemoteWorkerAssignmentRequest) -> RemoteWorkerStatus:
    """Update the desired queue assignment for one remote worker."""
    return set_remote_worker_assignment(worker_id, payload.desired_queues)


@app.post("/start", response_model=StatusResponse, dependencies=[Depends(require_api_key)])
def start_endpoint(payload: StartRequest) -> StatusResponse:
    """Ensure VPN is connected for the given customer / tenant slot."""
    context = slot_context(payload.customer)
    status_before = get_status_for_context(context)
    env = slot_env(context, passthrough=payload.passthrough)
    profile = resolve_vpn_profile(
        context,
        env=env,
        overrides={
            "vpn_type": payload.vpn_type,
            "vpn_client": payload.vpn_client,
            "profile_name": payload.profile_name,
            "usergroup": payload.usergroup,
            "client_runtime": payload.client_runtime,
            "worker_network_mode": payload.worker_network_mode,
        },
    )
    worker_compose_file = VPN_HOST_QUEUE_COMPOSE_FILE if profile.worker_network_mode == "host" else VPN_QUEUE_COMPOSE_FILE

    if status_before.vpn_running:
        ensure_worker_scale(
            context,
            desired_workers=payload.worker_count or max(status_before.desired_workers, 1),
            passthrough=payload.passthrough,
            worker_compose_file=worker_compose_file,
        )
        return get_status(customer=context.customer)

    if profile.vpn_type == "cisco-anyconnect" and profile.vpn_client == "cisco-secure-client":
        if profile.client_runtime != "host":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cisco-secure-client currently requires client_runtime=host.",
            )
        active_host_slots = [
            host_context
            for host_context in host_slot_contexts()
            if host_context.slug != context.slug and host_secure_client_is_connected(host_context)
        ]
        if active_host_slots:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A host Cisco Secure Client slot is already active on this node.",
            )
        start_host_secure_client(context, profile, banner_response=payload.banner_response, env=env)
        ensure_worker_scale(
            context,
            desired_workers=payload.worker_count or 1,
            passthrough=payload.passthrough,
            worker_compose_file=worker_compose_file,
        )
        return get_status(customer=context.customer)

    cmd = ["bash", str(VPN_SCRIPT), "start", context.customer]
    if payload.otp:
        cmd.extend(["--otp", payload.otp])
    if payload.authgroup:
        cmd.extend(["--authgroup", payload.authgroup])
    if profile.profile_name:
        cmd.extend(["--profile-name", profile.profile_name])
    if profile.usergroup:
        cmd.extend(["--usergroup", profile.usergroup])
    if payload.banner_response:
        cmd.extend(["--banner-response", payload.banner_response])
    if payload.extra_args:
        cmd.extend(["--extra-args", payload.extra_args])

    try:
        run_command(cmd, env=env)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "vpn.sh start failed", "stdout": exc.stdout, "stderr": exc.stderr},
        ) from exc

    ensure_worker_scale(
        context,
        desired_workers=payload.worker_count or 1,
        passthrough=payload.passthrough,
        worker_compose_file=worker_compose_file,
    )
    return get_status(customer=context.customer)


def _perform_stop(customer: Optional[str]) -> StopResponse:
    context = resolve_stop_context(customer)
    host_slot_exists = context.slug in load_host_slot_state().get("slots", {})
    try:
        if host_slot_exists:
            stop_host_secure_client(context, env=slot_env(context))
            run_command(
                compose_command(context, [VPN_SERVICE_COMPOSE_FILE, VPN_HOST_QUEUE_COMPOSE_FILE], ["rm", "-sf", VPN_WORKER_SERVICE]),
                env=slot_env(context),
            )
        else:
            run_command(["bash", str(VPN_SCRIPT), "stop"], env=slot_env(context))
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "vpn.sh stop failed", "stdout": exc.stdout, "stderr": exc.stderr},
        ) from exc
    return StopResponse(status="stopped", customer=context.customer, slot=context.slug)


@app.post("/stop", response_model=StopResponse, dependencies=[Depends(require_api_key)])
def stop_endpoint(payload: StopRequest) -> StopResponse:
    """Stop a specific tenant VPN slot, or the only running slot when unambiguous."""
    return _perform_stop(payload.customer)


@app.post("/restart", response_model=StatusResponse, dependencies=[Depends(require_api_key)])
def restart_endpoint(payload: StartRequest) -> StatusResponse:
    """Restart one tenant slot with the supplied overrides."""
    context = slot_context(payload.customer)
    try:
        _perform_stop(context.customer)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND:
            raise
    return start_endpoint(payload)


@app.post("/scale", response_model=StatusResponse, dependencies=[Depends(require_api_key)])
def scale_endpoint(payload: ScaleRequest) -> StatusResponse:
    """Resize the dedicated worker pool for a running tenant slot."""
    context = slot_context(payload.customer)
    status_before = get_status_for_context(context)
    if not status_before.vpn_running:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot scale workers because the tenant VPN is not running.",
        )
    ensure_worker_scale(context, desired_workers=payload.worker_count)
    return get_status(customer=context.customer)


@app.get("/stop", response_model=StopResponse, dependencies=[Depends(require_api_key)])
def stop_endpoint_get(customer: Optional[str] = Query(default=None)) -> StopResponse:
    """GET fallback for legacy callers."""
    return _perform_stop(customer)
