"""Normalization helpers for Cisco Commerce payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


def _get_nested(data: dict[str, Any], path: tuple[str, ...]):
    current = data
    for item in path:
        if not isinstance(current, dict):
            return None
        current = current.get(item)
        if current in (None, ""):
            return current
    return current


def _first_value(data: dict[str, Any], *paths: tuple[str, ...], default=None):
    for path in paths:
        value = _get_nested(data, path)
        if value not in (None, ""):
            return value
    return default


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def _parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _ensure_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _to_int(value, default=0):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class NormalizedOrderLine:
    """Normalized line item."""

    line_key: str
    line_number: str = ""
    sku: str = ""
    description: str = ""
    status: str = ""
    shipment_status: str = ""
    quantity_ordered: int = 0
    quantity_fulfilled: int = 0
    quantity_backordered: int = 0
    promised_delivery_date: date | None = None
    estimated_delivery_date: date | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedOrderSnapshot:
    """Normalized top-level order payload."""

    order_number: str
    customer_po_number: str = ""
    account_name: str = ""
    account_number: str = ""
    status: str = ""
    status_detail: str = ""
    lifecycle_state: str = ""
    requested_delivery_date: date | None = None
    promised_delivery_date: date | None = None
    estimated_delivery_date: date | None = None
    ordered_at: datetime | None = None
    last_event_at: datetime | None = None
    open_exception_count: int = 0
    exceptions: list[dict[str, Any]] = field(default_factory=list)
    lines: list[NormalizedOrderLine] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Normalized ad hoc search result."""

    order_number: str
    customer_po_number: str = ""
    account_name: str = ""
    account_number: str = ""
    status: str = ""
    promised_delivery_date: date | None = None
    estimated_delivery_date: date | None = None
    requested_delivery_date: date | None = None
    open_exception_count: int = 0
    raw_payload: dict[str, Any] = field(default_factory=dict)


class CiscoPayloadNormalizer:
    """Convert Cisco payloads into app-owned normalized structures."""

    search_result_paths = {
        "order_number": (
            ("ciscoSalesOrderReference", "ciscoSalesOrderId"),
            ("orderNumber",),
            ("order", "orderNumber"),
            ("header", "orderNumber"),
        ),
        "customer_po_number": (
            ("buyerPurchaseOrderReference", "purchaseOrderId"),
            ("customerPoNumber",),
            ("customerPurchaseOrderNumber",),
            ("customer", "poNumber"),
            ("header", "customerPoNumber"),
        ),
        "status": (("orderStatus",), ("status",), ("header", "status")),
        "promised_delivery_date": (("promisedDeliveryDate",), ("header", "promisedDeliveryDate")),
        "estimated_delivery_date": (("estimatedDeliveryDate",), ("header", "estimatedDeliveryDate")),
        "requested_delivery_date": (("requestedDeliveryDate",), ("header", "requestedDeliveryDate")),
        "open_exception_count": (("openExceptionCount",), ("header", "openExceptionCount")),
    }

    @staticmethod
    def _select_party(payload: dict[str, Any]):
        parties = _ensure_list(payload.get("parties"))
        if not parties:
            return {}

        def _score(party):
            tokens = " ".join(str(party.get(key, "")).upper() for key in ("type", "partnerType", "name"))
            score = 0
            if "END" in tokens and "CUSTOMER" in tokens:
                score += 30
            if "BILL" in tokens:
                score += 20
            if "CUSTOMER" in tokens:
                score += 10
            return score

        return sorted(parties, key=_score, reverse=True)[0]

    @staticmethod
    def _collect_order_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
        messages = []
        for message in _ensure_list(payload.get("messages")):
            messages.append(
                {
                    "code": message.get("code", ""),
                    "message": message.get("description") or message.get("message") or "",
                    "severity": message.get("severity", ""),
                }
            )
        return messages

    @staticmethod
    def _collect_line_holds(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        holds = []
        for raw_line in lines:
            line_key = _first_value(
                raw_line,
                ("orderLineReference", "lineId"),
                ("lineKey",),
                ("lineNumber",),
                default="",
            )
            for hold in _ensure_list(raw_line.get("holdInformation")):
                holds.append(
                    {
                        "code": hold.get("name", ""),
                        "message": hold.get("description") or hold.get("reason") or hold.get("name") or "",
                        "severity": "ERROR" if hold.get("isPartnerActionRequired") else "WARNING",
                        "line_key": str(line_key),
                    }
                )
        return holds

    @staticmethod
    def _line_delivery_dates(raw_lines: list[dict[str, Any]], field_name: str):
        dates = []
        for raw_line in raw_lines:
            shipping = raw_line.get("shippingAttributes") or {}
            parsed = _parse_date(shipping.get(field_name))
            if parsed:
                dates.append(parsed)
        return min(dates) if dates else None

    def normalize_search_result(self, payload: dict[str, Any]) -> SearchResult:
        """Normalize a search result object."""
        values = {
            key: _first_value(payload, *paths, default="")
            for key, paths in self.search_result_paths.items()
        }
        party = self._select_party(payload)
        messages = self._collect_order_messages(payload)
        return SearchResult(
            order_number=str(values["order_number"] or ""),
            customer_po_number=str(values["customer_po_number"] or ""),
            account_name=str(party.get("name") or ""),
            account_number=str(party.get("id") or ""),
            status=str(values["status"] or ""),
            promised_delivery_date=_parse_date(values["promised_delivery_date"]),
            estimated_delivery_date=_parse_date(values["estimated_delivery_date"]),
            requested_delivery_date=_parse_date(values["requested_delivery_date"]),
            open_exception_count=_to_int(values["open_exception_count"], default=len(messages)),
            raw_payload=payload,
        )

    def normalize_order_details(self, payload: dict[str, Any]) -> NormalizedOrderSnapshot:
        """Normalize an order detail payload."""
        raw_lines = _ensure_list(_first_value(payload, ("lines",), ("orderLines",), ("lineItems",), default=[]))
        exceptions = self._collect_order_messages(payload)
        exceptions.extend(self._collect_line_holds(raw_lines))

        lines = []
        for index, raw_line in enumerate(raw_lines, start=1):
            line_number = str(
                _first_value(
                    raw_line,
                    ("orderLineReference", "userInterfaceLineId"),
                    ("lineNumber",),
                    ("orderLineReference", "lineId"),
                    ("lineId",),
                    ("id",),
                    default=index,
                )
            )
            sku = str(_first_value(raw_line, ("item", "sku"), ("sku",), ("partNumber",), default=""))
            line_key = str(
                _first_value(
                    raw_line,
                    ("orderLineReference", "lineId"),
                    ("lineKey",),
                    ("lineNumber",),
                    ("lineId",),
                    default=f"{line_number}:{sku}",
                )
            )
            quantity_ordered = _to_int(_first_value(raw_line, ("quantity", "measurement"), ("quantityOrdered",), default=0))
            quantity_fulfilled = _to_int(
                _first_value(raw_line, ("shippingAttributes", "shippedQty"), ("quantityFulfilled",), default=0)
            )
            lines.append(
                NormalizedOrderLine(
                    line_key=line_key,
                    line_number=line_number,
                    sku=sku,
                    description=str(_first_value(raw_line, ("item", "description"), ("description",), default="")),
                    status=str(_first_value(raw_line, ("orderLineStatus",), ("status",), default="")),
                    shipment_status=str(
                        _first_value(
                            raw_line,
                            ("shippingAttributes", "shipSetStatus"),
                            ("shipmentStatus",),
                            ("fulfillmentStatus",),
                            default="",
                        )
                    ),
                    quantity_ordered=quantity_ordered,
                    quantity_fulfilled=quantity_fulfilled,
                    quantity_backordered=max(quantity_ordered - quantity_fulfilled, 0),
                    promised_delivery_date=_parse_date(
                        _first_value(
                            raw_line,
                            ("shippingAttributes", "promisedDate"),
                            ("promisedDeliveryDate",),
                            ("delivery", "promisedDate"),
                            default=None,
                        )
                    ),
                    estimated_delivery_date=_parse_date(
                        _first_value(
                            raw_line,
                            ("shippingAttributes", "estimatedDeliveryDate"),
                            ("estimatedDeliveryDate",),
                            ("delivery", "estimatedDate"),
                            default=None,
                        )
                    ),
                    raw_payload=raw_line,
                )
            )

        party = self._select_party(payload)
        line_event_datetimes = [
            _parse_datetime(_first_value(raw_line, ("orderLineStatusHistory", "updatedOn"), default=None))
            for raw_line in raw_lines
        ]
        last_event_at = max((value for value in line_event_datetimes if value), default=None)

        return NormalizedOrderSnapshot(
            order_number=str(
                _first_value(
                    payload,
                    ("ciscoSalesOrderReference", "ciscoSalesOrderId"),
                    ("orderNumber",),
                    ("header", "orderNumber"),
                    ("id",),
                    default="",
                )
            ),
            customer_po_number=str(
                _first_value(
                    payload,
                    ("buyerPurchaseOrderReference", "purchaseOrderId"),
                    ("customerPoNumber",),
                    ("customerPurchaseOrderNumber",),
                    ("header", "customerPoNumber"),
                    default="",
                )
            ),
            account_name=str(party.get("name") or ""),
            account_number=str(party.get("id") or ""),
            status=str(_first_value(payload, ("orderStatus",), ("status",), ("header", "status"), default="")),
            status_detail=str(
                _first_value(payload, ("businessStatus",), ("statusDetail",), ("header", "statusDetail"), default="")
                or (exceptions[0]["message"] if exceptions else "")
            ),
            lifecycle_state=str(
                _first_value(payload, ("businessStatus",), ("lifecycleState",), ("header", "lifecycleState"), default="")
            ),
            requested_delivery_date=_parse_date(
                _first_value(payload, ("requestedDeliveryDate",), ("header", "requestedDeliveryDate"), default=None)
            )
            or self._line_delivery_dates(raw_lines, "requestedDeliveryDate"),
            promised_delivery_date=_parse_date(
                _first_value(payload, ("promisedDeliveryDate",), ("header", "promisedDeliveryDate"), default=None)
            )
            or self._line_delivery_dates(raw_lines, "promisedDate"),
            estimated_delivery_date=_parse_date(
                _first_value(payload, ("estimatedDeliveryDate",), ("header", "estimatedDeliveryDate"), default=None)
            )
            or self._line_delivery_dates(raw_lines, "estimatedDeliveryDate"),
            ordered_at=_parse_datetime(
                _first_value(
                    payload,
                    ("metaData", "createdOn"),
                    ("buyerPurchaseOrderReference", "purchaseOrderDate"),
                    ("orderedAt",),
                    ("header", "orderedAt"),
                    default=None,
                )
            ),
            last_event_at=last_event_at
            or _parse_datetime(
                _first_value(payload, ("metaData", "lastUpdatedAt"), ("lastEventAt",), ("header", "lastEventAt"), default=None)
            ),
            open_exception_count=_to_int(
                _first_value(payload, ("openExceptionCount",), ("header", "openExceptionCount"), default=len(exceptions)),
                default=len(exceptions),
            ),
            exceptions=exceptions,
            lines=lines,
            raw_payload=payload,
        )
