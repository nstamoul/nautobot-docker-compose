"""Notification helpers for NBCOT tracked order changes."""

from __future__ import annotations

import logging
import re

import requests
from django.conf import settings
from django.core.mail import send_mail

from nbcot.choices import OrderUpdateTypeChoices


LOGGER = logging.getLogger(__name__)
NOTIFIABLE_UPDATE_TYPES = {
    OrderUpdateTypeChoices.DATE_CHANGED,
    OrderUpdateTypeChoices.STATUS_CHANGED,
    OrderUpdateTypeChoices.SHIPMENT_CHANGED,
}


def parse_recipients(value: str) -> list[str]:
    """Parse comma, semicolon, or whitespace separated email recipients."""
    return [token for token in re.split(r"[\s,;]+", value or "") if token]


def _build_message(order, changes) -> tuple[str, str]:
    subject = f"Cisco order {order.order_number} changed"
    lines = [
        f"Cisco order {order.order_number} changed.",
        f"Environment: {order.environment.upper()}",
        f"Project: {order.project_number or '-'}",
        "",
        "Changes:",
    ]
    for change in changes:
        lines.append(f"- {change.get_update_type_display()}: {change.summary}")
    return subject, "\n".join(lines)


def notify_order_changes(order, changes) -> None:
    """Notify configured recipients about date, status, and shipment changes."""
    notifiable_changes = [change for change in changes if change.update_type in NOTIFIABLE_UPDATE_TYPES]
    if not notifiable_changes:
        return

    subject, message = _build_message(order, notifiable_changes)
    recipients = parse_recipients(order.notification_recipients)
    if recipients:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=recipients,
                fail_silently=False,
            )
        except Exception:  # pragma: no cover - defensive for live mail backend failures
            LOGGER.exception("Failed to send NBCOT email notification for order %s", order.order_number)

    webhook_url = order.notification_teams_webhook_url or settings.PLUGINS_CONFIG.get("nbcot", {}).get(
        "teams_webhook_url",
        "",
    )
    if webhook_url:
        try:
            requests.post(
                webhook_url,
                json={"text": message},
                timeout=10,
            ).raise_for_status()
        except Exception:  # pragma: no cover - defensive for live Teams webhook failures
            LOGGER.exception("Failed to send NBCOT Teams notification for order %s", order.order_number)
