"""Views for the VPN manager app."""

from __future__ import annotations

import re
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView
from nautobot.tenancy.models import Tenant

from nautobot_vpn_manager.forms import VpnStartForm


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


class VpnApiError(RuntimeError):
    """Normalized VPN control API error."""


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


def _split_queue_csv(raw_value: str) -> list[str]:
    return [queue_name.strip() for queue_name in (raw_value or "").split(",") if queue_name.strip()]


class VpnDashboardView(LoginRequiredMixin, TemplateView):
    """Render the SHMS VPN control dashboard."""

    template_name = "nautobot_vpn_manager/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs.get("form") or VpnStartForm()
        status = None
        slots = []
        error_message = None
        remote_workers = []
        remote_worker_error = None

        try:
            status = _api_request("GET", "/status")
            slots = status.get("slots", [])
        except Exception as exc:  # pragma: no cover - live API failure path
            error_message = str(exc)

        try:
            remote_workers = _api_request("GET", "/remote-workers")
        except Exception as exc:  # pragma: no cover - live API failure path
            remote_worker_error = str(exc)

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
                "remote_workers": remote_workers,
                "remote_worker_error": remote_worker_error,
            }
        )
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
            desired_queues = _split_queue_csv(request.POST.get("desired_queues") or "")
            try:
                result = _api_request(
                    "POST",
                    f"/remote-workers/{worker_id}/assignment",
                    {"desired_queues": desired_queues},
                )
                queue_summary = ", ".join(result.get("desired_queues") or []) or "no queues"
                messages.success(
                    request,
                    f"Updated remote worker {result.get('worker_id') or worker_id} assignment to {queue_summary}.",
                )
            except Exception as exc:  # pragma: no cover - live API failure path
                messages.error(request, f"Failed to update remote worker assignment: {exc}")
            return redirect("plugins:nautobot_vpn_manager:dashboard")

        messages.error(request, "Unsupported VPN action.")
        return redirect("plugins:nautobot_vpn_manager:dashboard")
