"""Synchronization logic for Cisco Commerce orders."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from nbcot.choices import ChangeSourceChoices, OrderUpdateTypeChoices, SyncStatusChoices
from nbcot.models import CiscoOrder, CiscoOrderLine, CiscoOrderUpdate

from .client import CiscoGraphQLClient
from .normalizers import CiscoPayloadNormalizer


class CiscoOrderSynchronizer:
    """Search, normalize, and persist Cisco order data."""

    def __init__(
        self,
        client: CiscoGraphQLClient | None = None,
        normalizer: CiscoPayloadNormalizer | None = None,
        environment_override: str | None = None,
    ):
        """Initialize dependencies."""
        self.client = client or CiscoGraphQLClient(environment_override=environment_override)
        self.normalizer = normalizer or CiscoPayloadNormalizer()

    def search_orders(self, filters: dict[str, Any]):
        """Return normalized search results."""
        results = self.client.search_orders(filters)
        return [self.normalizer.normalize_search_result(result) for result in results]

    def preview_order_by_number(self, order_number: str):
        """Fetch and normalize order details without persisting them."""
        raw_payload = self.client.get_order_details(order_number)
        snapshot = self.normalizer.normalize_order_details(raw_payload)
        if not snapshot.order_number:
            raise ValueError("Cisco response did not contain an order number.")
        return snapshot

    @transaction.atomic
    def sync_order_by_number(
        self,
        order_number: str,
        source: str = ChangeSourceChoices.POLL,
        tracked_line_keys: list[str] | None = None,
    ):
        """Fetch order details and persist a normalized snapshot."""
        snapshot = self.preview_order_by_number(order_number)
        environment = getattr(getattr(self.client, "settings", None), "environment", "poe")

        order, created = CiscoOrder.objects.get_or_create(
            environment=environment,
            order_number=snapshot.order_number,
            defaults={
                "is_tracked": True,
                "last_sync_status": SyncStatusChoices.PENDING,
            },
        )

        previous_state = {
            "status": order.status,
            "status_detail": order.status_detail,
            "lifecycle_state": order.lifecycle_state,
            "requested_delivery_date": order.requested_delivery_date.isoformat() if order.requested_delivery_date else None,
            "promised_delivery_date": order.promised_delivery_date.isoformat() if order.promised_delivery_date else None,
            "estimated_delivery_date": order.estimated_delivery_date.isoformat() if order.estimated_delivery_date else None,
            "open_exception_count": order.open_exception_count,
        }

        order.customer_po_number = snapshot.customer_po_number
        order.environment = environment
        order.account_name = snapshot.account_name
        order.account_number = snapshot.account_number
        order.status = snapshot.status
        order.status_detail = snapshot.status_detail
        order.lifecycle_state = snapshot.lifecycle_state
        order.requested_delivery_date = snapshot.requested_delivery_date
        order.promised_delivery_date = snapshot.promised_delivery_date
        order.estimated_delivery_date = snapshot.estimated_delivery_date
        order.ordered_at = snapshot.ordered_at
        order.last_event_at = snapshot.last_event_at
        order.open_exception_count = snapshot.open_exception_count
        order.last_synced_at = timezone.now()
        order.last_sync_status = SyncStatusChoices.SUCCESS
        order.last_sync_message = ""
        order.raw_payload = snapshot.raw_payload
        order.validated_save()

        self._sync_lines(order, snapshot.lines, tracked_line_keys=tracked_line_keys)
        changes = self._record_changes(order, previous_state, snapshot, created=created, source=source)
        return order, changes

    def record_sync_error(self, order: CiscoOrder, error: Exception, source: str = ChangeSourceChoices.POLL):
        """Persist refresh failure state for an existing tracked order."""
        order.last_synced_at = timezone.now()
        order.last_sync_status = SyncStatusChoices.ERROR
        order.last_sync_message = str(error)[:255]
        order.validated_save()
        return CiscoOrderUpdate.objects.create(
            order=order,
            update_type=OrderUpdateTypeChoices.SYNC_ERROR,
            source=source,
            summary=f"Sync failed: {error}",
            details={"error": str(error)},
            raw_payload={},
        )

    def _sync_lines(self, order: CiscoOrder, lines, tracked_line_keys: list[str] | None = None):
        existing = {line.line_key: line for line in order.lines.all()}
        seen_keys = set()
        tracked_line_key_set = set(tracked_line_keys) if tracked_line_keys is not None else None
        for line in lines:
            line_obj = existing.get(line.line_key)
            if line_obj is None:
                line_obj = CiscoOrderLine(order=order, line_key=line.line_key)
            line_obj.line_number = line.line_number
            line_obj.sku = line.sku
            line_obj.description = line.description
            line_obj.status = line.status
            line_obj.shipment_status = line.shipment_status
            line_obj.quantity_ordered = line.quantity_ordered
            line_obj.quantity_fulfilled = line.quantity_fulfilled
            line_obj.quantity_backordered = line.quantity_backordered
            line_obj.promised_delivery_date = line.promised_delivery_date
            line_obj.estimated_delivery_date = line.estimated_delivery_date
            if tracked_line_key_set is not None:
                line_obj.is_tracked = line.line_key in tracked_line_key_set
            line_obj.raw_payload = line.raw_payload
            line_obj.validated_save()
            seen_keys.add(line.line_key)

        if seen_keys:
            order.lines.exclude(line_key__in=seen_keys).delete()
        else:
            order.lines.all().delete()

    def _record_changes(self, order, previous_state, snapshot, created, source):
        updates = []
        current_state = {
            "status": snapshot.status,
            "status_detail": snapshot.status_detail,
            "lifecycle_state": snapshot.lifecycle_state,
            "requested_delivery_date": snapshot.requested_delivery_date.isoformat() if snapshot.requested_delivery_date else None,
            "promised_delivery_date": snapshot.promised_delivery_date.isoformat() if snapshot.promised_delivery_date else None,
            "estimated_delivery_date": snapshot.estimated_delivery_date.isoformat() if snapshot.estimated_delivery_date else None,
            "open_exception_count": snapshot.open_exception_count,
        }

        if created:
            updates.append(
                CiscoOrderUpdate.objects.create(
                    order=order,
                    update_type=OrderUpdateTypeChoices.CREATED,
                    source=source,
                    summary="Order started being tracked.",
                    details={"after": current_state},
                    raw_payload=snapshot.raw_payload,
                )
            )
            return updates

        status_before = {key: previous_state[key] for key in ("status", "status_detail", "lifecycle_state")}
        status_after = {key: current_state[key] for key in ("status", "status_detail", "lifecycle_state")}
        if status_before != status_after:
            updates.append(
                CiscoOrderUpdate.objects.create(
                    order=order,
                    update_type=OrderUpdateTypeChoices.STATUS_CHANGED,
                    source=source,
                    summary="Order status changed.",
                    details={"before": status_before, "after": status_after},
                    raw_payload=snapshot.raw_payload,
                )
            )

        date_before = {
            key: previous_state[key]
            for key in ("requested_delivery_date", "promised_delivery_date", "estimated_delivery_date")
        }
        date_after = {
            key: current_state[key]
            for key in ("requested_delivery_date", "promised_delivery_date", "estimated_delivery_date")
        }
        if date_before != date_after:
            updates.append(
                CiscoOrderUpdate.objects.create(
                    order=order,
                    update_type=OrderUpdateTypeChoices.DATE_CHANGED,
                    source=source,
                    summary="Delivery dates changed.",
                    details={"before": date_before, "after": date_after},
                    raw_payload=snapshot.raw_payload,
                )
            )

        if previous_state["open_exception_count"] != current_state["open_exception_count"]:
            updates.append(
                CiscoOrderUpdate.objects.create(
                    order=order,
                    update_type=OrderUpdateTypeChoices.EXCEPTION_CHANGED,
                    source=source,
                    summary="Order exceptions changed.",
                    details={
                        "before": {"open_exception_count": previous_state["open_exception_count"]},
                        "after": {
                            "open_exception_count": current_state["open_exception_count"],
                            "exceptions": snapshot.exceptions,
                        },
                    },
                    raw_payload=snapshot.raw_payload,
                )
            )

        return updates
