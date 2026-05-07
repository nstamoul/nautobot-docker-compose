"""Pure row actions for the online connectivity matrix."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any


HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def swap_plan_endpoints(plan: Any) -> Any:
    """Swap endpoint A and B fields on a mutable connection plan-like object."""
    pairs = (
        ("device_a", "device_b"),
        ("device_a_name", "device_b_name"),
        ("interface_a", "interface_b"),
        ("interface_a_name", "interface_b_name"),
        ("sfp_a", "sfp_b"),
    )
    for left, right in pairs:
        left_value = getattr(plan, left, None)
        setattr(plan, left, getattr(plan, right, None))
        setattr(plan, right, left_value)
    return plan


def normalize_row_color(value: str | None) -> str:
    """Return a normalized `#rrggbb` color or an empty string."""
    if not value:
        return ""
    color = str(value).strip()
    if not HEX_COLOR_RE.match(color):
        raise ValueError("Row color must be an empty value or a six-character hex color")
    if not color.startswith("#"):
        color = f"#{color}"
    return color.lower()


def reorder_rows(rows: Iterable[Any], ordered_ids: Sequence[str]) -> list[Any]:
    """Apply dense 10-based row order values to rows listed by ID."""
    order_map = {str(row_id): (index + 1) * 10 for index, row_id in enumerate(ordered_ids)}
    updated = []
    for row in rows:
        row_id = str(getattr(row, "id"))
        if row_id in order_map:
            row.row_order = order_map[row_id]
            updated.append(row)
    return updated
