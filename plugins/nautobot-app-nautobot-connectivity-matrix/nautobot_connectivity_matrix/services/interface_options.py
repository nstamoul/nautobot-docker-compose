"""Helpers for constrained interface option selection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


CLOSED_PLAN_STATUSES = frozenset({"executed", "failed"})
EXCLUDED_INTERFACE_TYPES = frozenset({"virtual", "lag", "bridge"})


def collect_reserved_interface_ids(plan_rows: Iterable[Mapping[str, Any]]) -> set[Any]:
    """Return interface IDs reserved by non-closed connection plan rows."""
    reserved = set()
    for row in plan_rows:
        if row.get("status") in CLOSED_PLAN_STATUSES:
            continue
        for field_name in ("interface_a_id", "interface_b_id"):
            interface_id = row.get(field_name)
            if interface_id:
                reserved.add(interface_id)
    return reserved
