from datetime import datetime, timezone

from nautobot_vpn_manager.piconfig_client import (
    PiconfigClient,
    PiconfigClientConfig,
    normalize_worker_payload,
    queue_names_for_tenant_slugs,
    tenant_slugs_from_assignment_input,
)


def test_normalize_worker_payload_exposes_piconfig_assignment_as_dashboard_worker():
    worker = normalize_worker_payload(
        {
            "hostname": "RPiNo18",
            "worker_kind": "rpi",
            "celery_node_name": "worker1@RPiNo18",
            "ip_address": "10.10.10.18",
            "version": "2026.04.24",
            "last_seen": "2026-04-24T09:30:00Z",
            "first_seen": "2026-04-23T20:00:00Z",
            "tenant_slugs": ["acme", "dodoni"],
            "assignment_version": 7,
            "assignment_updated_at": "2026-04-24T09:00:00Z",
            "is_enabled": True,
        },
        now=datetime(2026, 4, 24, 9, 35, tzinfo=timezone.utc),
    )

    assert worker["worker_id"] == "RPiNo18"
    assert worker["hostname"] == "RPiNo18"
    assert worker["celery_node_name"] == "worker1@RPiNo18"
    assert worker["ip_address"] == "10.10.10.18"
    assert worker["platform"] == "rpi"
    assert worker["software_version"] == "2026.04.24"
    assert worker["last_heartbeat"] == "2026-04-24T09:30:00Z"
    assert worker["heartbeat_age_seconds"] == 300
    assert worker["status"] == "online"
    assert worker["is_online"] is True
    assert worker["registered_at"] == "2026-04-23T20:00:00Z"
    assert worker["assignment_status"] == "assigned"
    assert worker["desired_queues"] == ["remote-worker-acme", "remote-worker-dodoni"]
    assert worker["current_queues"] == ["remote-worker-acme", "remote-worker-dodoni"]
    assert worker["tenant_slugs"] == ["acme", "dodoni"]
    assert worker["assignment_version"] == 7
    assert worker["last_assignment"] == "2026-04-24T09:00:00Z"
    assert worker["needs_restart"] is False
    assert worker["stale"] is False


def test_normalize_worker_payload_marks_enabled_worker_offline_after_heartbeat_ttl():
    worker = normalize_worker_payload(
        {
            "hostname": "RPiNo19",
            "last_seen": "2026-04-24T09:00:00Z",
            "is_enabled": True,
        },
        now=datetime(2026, 4, 24, 9, 20, tzinfo=timezone.utc),
        online_ttl_seconds=900,
    )

    assert worker["heartbeat_age_seconds"] == 1200
    assert worker["status"] == "offline"
    assert worker["is_online"] is False
    assert worker["stale"] is True


def test_assignment_input_accepts_tenant_slugs_remote_worker_queues_and_legacy_vpn_queue_names():
    assert tenant_slugs_from_assignment_input(
        "remote-worker-acme, dodoni, vpn-acme, remote-worker-acme"
    ) == ["acme", "dodoni"]
    assert queue_names_for_tenant_slugs(["dodoni", "vpn-acme"]) == [
        "remote-worker-dodoni",
        "remote-worker-acme",
    ]


def test_piconfig_client_uses_mtls_service_endpoint_for_assignment(monkeypatch):
    calls = []

    class Response:
        ok = True

        def json(self):
            return {
                "hostname": "RPiNo18",
                "tenant_slugs": ["acme"],
                "assignment_version": 3,
                "assignment_updated_at": "2026-04-24T09:00:00Z",
            }

    class Session:
        trust_env = True

        def request(self, **kwargs):
            calls.append((self.trust_env, kwargs))
            return Response()

    monkeypatch.setattr("requests.Session", Session)

    client = PiconfigClient(
        PiconfigClientConfig(
            base_url="https://piconfig.example",
            client_cert="/certs/nautobot.crt",
            client_key="/certs/nautobot.key",
            ca_bundle="/certs/ca.pem",
            timeout=12,
        )
    )

    worker = client.set_worker_tenants("RPiNo18", ["acme"])

    trust_env, kwargs = calls[0]
    assert trust_env is False
    assert kwargs["method"] == "PUT"
    assert kwargs["url"] == "https://piconfig.example/api/integrations/nautobot/v1/workers/RPiNo18/tenants/"
    assert kwargs["json"] == {"tenant_slugs": ["acme"]}
    assert kwargs["cert"] == ("/certs/nautobot.crt", "/certs/nautobot.key")
    assert kwargs["verify"] == "/certs/ca.pem"
    assert kwargs["timeout"] == 12
    assert worker["desired_queues"] == ["remote-worker-acme"]
