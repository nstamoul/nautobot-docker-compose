"""Tests for NBCOT notification formatting and delivery."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from nbcot.choices import OrderUpdateTypeChoices
from nbcot.notifications import notify_order_changes


class NotificationTest(SimpleTestCase):
    """Test email and Teams notification behavior."""

    @override_settings(
        DEFAULT_FROM_EMAIL="nautobot@example.com",
        PLUGINS_CONFIG={"nbcot": {"teams_webhook_url": "https://teams.example/webhook"}},
    )
    @patch("nbcot.notifications.requests.post")
    @patch("nbcot.notifications.send_mail")
    def test_teams_notification_uses_html_breaks_without_changing_email_plain_text(self, mock_send_mail, mock_post):
        """Teams should receive HTML line breaks while email keeps the plain-text body."""
        order = SimpleNamespace(
            order_number="119744472",
            environment="prod",
            project_number="PRJ-1",
            notification_recipients="ops@example.com",
            notification_teams_webhook_url="",
        )
        change = SimpleNamespace(
            update_type=OrderUpdateTypeChoices.STATUS_CHANGED,
            summary="Status changed from <BOOKED> to CLOSED",
            get_update_type_display=lambda: "Status Changed",
        )

        notify_order_changes(order, [change])

        email_body = mock_send_mail.call_args.kwargs["message"]
        teams_body = mock_post.call_args.kwargs["json"]["text"]
        self.assertIn("\nChanges:\n- Status Changed:", email_body)
        self.assertNotIn("<br>", email_body)
        self.assertIn("<br>Changes:<br>- Status Changed:", teams_body)
        self.assertIn("&lt;BOOKED&gt;", teams_body)
