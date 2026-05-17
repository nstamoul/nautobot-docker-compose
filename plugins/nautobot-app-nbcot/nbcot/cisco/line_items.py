"""Line item sorting and hierarchy helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass
class LineGroup:
    """A major order line and its minor child lines."""

    major: Any
    minor_lines: list[Any]


@dataclass
class LineTreeRow:
    """A flattened row in the Cisco line hierarchy."""

    line: Any
    row_id: str
    parent_id: str
    ancestor_ids: tuple[str, ...]
    depth: int
    has_children: bool

    @property
    def indent_px(self) -> int:
        """Return the left padding for the hierarchy cell."""
        return 8 + (self.depth * 28)


def line_number_sort_key(line_number: str | None) -> tuple[tuple[int, int | str], ...]:
    """Return a natural sort key for Cisco dotted line numbers."""
    if not line_number:
        return ((1, ""),)
    parts = []
    for part in str(line_number).split("."):
        try:
            parts.append((0, int(part)))
        except ValueError:
            parts.append((1, part))
    return tuple(parts)


def line_number_sort_value(line_number: str | None) -> str:
    """Return a stable string sort value for database ordering."""
    if not line_number:
        return ""
    values = []
    for kind, value in line_number_sort_key(line_number):
        if kind == 0:
            values.append(f"{int(value):08d}")
        else:
            values.append(f"~{value}")
    return ".".join(values)


def is_major_line(line: Any) -> bool:
    """Return True when the line is a Cisco major item."""
    return str(getattr(line, "line_number", "") or "").endswith(".0")


def major_line_number_for(line: Any) -> str:
    """Return the major line number that should own this line."""
    line_number = str(getattr(line, "line_number", "") or "")
    if is_major_line(line):
        return line_number
    first_part = line_number.split(".", maxsplit=1)[0]
    return f"{first_part}.0" if first_part else line_number


def parent_line_number_for(line_number: str | None) -> str:
    """Return the expected parent line number for Cisco's two-level hierarchy."""
    if not line_number:
        return ""
    parts = str(line_number).split(".")
    if len(parts) < 2:
        return ""
    root_number = f"{parts[0]}.0"
    if len(parts) == 2:
        return "" if parts[1] == "0" else root_number
    return root_number if parts[1] == "0" else f"{parts[0]}.{parts[1]}"


def build_line_tree(lines: Iterable[Any]) -> list[LineTreeRow]:
    """Build a flattened Cisco line hierarchy for rendering and client-side controls."""
    sorted_lines = sorted(lines, key=lambda line: line_number_sort_key(getattr(line, "line_number", "")))
    row_ids_by_line_number = {}
    row_ids_by_line = {}
    children_by_parent = {"": []}

    for index, line in enumerate(sorted_lines, start=1):
        row_id = f"nbcot-line-{index}"
        row_ids_by_line[id(line)] = row_id
        line_number = str(getattr(line, "line_number", "") or "")
        row_ids_by_line_number.setdefault(line_number, row_id)

    for line in sorted_lines:
        row_id = row_ids_by_line[id(line)]
        line_number = str(getattr(line, "line_number", "") or "")
        parent_number = parent_line_number_for(line_number)
        parent_id = row_ids_by_line_number.get(parent_number, "")
        if parent_id == row_id:
            parent_id = ""
        children_by_parent.setdefault(parent_id, []).append(line)

    rows = []

    def add_rows(parent_id: str, ancestors: tuple[str, ...], depth: int) -> None:
        child_lines = sorted(
            children_by_parent.get(parent_id, []),
            key=lambda line: line_number_sort_key(getattr(line, "line_number", "")),
        )
        for line in child_lines:
            row_id = row_ids_by_line[id(line)]
            rows.append(
                LineTreeRow(
                    line=line,
                    row_id=row_id,
                    parent_id=parent_id,
                    ancestor_ids=ancestors,
                    depth=depth,
                    has_children=bool(children_by_parent.get(row_id)),
                )
            )
            add_rows(row_id, (*ancestors, row_id), depth + 1)

    add_rows("", (), 0)
    return rows


def group_order_lines(lines: Iterable[Any]) -> list[LineGroup]:
    """Group lines into major/minor hierarchy using natural Cisco line ordering."""
    sorted_lines = sorted(lines, key=lambda line: line_number_sort_key(getattr(line, "line_number", "")))
    major_by_number = {str(getattr(line, "line_number", "") or ""): line for line in sorted_lines if is_major_line(line)}
    groups_by_number = {
        line_number: LineGroup(major=line, minor_lines=[]) for line_number, line in major_by_number.items()
    }

    for line in sorted_lines:
        if is_major_line(line):
            continue
        major_number = major_line_number_for(line)
        group = groups_by_number.get(major_number)
        if group is None:
            groups_by_number[major_number] = LineGroup(major=line, minor_lines=[])
        else:
            group.minor_lines.append(line)

    return sorted(groups_by_number.values(), key=lambda group: line_number_sort_key(getattr(group.major, "line_number", "")))
