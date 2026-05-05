"""Views for the VPN manager app."""

from __future__ import annotations

import re
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView
from nautobot.tenancy.models import Tenant

from nautobot_vpn_manager.forms import VpnStartForm
from nautobot_vpn_manager.piconfig_client import (
    PiconfigClient,
    PiconfigClientConfig,
    queue_names_for_tenant_slugs,
    tenant_slugs_from_assignment_input,
)
from nautobot_vpn_manager.worker_inventory import (
    annotate_worker_drift,
    celery_active_queues_by_node,
    filter_remote_workers,
    find_remote_worker,
    vpn_queue_set,
)


def _plugin_settings() -> dict:
    return settings.PLUGINS_CONFIG.get("nautobot_vpn_manager", {})


def _api_base_url() -> str:
    return _plugin_settings().get("control_api_url", "http://vpn-control-api:5001").rstrip("/")


def _api_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = _plugin_settings().get("control_api_key", "")
    if api_key:
        headers["X-VPN-Control"] = api_key
    return headers


def _api_timeout() -> int:
    return int(_plugin_settings().get("request_timeout_seconds", 30))


def _split_csv(raw_value: str) -> list[str]:
    return [item.strip() for item in (raw_value or "").split(",") if item.strip()]


def _node_hostname(node_name: str) -> str:
    if "@" in node_name:
        return node_name.rsplit("@", 1)[-1].strip().lower()
    return node_name.strip().lower()


def _hostname_keys(value: str) -> set[str]:
    hostname = (value or "").strip().lower()
    if not hostname:
        return set()
    keys = {hostname}
    if "." in hostname:
        keys.add(hostname.split(".", 1)[0])
    return keys


def _is_enabled(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _piconfig_client() -> PiconfigClient:
    plugin_settings = _plugin_settings()
    return PiconfigClient(
        PiconfigClientConfig(
            base_url=plugin_settings.get("piconfig_api_url", ""),
            client_cert=plugin_settings.get("piconfig_client_cert", ""),
            client_key=plugin_settings.get("piconfig_client_key", ""),
            ca_bundle=plugin_settings.get("piconfig_ca_bundle", ""),
            verify=_is_enabled(plugin_settings.get("piconfig_verify_tls", True)),
            timeout=_api_timeout(),
        )
    )


class VpnApiError(RuntimeError):
    """Normalized VPN control API error."""


class VpnLiveSteeringError(RuntimeError):
    """Raised when Celery live steering cannot be completed."""


ACTIVE_SLOT_STATUSES = {"up", "starting", "failed"}


def _slot_slug(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value


def _api_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    detail = payload.get("detail")
    if isinstance(detail, dict):
        message = detail.get("message") or response.text
        stderr = (detail.get("stderr") or "").strip()
        stdout = (detail.get("stdout") or "").strip()
        extras = []
        if stderr:
            extras.append(stderr)
        elif stdout:
            extras.append(stdout)
        if extras:
            return f"{message}: {' | '.join(extras)}"
        return str(message)
    if detail:
        return str(detail)
    return response.text or f"{response.status_code} {response.reason}"


def _api_request(method: str, path: str, payload: dict | None = None) -> dict:
    session = requests.Session()
    session.trust_env = False
    response = session.request(
        method=method,
        url=f"{_api_base_url()}{path}",
        headers=_api_headers(),
        json=payload,
        timeout=_api_timeout(),
    )
    if not response.ok:
        raise VpnApiError(_api_error_message(response))
    return response.json()


def _steer_remote_worker_queues(celery_node_name: str, desired_queues: list[str], previous_queues: list[str]) -> None:
    """Apply best-effort live Celery queue steering for an online worker."""

    if not celery_node_name:
        raise VpnLiveSteeringError("worker has no Celery node name; assignment will apply on next worker check-in")

    from celery import current_app  # Imported lazily so tests can exercise pure helpers without Celery settings.

    destination = [celery_node_name]
    desired = vpn_queue_set(desired_queues, include_generic=False)
    previous = vpn_queue_set(previous_queues, include_generic=True)
    replies = []

    for queue_name in sorted(desired):
        replies.extend(current_app.control.add_consumer(queue_name, destination=destination, reply=True, timeout=5) or [])

    for queue_name in sorted(previous - desired):
        replies.extend(current_app.control.cancel_consumer(queue_name, destination=destination, reply=True, timeout=5) or [])

    if (desired or previous) and not replies:
        raise VpnLiveSteeringError("Celery control did not receive a reply from the worker")


def _active_queues_by_celery_node() -> tuple[dict[str, list[str]], str | None]:
    """Return live worker queues from Celery if the control plane is reachable."""

    try:
        from celery import current_app
    except Exception as exc:  # pragma: no cover - broker/config availability varies by deployment.
        return {}, str(exc)
    return celery_active_queues_by_node(current_app, timeout=2, attempts=2)


def _celery_worker_runtime() -> tuple[dict, str | None]:
    """Return live Celery worker nodes, queues, and hostname mapping."""

    queues_by_node, error = _active_queues_by_celery_node()
    node_names = set(queues_by_node)
    if error:
        return {"queues_by_node": queues_by_node, "node_names": node_names, "node_by_hostname": {}}, error

    node_by_hostname = {}
    for node_name in node_names:
        hostname = _node_hostname(node_name)
        for hostname_key in _hostname_keys(hostname):
            node_by_hostname.setdefault(hostname_key, node_name)

    return {"queues_by_node": queues_by_node, "node_names": node_names, "node_by_hostname": node_by_hostname}, None


def _merge_live_worker_state(workers: list[dict], runtime: dict) -> list[dict]:
    """Overlay live Celery state onto piconfig worker records."""

    queues_by_node = runtime.get("queues_by_node") or {}
    node_names = runtime.get("node_names") or set()
    node_by_hostname = runtime.get("node_by_hostname") or {}

    for worker in workers:
        worker["status_source"] = "piconfig heartbeat"
        worker["current_queues_source"] = "piconfig assignment"
        celery_node_name = worker.get("celery_node_name") or ""
        hostname = worker.get("hostname") or worker.get("worker_id") or ""
        live_node_name = None
        if celery_node_name in node_names:
            live_node_name = celery_node_name
        else:
            for hostname_key in _hostname_keys(hostname):
                live_node_name = node_by_hostname.get(hostname_key)
                if live_node_name:
                    break

        if live_node_name:
            worker["celery_node_name"] = live_node_name
            worker["status"] = "online"
            worker["is_online"] = True
            worker["stale"] = False
            worker["status_source"] = "live Celery"
            worker["current_queues"] = queues_by_node.get(live_node_name, worker.get("current_queues", []))
            worker["current_queues_source"] = "live Celery"

    return workers


def _tenant_queue_choices() -> list[dict[str, str]]:
    choices = []
    for tenant in Tenant.objects.order_by("name"):
        slug = _slot_slug(tenant.name)
        if not slug:
            continue
        choices.append({"slug": slug, "name": tenant.name, "queue": f"vpn-{slug}"})
    return choices


def _remote_worker_context(*, active_only: bool) -> dict:
    remote_workers = []
    remote_worker_error = None
    live_queue_error = None
    all_remote_worker_count = 0

    try:
        remote_workers = _piconfig_client().list_workers()
    except Exception as exc:  # pragma: no cover - live API failure path
        remote_worker_error = str(exc)

    if remote_workers:
        runtime, live_queue_error = _celery_worker_runtime()
        remote_workers = _merge_live_worker_state(remote_workers, runtime)
        remote_workers = annotate_worker_drift(remote_workers)
        all_remote_worker_count = len(remote_workers)
        if active_only:
            remote_workers = [worker for worker in remote_workers if worker.get("is_online")]

    return {
        "remote_workers": remote_workers,
        "remote_worker_error": remote_worker_error,
        "live_queue_error": live_queue_error,
        "all_remote_worker_count": all_remote_worker_count,
        "tenant_queue_choices": _tenant_queue_choices(),
    }


def _worker_filter_context(request) -> dict:
    return {
        "name": (request.GET.get("name") or "").strip(),
        "queue": [queue.strip() for queue in request.GET.getlist("queue") if queue.strip()],
        "status": [status.strip().lower() for status in request.GET.getlist("status") if status.strip()],
        "assignment_from": (request.GET.get("assignment_from") or "").strip(),
        "assignment_to": (request.GET.get("assignment_to") or "").strip(),
        "heartbeat_from": (request.GET.get("heartbeat_from") or "").strip(),
        "heartbeat_to": (request.GET.get("heartbeat_to") or "").strip(),
    }


class VpnDashboardView(LoginRequiredMixin, TemplateView):
    """Render the SHMS VPN control dashboard."""

    template_name = "nautobot_vpn_manager/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs.get("form") or VpnStartForm()
        status = None
        slots = []
        error_message = None

        try:
            status = _api_request("GET", "/status")
            slots = status.get("slots", [])
        except Exception as exc:  # pragma: no cover - live API failure path
            error_message = str(exc)

        tenant_by_slug = {_slot_slug(tenant.name): tenant.name for tenant in Tenant.objects.order_by("name")}

        inventory = []
        for slot in slots:
            slot_status = (slot.get("status") or "down").lower()
            if slot_status not in ACTIVE_SLOT_STATUSES:
                continue
            slot["tenant_name"] = tenant_by_slug.get(slot.get("slot"))
            slot["is_tenant_backed"] = slot["tenant_name"] is not None
            inventory.append(slot)

        inventory.sort(key=lambda item: (item.get("tenant_name") or item.get("customer") or "").lower())

        context.update(
            {
                "form": form,
                "status": status,
                "slots": slots,
                "inventory": inventory,
                "error_message": error_message,
            }
        )
        context.update(_remote_worker_context(active_only=True))
        return context


class VpnWorkerSteeringView(LoginRequiredMixin, TemplateView):
    """Render remote worker inventory and filters."""

    template_name = "nautobot_vpn_manager/workers.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_remote_worker_context(active_only=False))
        filters = _worker_filter_context(self.request)
        unfiltered_workers = context["remote_workers"]
        context["remote_workers"] = filter_remote_workers(unfiltered_workers, filters)
        context["worker_filters"] = filters
        context["visible_remote_worker_count"] = len(context["remote_workers"])
        context["active_remote_worker_count"] = len([worker for worker in unfiltered_workers if worker.get("is_online")])
        return context


class VpnWorkerDetailView(LoginRequiredMixin, TemplateView):
    """Render remote worker assignment management for one worker."""

    template_name = "nautobot_vpn_manager/worker_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worker_name = kwargs.get("worker_name") or ""
        context.update(_remote_worker_context(active_only=False))
        worker = find_remote_worker(context["remote_workers"], worker_name)
        if worker is None:
            raise Http404(f"Remote worker {worker_name} was not found")
        context["worker"] = worker
        context["worker_name"] = worker_name
        return context


class VpnActionView(LoginRequiredMixin, View):
    """Handle dashboard start/stop actions."""

    def post(self, request):
        action = (request.POST.get("action") or "").strip().lower()

        if action == "start":
            form = VpnStartForm(request.POST)
            if not form.is_valid():
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
                return redirect("plugins:nautobot_vpn_manager:dashboard")

            payload = {
                "customer": form.resolved_customer(),
                "worker_count": form.resolved_worker_count(),
                "otp": form.cleaned_data.get("otp") or None,
                "authgroup": form.cleaned_data.get("authgroup") or None,
                "banner_response": form.cleaned_data.get("banner_response") or None,
                "extra_args": form.cleaned_data.get("extra_args") or None,
                "passthrough": form.cleaned_data.get("passthrough") or None,
            }

            try:
                result = _api_request("POST", "/start", payload)
                messages.success(
                    request,
                    f"VPN slot for {result.get('customer') or payload['customer']} is active; "
                    f"workers={result.get('running_workers', 0)}/{result.get('desired_workers', 0)}, "
                    f"tunnel={result.get('tunnel_interface') or 'n/a'}.",
                )
            except Exception as exc:  # pragma: no cover - live API failure path
                messages.error(request, f"Failed to start VPN slot: {exc}")
            return redirect("plugins:nautobot_vpn_manager:dashboard")

        if action == "stop":
            customer = (request.POST.get("customer") or "").strip() or None
            try:
                result = _api_request("POST", "/stop", {"customer": customer})
                messages.success(
                    request,
                    f"Stopped VPN slot for {result.get('customer') or customer or 'resolved running slot'}.",
                )
            except Exception as exc:  # pragma: no cover - live API failure path
                messages.error(request, f"Failed to stop VPN slot: {exc}")
            return redirect("plugins:nautobot_vpn_manager:dashboard")

        if action == "restart":
            customer = (request.POST.get("customer") or "").strip()
            worker_count = int(request.POST.get("worker_count") or "1")
            payload = {"customer": customer, "worker_count": worker_count}
            try:
                result = _api_request("POST", "/restart", payload)
                messages.success(
                    request,
                    f"Restarted VPN slot for {result.get('customer') or customer}; "
                    f"workers={result.get('running_workers', 0)}/{result.get('desired_workers', 0)}.",
                )
            except Exception as exc:  # pragma: no cover - live API failure path
                messages.error(request, f"Failed to restart VPN slot: {exc}")
            return redirect("plugins:nautobot_vpn_manager:dashboard")

        if action == "scale":
            customer = (request.POST.get("customer") or "").strip()
            worker_count = int(request.POST.get("worker_count") or "1")
            try:
                result = _api_request(
                    "POST",
                    "/scale",
                    {"customer": customer, "worker_count": worker_count},
                )
                messages.success(
                    request,
                    f"Updated worker pool for {result.get('customer') or customer} to "
                    f"{result.get('desired_workers', worker_count)} worker(s).",
                )
            except Exception as exc:  # pragma: no cover - live API failure path
                messages.error(request, f"Failed to resize VPN worker pool: {exc}")
            return redirect("plugins:nautobot_vpn_manager:dashboard")

        if action == "assign_remote_worker":
            worker_id = (request.POST.get("worker_id") or "").strip()
            celery_node_name = (request.POST.get("celery_node_name") or "").strip()
            previous_queues = _split_csv(request.POST.get("current_queues") or "")
            next_url = request.POST.get("next") or ""
            tenant_slugs = tenant_slugs_from_assignment_input(",".join(request.POST.getlist("tenant_slugs")))
            if not tenant_slugs:
                tenant_slugs = tenant_slugs_from_assignment_input(request.POST.get("desired_queues") or "")
            try:
                result = _piconfig_client().set_worker_tenants(worker_id, tenant_slugs)
                desired_queues = result.get("desired_queues") or queue_names_for_tenant_slugs(tenant_slugs)
                queue_summary = ", ".join(desired_queues)
                queue_summary = queue_summary or "no queues"
                messages.success(
                    request,
                    f"Updated remote worker {result.get('worker_id') or worker_id} assignment to {queue_summary}.",
                )
                try:
                    _steer_remote_worker_queues(
                        result.get("celery_node_name") or celery_node_name,
                        desired_queues,
                        previous_queues,
                    )
                    messages.success(request, f"Live-steered {result.get('worker_id') or worker_id} to {queue_summary}.")
                except Exception as exc:  # pragma: no cover - live broker failure path
                    messages.warning(request, f"Assignment persisted in piconfig; live steering deferred: {exc}")
            except Exception as exc:  # pragma: no cover - live API failure path
                messages.error(request, f"Failed to update remote worker assignment: {exc}")
            if next_url.startswith("/plugins/vpn-manager/workers/"):
                return redirect(next_url)
            if worker_id:
                return redirect("plugins:nautobot_vpn_manager:worker_detail", worker_name=worker_id)
            return redirect("plugins:nautobot_vpn_manager:workers")

        messages.error(request, "Unsupported VPN action.")
        return redirect("plugins:nautobot_vpn_manager:dashboard")
