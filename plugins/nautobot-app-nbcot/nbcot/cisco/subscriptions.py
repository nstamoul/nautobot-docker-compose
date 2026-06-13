"""CCW-R subscription helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .client import CiscoGraphQLClient
from .normalizers import _ensure_list, _parse_date


def _party_map(parties: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping = {}
    for party in parties:
        party_type = str(party.get("type") or "").upper()
        if party_type and party_type not in mapping:
            mapping[party_type] = party
    return mapping


def _line_matches(line: "NormalizedSubscriptionLine", filters: dict[str, str]) -> bool:
    for key, value in filters.items():
        text = str(value or "").strip().lower()
        if not text:
            continue
        haystacks = {
            "pak_serial_number": [
                line.serial_pak_instance_number,
                line.additional_attributes_text,
                line.sku,
                line.description,
            ],
            "so_mso_number": [line.sales_order_number, line.web_order_id, line.additional_attributes_text],
            "po_mpo_number": [
                line.purchase_order_number,
                line.purchase_order_line_reference,
                line.additional_attributes_text,
            ],
            "line_end_customer": [line.end_customer_name, line.end_customer_id],
        }.get(key, [])
        if not any(text in str(candidate or "").lower() for candidate in haystacks):
            return False
    return True


@dataclass
class NormalizedSubscriptionSearchResult:
    """Normalized CCW-R search result."""

    identifier: str
    name: str = ""
    status: str = ""
    activation_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    has_auto_renewal: bool | None = None
    billing_preference: str = ""
    end_customer_name: str = ""
    end_customer_id: str = ""
    bill_to_name: str = ""
    bill_to_id: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedSubscriptionLine:
    """Normalized CCW-R subscription line."""

    line_id: str = ""
    parent_line_id: str = ""
    sku: str = ""
    description: str = ""
    quantity: str = ""
    unit_of_measure: str = ""
    web_order_id: str = ""
    sales_order_number: str = ""
    purchase_order_number: str = ""
    purchase_order_line_reference: str = ""
    user_interface_line_id: str = ""
    serial_pak_instance_number: str = ""
    end_customer_name: str = ""
    end_customer_id: str = ""
    additional_attributes: list[dict[str, Any]] = field(default_factory=list)
    additional_attributes_text: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedSubscriptionDetail:
    """Normalized CCW-R subscription detail."""

    identifier: str
    name: str = ""
    status: str = ""
    activation_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    renewal_date: date | None = None
    has_auto_renewal: bool | None = None
    billing_preference: str = ""
    end_customer_name: str = ""
    end_customer_id: str = ""
    bill_to_name: str = ""
    bill_to_id: str = ""
    install_site_name: str = ""
    install_site_id: str = ""
    lines: list[NormalizedSubscriptionLine] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def filtered_lines(self, filters: dict[str, str]) -> list[NormalizedSubscriptionLine]:
        """Apply client-side filters to the resolved line set."""
        if not filters:
            return self.lines
        return [line for line in self.lines if _line_matches(line, filters)]


class CiscoSubscriptionService:
    """Small service wrapper for CCW-R subscription queries."""

    def __init__(self, client: CiscoGraphQLClient | None = None, environment_override: str | None = None):
        self.client = client or CiscoGraphQLClient(environment_override=environment_override)

    @staticmethod
    def _normalize_result(payload: dict[str, Any]) -> NormalizedSubscriptionSearchResult:
        parties = _ensure_list(payload.get("parties"))
        party_lookup = _party_map(parties)
        characteristics = payload.get("mySubscriptionCharacteristics") or {}
        end_customer = party_lookup.get("END_CUSTOMER") or {}
        bill_to = party_lookup.get("BILL_TO") or {}
        return NormalizedSubscriptionSearchResult(
            identifier=str(payload.get("id") or ""),
            name=str(payload.get("name") or ""),
            status=str(characteristics.get("mySubscriptionStatus") or payload.get("businessStatus") or ""),
            activation_date=_parse_date(payload.get("activationDate") or characteristics.get("activationDate")),
            start_date=_parse_date(characteristics.get("startDate")),
            end_date=_parse_date(characteristics.get("endDate")),
            has_auto_renewal=characteristics.get("hasAutoRenewal"),
            billing_preference=str(characteristics.get("billingPreference") or ""),
            end_customer_name=str(end_customer.get("name") or ""),
            end_customer_id=str(end_customer.get("id") or ""),
            bill_to_name=str(bill_to.get("name") or ""),
            bill_to_id=str(bill_to.get("id") or ""),
            raw_payload=payload,
        )

    @staticmethod
    def _normalize_line(payload: dict[str, Any], detail: NormalizedSubscriptionSearchResult) -> NormalizedSubscriptionLine:
        attrs = _ensure_list((payload.get("item") or {}).get("additionalAttributes"))
        attrs_text = " ".join(
            f"{attribute.get('name', '')}:{attribute.get('value', '')}" for attribute in attrs if attribute
        )
        serial_value = ""
        for attribute in attrs:
            name = str(attribute.get("name") or "").lower()
            if any(token in name for token in ("serial", "pak", "instance", "host", "mac")):
                serial_value = str(attribute.get("value") or "")
                if serial_value:
                    break

        order_reference = payload.get("orderReference") or {}
        line_reference = payload.get("orderLineReference") or {}
        quantity = payload.get("quantity") or {}
        item = payload.get("item") or {}
        subscription_line_reference = payload.get("mySubscriptionLineReference") or {}
        return NormalizedSubscriptionLine(
            line_id=str(subscription_line_reference.get("lineId") or ""),
            parent_line_id=str(subscription_line_reference.get("parentLineId") or ""),
            sku=str(item.get("sku") or ""),
            description=str(item.get("description") or ""),
            quantity=str(quantity.get("measurement") or ""),
            unit_of_measure=str(quantity.get("unitOfMeasure") or ""),
            web_order_id=str(order_reference.get("webOrderId") or line_reference.get("webOrderId") or ""),
            sales_order_number=str(
                ((order_reference.get("ciscoSalesOrderReference") or {}).get("ciscoSalesOrderId")) or ""
            ),
            purchase_order_number=str(
                ((order_reference.get("buyerPurchaseOrderReference") or {}).get("purchaseOrderId")) or ""
            ),
            purchase_order_line_reference=str(line_reference.get("purchaseOrderLineReference") or ""),
            user_interface_line_id=str(line_reference.get("userInterfaceLineId") or ""),
            serial_pak_instance_number=serial_value,
            end_customer_name=detail.end_customer_name,
            end_customer_id=detail.end_customer_id,
            additional_attributes=attrs,
            additional_attributes_text=attrs_text,
            raw_payload=payload,
        )

    def search(self, filters: dict[str, Any]) -> list[NormalizedSubscriptionSearchResult]:
        """Search CCW-R subscriptions."""
        results = self.client.search_subscriptions(filters)
        return [self._normalize_result(result) for result in results]

    def get_detail(self, filters: dict[str, Any]) -> NormalizedSubscriptionDetail | None:
        """Fetch one CCW-R subscription detail."""
        payload = self.client.get_subscription_details(filters)
        if not payload:
            return None

        base = self._normalize_result(payload)
        party_lookup = _party_map(_ensure_list(payload.get("parties")))
        install_site = party_lookup.get("INSTALL_SITE") or {}
        detail = NormalizedSubscriptionDetail(
            identifier=base.identifier,
            name=base.name,
            status=base.status,
            activation_date=base.activation_date,
            start_date=base.start_date,
            end_date=base.end_date,
            renewal_date=_parse_date((payload.get("mySubscriptionCharacteristics") or {}).get("renewalDate")),
            has_auto_renewal=base.has_auto_renewal,
            billing_preference=base.billing_preference,
            end_customer_name=base.end_customer_name,
            end_customer_id=base.end_customer_id,
            bill_to_name=base.bill_to_name,
            bill_to_id=base.bill_to_id,
            install_site_name=str(install_site.get("name") or ""),
            install_site_id=str(install_site.get("id") or ""),
            raw_payload=payload,
        )
        detail.lines = [self._normalize_line(line, detail) for line in _ensure_list(payload.get("lines"))]
        return detail
