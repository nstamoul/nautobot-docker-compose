"""Pure helpers for remote worker inventory and steering views."""

from __future__ import annotations

from datetime import datetime, time, timezone
from fnmatch import fnmatchcase


def vpn_queue_set(queue_names: list[str], *, include_generic: bool) -> set[str]:
    """Return VPN queues from a live/current queue list."""

    queues = {queue for queue in queue_names if queue.startswith("vpn-")}
    if not include_generic:
        queues.discard("vpn-generic")
    return queues


def annotate_worker_drift(workers: list[dict]) -> list[dict]:
    """Annotate workers with desired-vs-live VPN queue drift state."""

    for worker in workers:
        desired = vpn_queue_set(worker.get("desired_queues") or [], include_generic=False)
        current = vpn_queue_set(worker.get("current_queues") or [], include_generic=False)
        missing = sorted(desired - current)
        unexpected = sorted(current - desired)
        has_live_current = worker.get("is_online") or worker.get("current_queues_source") == "live Celery"
        summary_parts = []

        worker["queue_drift_missing"] = missing
        worker["queue_drift_unexpected"] = unexpected
        worker["queue_drift"] = False

        if has_live_current:
            if missing or unexpected:
                worker["queue_drift"] = True
                worker["queue_drift_status"] = "drift"
                if missing:
                    summary_parts.append(f"missing {', '.join(missing)}")
                if unexpected:
                    summary_parts.append(f"unexpected {', '.join(unexpected)}")
                worker["queue_drift_summary"] = "; ".join(summary_parts)
            else:
                worker["queue_drift_status"] = "in_sync"
                worker["queue_drift_summary"] = "live queues match assignment intent"
        elif desired:
            worker["queue_drift_status"] = "deferred"
            worker["queue_drift_summary"] = "assignment will apply on next worker check-in"
        else:
            worker["queue_drift_status"] = "idle"
            worker["queue_drift_summary"] = "no tenant assignment intent"

    return workers


def celery_active_queues_by_node(celery_app, *, timeout: int = 2, attempts: int = 2) -> tuple[dict[str, list[str]], str | None]:
    """Return live Celery worker queues with a fresh connection and one retry."""

    last_error = None
    for _ in range(max(1, attempts)):
        try:
            connection_factory = getattr(celery_app, "connection_for_read", None)
            if connection_factory:
                with connection_factory() as connection:
                    active_queues = celery_app.control.inspect(timeout=timeout, connection=connection).active_queues() or {}
            else:
                active_queues = celery_app.control.inspect(timeout=timeout).active_queues() or {}
            break
        except Exception as exc:  # pragma: no cover - exact broker exceptions vary by Celery transport.
            last_error = str(exc)
    else:
        return {}, last_error

    queues_by_node: dict[str, list[str]] = {}
    for node_name, queues in active_queues.items():
        queue_names = []
        for queue in queues or []:
            if isinstance(queue, dict) and queue.get("name"):
                queue_names.append(str(queue["name"]))
        queues_by_node[str(node_name)] = sorted(set(queue_names))
    return queues_by_node, None


def _filter_values(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def parse_filter_datetime(value: str, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    value = str(value).strip()
    try:
        if len(value) == 10 and value[4] == "-" and value[7] == "-":
            date_value = datetime.fromisoformat(value).date()
            dt = datetime.combine(date_value, time.max if end_of_day else time.min, tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _worker_datetime(worker: dict, field: str) -> datetime | None:
    return parse_filter_datetime(str(worker.get(field) or ""))


def _matches_name_filter(worker: dict, raw_filter: str) -> bool:
    name_filter = (raw_filter or "").strip().lower()
    if not name_filter:
        return True
    pattern = name_filter if "*" in name_filter else f"*{name_filter}*"
    candidates = [
        worker.get("worker_id") or "",
        worker.get("hostname") or "",
        worker.get("celery_node_name") or "",
    ]
    return any(fnmatchcase(str(candidate).lower(), pattern) for candidate in candidates)


def _matches_queue_filter(worker: dict, queue_filter) -> bool:
    queue_filters = set(_filter_values(queue_filter))
    if not queue_filters:
        return True
    queues = set(worker.get("current_queues") or []) | set(worker.get("desired_queues") or [])
    return bool(queue_filters & queues)


def _matches_status_filter(worker: dict, status_filter) -> bool:
    status_filters = {status.lower() for status in _filter_values(status_filter)}
    if not status_filters:
        return True
    if "stale" in status_filters and worker.get("stale"):
        return bool(worker.get("stale"))
    return str(worker.get("status") or "").lower() in status_filters


def _matches_datetime_window(worker: dict, field: str, start: datetime | None, end: datetime | None) -> bool:
    if not start and not end:
        return True
    value = _worker_datetime(worker, field)
    if value is None:
        return False
    if start and value < start:
        return False
    if end and value > end:
        return False
    return True


def filter_remote_workers(workers: list[dict], filters: dict[str, str]) -> list[dict]:
    assignment_from = parse_filter_datetime(filters.get("assignment_from", ""))
    assignment_to = parse_filter_datetime(filters.get("assignment_to", ""), end_of_day=True)
    heartbeat_from = parse_filter_datetime(filters.get("heartbeat_from", ""))
    heartbeat_to = parse_filter_datetime(filters.get("heartbeat_to", ""), end_of_day=True)
    queue_filter = filters.get("queue", "")
    status_filter = filters.get("status", "")
    name_filter = filters.get("name", "")

    filtered = []
    for worker in workers:
        if not _matches_name_filter(worker, name_filter):
            continue
        if not _matches_queue_filter(worker, queue_filter):
            continue
        if not _matches_status_filter(worker, status_filter):
            continue
        if not _matches_datetime_window(worker, "last_assignment", assignment_from, assignment_to):
            continue
        if not _matches_datetime_window(worker, "last_heartbeat", heartbeat_from, heartbeat_to):
            continue
        filtered.append(worker)
    return filtered


def find_remote_worker(workers: list[dict], worker_name: str) -> dict | None:
    worker_name = worker_name.strip().lower()
    for worker in workers:
        if str(worker.get("worker_id") or "").lower() == worker_name:
            return worker
        if str(worker.get("hostname") or "").lower() == worker_name:
            return worker
    return None
