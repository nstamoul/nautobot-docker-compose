"""Validation for online connectivity matrix rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .interface_options import CLOSED_PLAN_STATUSES


@dataclass(frozen=True)
class ValidationResult:
    """Hard blockers and non-blocking warnings for one matrix row."""

    blockers: list[str]
    warnings: list[str]


def _read_value(row: Any, field_name: str) -> Any:
    """Read a field from a model, simple object, or dict-like row."""
    if isinstance(row, dict):
        return row.get(field_name)
    return getattr(row, field_name, None)


def _endpoint_key(device: Any, device_name: str, interface: Any, interface_name: str) -> tuple[str, str] | None:
    """Return a comparable endpoint key when both device and interface are known."""
    device_key = str(getattr(device, "id", None) or device_name or "")
    interface_key = str(getattr(interface, "id", None) or interface_name or "")
    if not device_key or not interface_key:
        return None
    return device_key, interface_key


def collect_row_reserved_interface_ids(plan_rows: Any, current_plan_id: Any | None = None) -> set[str]:
    """Return interface IDs used by other non-closed rows."""
    reserved: set[str] = set()
    current_plan_id = str(current_plan_id) if current_plan_id else None
    for row in plan_rows:
        if current_plan_id and str(_read_value(row, "id")) == current_plan_id:
            continue
        if _read_value(row, "status") in CLOSED_PLAN_STATUSES:
            continue
        for field_name in ("interface_a_id", "interface_b_id"):
            interface_id = _read_value(row, field_name)
            if interface_id:
                reserved.add(str(interface_id))
    return reserved


def validate_plan_row(plan: Any, reserved_interface_ids: set[str] | None = None) -> ValidationResult:
    """Validate one row without mutating it."""
    reserved_interface_ids = reserved_interface_ids or set()
    blockers: list[str] = []
    warnings: list[str] = []

    endpoint_a = _endpoint_key(plan.device_a, plan.device_a_name, plan.interface_a, plan.interface_a_name)
    endpoint_b = _endpoint_key(plan.device_b, plan.device_b_name, plan.interface_b, plan.interface_b_name)

    if not plan.device_a and not plan.device_a_name:
        blockers.append("Device A is required")
    if not plan.device_b and not plan.device_b_name:
        blockers.append("Device B is required")
    if not plan.interface_a and not plan.interface_a_name:
        blockers.append("Interface A is required")
    if not plan.interface_b and not plan.interface_b_name:
        blockers.append("Interface B is required")

    if endpoint_a and endpoint_a == endpoint_b:
        blockers.append("Device A/interface A and Device B/interface B are the same endpoint")

    for side, interface in (("A", plan.interface_a), ("B", plan.interface_b)):
        if interface and getattr(interface, "cable", None):
            blockers.append(f"Interface {side} is already cabled in Nautobot")
        if interface and str(getattr(interface, "id")) in reserved_interface_ids:
            blockers.append("already used in this matrix")

    if plan.device_a is None and plan.device_a_name:
        warnings.append("Device A is unresolved and will not be cabled until materialized")
    if plan.device_b is None and plan.device_b_name:
        warnings.append("Device B is unresolved and will not be cabled until materialized")

    return ValidationResult(blockers=blockers, warnings=warnings)
