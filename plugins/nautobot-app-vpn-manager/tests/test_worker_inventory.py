from nautobot_vpn_manager.worker_inventory import (
    annotate_worker_drift,
    celery_active_queues_by_node,
    filter_remote_workers,
    find_remote_worker,
    vpn_queue_set,
)


def test_vpn_queue_set_can_cancel_generic_from_live_current_queues():
    assert vpn_queue_set(["vpn-generic", "vpn-axepa", "celery"], include_generic=True) == {
        "vpn-generic",
        "vpn-axepa",
    }
    assert vpn_queue_set(["vpn-generic", "vpn-axepa"], include_generic=False) == {"vpn-axepa"}


def test_annotate_worker_drift_marks_online_worker_in_sync_ignoring_generic_queue():
    workers = [
        {
            "worker_id": "RPiNo18",
            "is_online": True,
            "current_queues_source": "live Celery",
            "current_queues": ["vpn-axepa", "vpn-generic"],
            "desired_queues": ["vpn-axepa"],
        }
    ]

    annotate_worker_drift(workers)

    assert workers[0]["queue_drift_status"] == "in_sync"
    assert workers[0]["queue_drift"] is False
    assert workers[0]["queue_drift_missing"] == []
    assert workers[0]["queue_drift_unexpected"] == []


def test_annotate_worker_drift_detects_online_worker_queue_mismatch():
    workers = [
        {
            "worker_id": "RPiNo18",
            "is_online": True,
            "current_queues_source": "live Celery",
            "current_queues": ["vpn-axepa"],
            "desired_queues": ["vpn-dodoni"],
        }
    ]

    annotate_worker_drift(workers)

    assert workers[0]["queue_drift_status"] == "drift"
    assert workers[0]["queue_drift"] is True
    assert workers[0]["queue_drift_missing"] == ["vpn-dodoni"]
    assert workers[0]["queue_drift_unexpected"] == ["vpn-axepa"]
    assert workers[0]["queue_drift_summary"] == "missing vpn-dodoni; unexpected vpn-axepa"


def test_annotate_worker_drift_marks_offline_assignment_as_deferred_not_drift():
    workers = [
        {
            "worker_id": "RPiNo19",
            "is_online": False,
            "current_queues_source": "piconfig assignment",
            "current_queues": ["vpn-dodoni"],
            "desired_queues": ["vpn-dodoni"],
        }
    ]

    annotate_worker_drift(workers)

    assert workers[0]["queue_drift_status"] == "deferred"
    assert workers[0]["queue_drift"] is False
    assert workers[0]["queue_drift_summary"] == "assignment will apply on next worker check-in"


def test_celery_active_queues_by_node_retries_closed_broker_connection():
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeInspector:
        def __init__(self, control):
            self.control = control

        def active_queues(self):
            self.control.calls += 1
            if self.control.calls == 1:
                raise RuntimeError("Connection closed by server")
            return {
                "worker1@RPiNo18": [
                    {"name": "vpn-axepa"},
                    {"name": "vpn-axepa"},
                    {"name": "celery"},
                ]
            }

    class FakeControl:
        def __init__(self):
            self.calls = 0
            self.connections = []

        def inspect(self, *, timeout, connection):
            self.connections.append((timeout, connection))
            return FakeInspector(self)

    class FakeCeleryApp:
        def __init__(self):
            self.control = FakeControl()

        def connection_for_read(self):
            return FakeConnection()

    queues, error = celery_active_queues_by_node(FakeCeleryApp(), timeout=2, attempts=2)

    assert error is None
    assert queues == {"worker1@RPiNo18": ["celery", "vpn-axepa"]}


def test_filter_remote_workers_matches_name_queue_status_and_datetime_windows():
    workers = [
        {
            "worker_id": "RPiNo18",
            "hostname": "RPiNo18",
            "celery_node_name": "worker1@RPiNo18",
            "status": "online",
            "stale": False,
            "current_queues": ["vpn-axepa", "vpn-generic"],
            "desired_queues": ["vpn-axepa"],
            "last_assignment": "2026-04-25T08:27:16+00:00",
            "last_heartbeat": "2026-04-25T08:27:31+00:00",
        },
        {
            "worker_id": "RPiNo17",
            "hostname": "RPiNo17",
            "status": "offline",
            "stale": True,
            "current_queues": [],
            "desired_queues": ["vpn-dodoni"],
            "last_assignment": "2026-04-24T08:00:00Z",
            "last_heartbeat": "2026-04-24T08:00:00Z",
        },
    ]

    result = filter_remote_workers(
        workers,
        {
            "name": "RPiNo1*",
            "queue": "vpn-generic",
            "status": "online",
            "assignment_from": "2026-04-25T08:00:00+00:00",
            "assignment_to": "",
            "heartbeat_from": "2026-04-25T08:20:00+00:00",
            "heartbeat_to": "",
        },
    )

    assert [worker["worker_id"] for worker in result] == ["RPiNo18"]
    assert [worker["worker_id"] for worker in filter_remote_workers(workers, {"status": "stale"})] == ["RPiNo17"]


def test_filter_remote_workers_accepts_multi_value_queue_and_status_filters():
    workers = [
        {
            "worker_id": "RPiNo18",
            "status": "online",
            "stale": False,
            "current_queues": ["vpn-axepa"],
            "desired_queues": ["vpn-axepa"],
        },
        {
            "worker_id": "RPiNo19",
            "status": "offline",
            "stale": True,
            "current_queues": ["vpn-dodoni"],
            "desired_queues": ["vpn-dodoni"],
        },
        {
            "worker_id": "RPiNo20",
            "status": "disabled",
            "stale": False,
            "current_queues": ["vpn-other"],
            "desired_queues": ["vpn-other"],
        },
    ]

    result = filter_remote_workers(workers, {"queue": ["vpn-axepa", "vpn-dodoni"], "status": ["online", "stale"]})

    assert [worker["worker_id"] for worker in result] == ["RPiNo18", "RPiNo19"]


def test_filter_remote_workers_treats_date_only_heartbeat_to_as_end_of_day():
    workers = [
        {
            "worker_id": "RPiNo18",
            "status": "online",
            "last_heartbeat": "2026-04-25T13:36:27+00:00",
        },
        {
            "worker_id": "RPiNo19",
            "status": "online",
            "last_heartbeat": "2026-04-26T00:00:00+00:00",
        },
    ]

    result = filter_remote_workers(workers, {"heartbeat_from": "2026-04-25", "heartbeat_to": "2026-04-25"})

    assert [worker["worker_id"] for worker in result] == ["RPiNo18"]


def test_find_remote_worker_accepts_worker_id_or_hostname_case_insensitively():
    workers = [
        {"worker_id": "RPiNo18", "hostname": "rpi18.local"},
        {"worker_id": "worker-vm-01", "hostname": "worker-vm-01"},
    ]

    assert find_remote_worker(workers, "rpino18") == workers[0]
    assert find_remote_worker(workers, "RPI18.LOCAL") == workers[0]
    assert find_remote_worker(workers, "missing") is None
