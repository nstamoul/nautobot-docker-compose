from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_NAME = "vpn.VPN_Control_API.app"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def app_module(monkeypatch, tmp_path):
    monkeypatch.setenv("VPN_PROJECT_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("VPN_REMOTE_WORKER_STATE_FILE", str(tmp_path / "remote-workers.json"))
    monkeypatch.setenv("VPN_CONTROL_API_KEY", "test-key")
    sys.modules.pop(MODULE_NAME, None)
    module = importlib.import_module(MODULE_NAME)
    return importlib.reload(module)


def test_cisco_anyconnect_defaults_to_openconnect_when_vpn_client_metadata_is_missing(app_module, monkeypatch):
    def fake_run_command(cmd, *, env=None, check=True, capture=True):
        if cmd[:4] == ["vault", "kv", "metadata", "get"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    {
                        "data": {
                            "custom_metadata": {
                                "vpn_type": "cisco-anyconnect",
                                "host": "vpn.example.test",
                                "port": "443",
                            }
                        }
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(app_module, "run_command", fake_run_command)

    profile = app_module.resolve_vpn_profile(app_module.slot_context("Example"), env={})

    assert profile.vpn_type == "cisco-anyconnect"
    assert profile.vpn_client == "openconnect"


def test_start_endpoint_passes_official_client_to_container_vpn_wrapper(app_module, monkeypatch):
    context = app_module.slot_context("e-Trikala")
    calls = {"run_command": [], "worker_scale": []}
    down_status = app_module.SlotStatus(
        customer=context.customer,
        slot=context.slug,
        queue_name=context.queue_name,
        project_name=context.project_name,
        status="down",
        vpn_running=False,
        worker_running=False,
    )

    def fake_resolve_vpn_profile(context, *, env=None, overrides=None):
        return app_module.VpnProfile(
            vpn_type="cisco-anyconnect",
            vpn_client="cisco-secure-client",
            host="stadium-wifi-wired-tnknwjndbr.dynamic-m.com",
            port="443",
            profile_name="e-Trikala VPN Profile Admins",
            usergroup="RAVPN_Admins",
        )

    def fake_run_command(cmd, *, env=None, check=True, capture=True):
        calls["run_command"].append((cmd, env))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def fake_ensure_worker_scale(context, *, desired_workers, passthrough=None):
        calls["worker_scale"].append((context, desired_workers, passthrough))

    def fake_get_status(customer=None):
        return app_module.StatusResponse(
            vpn_running=True,
            customer=context.customer,
            tunnel_interface="tun0",
            worker_running=True,
            slots=[],
        )

    monkeypatch.setattr(app_module, "get_status_for_context", lambda ctx: down_status)
    monkeypatch.setattr(app_module, "get_status", fake_get_status)
    monkeypatch.setattr(app_module, "resolve_vpn_profile", fake_resolve_vpn_profile)
    monkeypatch.setattr(app_module, "run_command", fake_run_command)
    monkeypatch.setattr(app_module, "ensure_worker_scale", fake_ensure_worker_scale)

    result = app_module.start_endpoint(
        app_module.StartRequest(customer="e-Trikala", worker_count=2, banner_response="yes")
    )

    assert result.vpn_running is True
    cmd, env = calls["run_command"][0]
    assert cmd == [
        "bash",
        str(app_module.VPN_SCRIPT),
        "start",
        "e-Trikala",
        "--vpn-client",
        "cisco-secure-client",
        "--profile-name",
        "e-Trikala VPN Profile Admins",
        "--usergroup",
        "RAVPN_Admins",
        "--banner-response",
        "yes",
    ]
    assert env["VPN_CLIENT"] == "cisco-secure-client"
    assert env["CISCO_PROFILE_NAME"] == "e-Trikala VPN Profile Admins"
    assert env["CISCO_USERGROUP"] == "RAVPN_Admins"
    assert calls["worker_scale"] == [(context, 2, None)]
