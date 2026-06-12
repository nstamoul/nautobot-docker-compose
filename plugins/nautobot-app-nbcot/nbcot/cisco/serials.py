"""Helpers for Cisco serial-number attribute payloads."""

from __future__ import annotations

from typing import Any, Iterable


UI_SERIAL_VALUE_LIMIT = 10


def _ensure_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text_values(value) -> list[str]:
    values = []
    for item in _ensure_list(value):
        if item in (None, ""):
            continue
        text = str(item).strip()
        if text:
            values.append(text)
    return values


def _dedupe(values: Iterable[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def serial_attribute_values(raw_payload: dict[str, Any] | None, field_name: str, fallback: str = "") -> list[str]:
    """Return all values for a serialNumberAttributes field."""
    values = []
    payload = raw_payload or {}
    for attributes in _ensure_list(payload.get("serialNumberAttributes")):
        if not isinstance(attributes, dict):
            continue
        values.extend(_text_values(attributes.get(field_name)))
    if not values:
        values.extend(_text_values(fallback))
    return _dedupe(values)


def joined_attribute_values(raw_payload: dict[str, Any] | None, field_name: str, fallback: str = "") -> str:
    """Return newline-separated values for Excel export."""
    return "\n".join(serial_attribute_values(raw_payload, field_name, fallback=fallback))


def serial_values_display(values: Iterable[str], limit: int = UI_SERIAL_VALUE_LIMIT) -> str:
    """Return a bounded newline display string for table cells."""
    values = list(values)
    if not values:
        return ""
    shown = values[:limit]
    if len(values) > limit:
        shown.append(f"+{len(values) - limit} more")
    return "\n".join(shown)


def serial_attribute_display(raw_payload: dict[str, Any] | None, field_name: str, fallback: str = "") -> str:
    """Return a bounded display string for a serialNumberAttributes field."""
    return serial_values_display(serial_attribute_values(raw_payload, field_name, fallback=fallback))
