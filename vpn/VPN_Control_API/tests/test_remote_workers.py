from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_NAME = "vpn.VPN_Control_API.app"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def app_module(monkeypatch, tmp_path):
    monkeypatch.setenv("VPN_PROJECT_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("VPN_REMOTE_WORKER_STATE_FILE", str(tmp_path / "remote-workers.json"))
    monkeypatch.setenv("VPN_REMOTE_WORKER_STALE_SECONDS", "60")
    monkeypatch.setenv("VPN_CONTROL_API_KEY", "test-key")
    sys.modules.pop(MODULE_NAME, None)
    module = importlib.import_module(MODULE_NAME)
    return importlib.reload(module)


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


@pytest.fixture
def headers():
    return {"X-VPN-Control": "test-key"}


def test_remote_worker_registration_assignment_and_heartbeat(client, headers):
    register_payload = {
        "worker_id": "tech-laptop-01",
        "hostname": "tech-laptop-01",
        "software_version": "3.0.4",
        "platform": "docker-compose",
        "capabilities": {"vpn_type": "wireguard", "self_restart": True},
        "advertised_queues": ["remote-worker-acme", "remote-worker-generic"],
        "current_queues": [],
        "status": "starting",
    }

    response = client.post("/remote-workers/register", json=register_payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["assignment_status"] == "unassigned"
    assert response.json()["desired_queues"] == []

    response = client.post(
        "/remote-workers/tech-laptop-01/assignment",
        json={"desired_queues": ["remote-worker-acme"]},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["assignment_status"] == "pending-restart"
    assert response.json()["desired_queues"] == ["remote-worker-acme"]

    heartbeat_response = client.post(
        "/remote-workers/tech-laptop-01/heartbeat",
        json={"current_queues": [], "status": "starting"},
        headers=headers,
    )
    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["desired_queues"] == ["remote-worker-acme"]
    assert heartbeat_response.json()["assignment_status"] == "pending-restart"

    active_response = client.post(
        "/remote-workers/tech-laptop-01/heartbeat",
        json={"current_queues": ["remote-worker-acme"], "status": "up"},
        headers=headers,
    )
    assert active_response.status_code == 200
    assert active_response.json()["assignment_status"] == "assigned"
    assert active_response.json()["needs_restart"] is False


def test_remote_worker_list_marks_stale_records(client, headers, app_module):
    response = client.post(
        "/remote-workers/register",
        json={
            "worker_id": "pi-worker-01",
            "hostname": "pi-worker-01",
            "platform": "docker-compose",
            "current_queues": ["remote-worker-generic"],
            "status": "up",
        },
        headers=headers,
    )
    assert response.status_code == 200

    state_path = Path(app_module.REMOTE_WORKER_STATE_FILE)
    state = json.loads(state_path.read_text())
    state["workers"]["pi-worker-01"]["last_heartbeat"] = "2000-01-01T00:00:00Z"
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True))

    response = client.get("/remote-workers", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    worker = response.json()[0]
    assert worker["worker_id"] == "pi-worker-01"
    assert worker["stale"] is True
    assert worker["assignment_status"] == "stale"


def test_assignment_rejects_unadvertised_queues(client, headers):
    response = client.post(
        "/remote-workers/register",
        json={
            "worker_id": "field-pi-01",
            "hostname": "field-pi-01",
            "advertised_queues": ["remote-worker-generic"],
        },
        headers=headers,
    )
    assert response.status_code == 200

    response = client.post(
        "/remote-workers/field-pi-01/assignment",
        json={"desired_queues": ["remote-worker-acme"]},
        headers=headers,
    )
    assert response.status_code == 400
    assert "advertised" in response.json()["detail"]


def test_remote_worker_legacy_vpn_assignment_is_canonicalized_to_remote_worker(client, headers):
    response = client.post(
        "/remote-workers/register",
        json={
            "worker_id": "legacy-laptop-01",
            "hostname": "legacy-laptop-01",
            "advertised_queues": ["vpn-e-trikala", "vpn-generic"],
            "current_queues": ["vpn-e-trikala"],
            "status": "up",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["advertised_queues"] == [
        "remote-worker-e-trikala",
        "remote-worker-generic",
    ]
    assert response.json()["current_queues"] == ["vpn-e-trikala"]

    response = client.post(
        "/remote-workers/legacy-laptop-01/assignment",
        json={"desired_queues": ["vpn-e-trikala"]},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["desired_queues"] == ["remote-worker-e-trikala"]
    assert response.json()["current_queues"] == ["vpn-e-trikala"]
    assert response.json()["assignment_status"] == "pending-restart"
    assert response.json()["needs_restart"] is True

    response = client.post(
        "/remote-workers/legacy-laptop-01/heartbeat",
        json={"current_queues": ["remote-worker-e-trikala"], "status": "up"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["assignment_status"] == "assigned"
    assert response.json()["needs_restart"] is False


def test_remote_worker_rejects_server_side_vpn_queue_without_tenant_slug(client, headers):
    response = client.post(
        "/remote-workers/register",
        json={
            "worker_id": "bad-worker-01",
            "hostname": "bad-worker-01",
            "advertised_queues": ["vpn"],
        },
        headers=headers,
    )
    assert response.status_code == 400
