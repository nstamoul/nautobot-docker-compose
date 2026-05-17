"""View tests for NBCOT."""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from nautobot.apps.testing import ViewTestCases

from nbcot import models
from nbcot.tests import fixtures


class CiscoOrderViewTest(ViewTestCases.PrimaryObjectViewTestCase):
    """Test the standard CiscoOrder UI views."""

    model = models.CiscoOrder
    bulk_edit_data = {"status": "Bulk Updated"}
    form_data = {
        "order_number": "SO-5001",
        "customer_po_number": "PO-5001",
        "account_name": "Initial Account",
        "status": "Submitted",
        "is_tracked": True,
    }
    update_data = {
        "order_number": "SO-5001",
        "customer_po_number": "PO-5001",
        "account_name": "Updated Account",
        "status": "Shipped",
        "is_tracked": True,
    }

    @classmethod
    def setUpTestData(cls):
        """Create tracked orders for generic view tests."""
        fixtures.create_ciscoorder(order_number="SO-5002")
        fixtures.create_ciscoorder(order_number="SO-5003")
        fixtures.create_ciscoorder(order_number="SO-5004")


class NBCOTCustomViewTest(TestCase):
    """Test custom search and action views."""

    @classmethod
    def setUpTestData(cls):
        """Create a superuser and one tracked order."""
        cls.user = get_user_model().objects.create_superuser(
            username="nbcot-admin",
            email="admin@example.com",
            password="password",
        )
        cls.order = fixtures.create_ciscoorder(order_number="SO-6001")

    def setUp(self):
        """Authenticate the test client."""
        self.client.force_login(self.user)

    @patch("nbcot.views.CiscoOrderSynchronizer")
    def test_search_view_renders_results(self, mock_sync_class):
        """Search page should render normalized results."""
        mock_sync = mock_sync_class.return_value
        mock_sync.search_orders.return_value = [
            type(
                "Result",
                (),
                {
                    "order_number": "SO-7001",
                    "customer_po_number": "PO-7001",
                    "account_name": "Acme",
                    "status": "Submitted",
                    "promised_delivery_date": None,
                    "estimated_delivery_date": None,
                    "open_exception_count": 0,
                },
            )()
        ]
        response = self.client.get(
            reverse("plugins:nbcot:order_search"),
            {"environment": "prod", "order_number": "SO-7001"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SO-7001")
        mock_sync_class.assert_called_once_with(environment_override="prod")
        mock_sync.search_orders.assert_called_once_with({"order_number": "SO-7001"})

    @patch("nbcot.views.CiscoOrderSynchronizer")
    def test_preview_view_renders_lines_without_persisting_order(self, mock_sync_class):
        """Previewing an order should not create a tracked CiscoOrder row."""
        mock_sync = mock_sync_class.return_value
        mock_sync.preview_order_by_number.return_value = SimpleNamespace(
            order_number="SO-7100",
            customer_po_number="PO-7100",
            account_name="Acme",
            account_number="A-7100",
            status="Submitted",
            status_detail="",
            lifecycle_state="SUCCESS",
            requested_delivery_date=None,
            promised_delivery_date=None,
            estimated_delivery_date=None,
            open_exception_count=0,
            lines=[
                SimpleNamespace(
                    line_key="major-1",
                    line_number="1.0",
                    sku="N9K-C93180YC-FX",
                    description="Switch",
                    status="Open",
                    shipment_status="",
                    quantity_ordered=1,
                    quantity_fulfilled=0,
                    quantity_backordered=1,
                    promised_delivery_date=None,
                    estimated_delivery_date=None,
                ),
                SimpleNamespace(
                    line_key="minor-1",
                    line_number="1.0.1",
                    sku="CON-SNT",
                    description="Support",
                    status="Open",
                    shipment_status="",
                    quantity_ordered=1,
                    quantity_fulfilled=0,
                    quantity_backordered=1,
                    promised_delivery_date=None,
                    estimated_delivery_date=None,
                ),
            ],
        )

        response = self.client.get(
            reverse("plugins:nbcot:order_preview"),
            {"environment": "prod", "order_number": "SO-7100"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SO-7100")
        self.assertContains(response, "N9K-C93180YC-FX")
        self.assertContains(response, "CON-SNT")
        self.assertContains(response, 'data-line-filter="sku"')
        self.assertContains(response, 'data-line-sort="line"')
        self.assertFalse(models.CiscoOrder.objects.filter(order_number="SO-7100").exists())
        mock_sync_class.assert_called_once_with(environment_override="prod")
        mock_sync.preview_order_by_number.assert_called_once_with("SO-7100")

    def test_detail_view_uses_line_tree_controls_for_persisted_lines(self):
        """Saved order detail should expose the same line filtering, sorting, and tree controls."""
        fixtures.create_line(self.order, line_key="45.0", line_number="45.0", sku="HCI-MAJOR", is_tracked=True)
        fixtures.create_line(self.order, line_key="45.1", line_number="45.1", sku="HCI-SUBMAJOR")
        fixtures.create_line(self.order, line_key="45.1.1", line_number="45.1.1", sku="HCI-CHILD")

        response = self.client.get(self.order.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-line-tree="nbcot-order-lines-')
        self.assertContains(response, 'data-line-filter="all"')
        self.assertContains(response, 'data-line-filter="sku"')
        self.assertContains(response, 'data-line-sort="line"')
        self.assertContains(response, 'data-line-action="expand-all"')
        self.assertContains(response, 'data-line-action="collapse-all"')
        self.assertContains(response, 'data-line-action="select-visible"')
        self.assertContains(response, 'data-line-action="clear-visible"')
        self.assertContains(response, "Save Line Tracking")
        self.assertContains(response, 'name="line_keys" value="45.0" checked')
        self.assertContains(response, 'name="line_keys" value="45.1"')
        self.assertContains(response, "HCI-SUBMAJOR")

    def test_line_tracking_view_updates_selected_lines(self):
        """Saved order detail should persist the line tracking checkbox selections."""
        major_line = fixtures.create_line(self.order, line_key="45.0", line_number="45.0", sku="HCI-MAJOR")
        tracked_child = fixtures.create_line(
            self.order,
            line_key="45.1",
            line_number="45.1",
            sku="HCI-SUBMAJOR",
            is_tracked=True,
        )
        untracked_child = fixtures.create_line(self.order, line_key="45.1.1", line_number="45.1.1", sku="HCI-CHILD")

        response = self.client.post(
            reverse("plugins:nbcot:ciscoorder_line_tracking", kwargs={"pk": self.order.pk}),
            {"line_keys": [major_line.line_key, untracked_child.line_key]},
        )

        self.assertRedirects(response, self.order.get_absolute_url())
        major_line.refresh_from_db()
        tracked_child.refresh_from_db()
        untracked_child.refresh_from_db()
        self.assertTrue(major_line.is_tracked)
        self.assertFalse(tracked_child.is_tracked)
        self.assertTrue(untracked_child.is_tracked)

    @patch("nbcot.views.CiscoOrderSynchronizer")
    def test_track_view_redirects_to_order(self, mock_sync_class):
        """Tracking an order should redirect to the detail view."""
        mock_sync = mock_sync_class.return_value
        mock_sync.sync_order_by_number.return_value = (self.order, [])
        response = self.client.post(
            reverse("plugins:nbcot:order_track"),
            {"environment": "prod", "order_number": self.order.order_number},
        )
        self.assertRedirects(response, self.order.get_absolute_url())
        mock_sync_class.assert_called_once_with(environment_override="prod")
        mock_sync.sync_order_by_number.assert_called_once_with(
            order_number=self.order.order_number,
            source="manual",
            tracked_line_keys=None,
        )

    @patch("nbcot.views.CiscoOrderSynchronizer")
    def test_track_view_passes_selected_line_keys(self, mock_sync_class):
        """Tracking from preview should pass selected line keys to the synchronizer."""
        mock_sync = mock_sync_class.return_value
        mock_sync.sync_order_by_number.return_value = (self.order, [])

        response = self.client.post(
            reverse("plugins:nbcot:order_track"),
            {
                "environment": "prod",
                "order_number": self.order.order_number,
                "line_keys": ["major-1", "minor-1"],
            },
        )

        self.assertRedirects(response, self.order.get_absolute_url())
        mock_sync.sync_order_by_number.assert_called_once_with(
            order_number=self.order.order_number,
            source="manual",
            tracked_line_keys=["major-1", "minor-1"],
        )

    @patch("nbcot.views.CiscoSubscriptionService")
    def test_ccwr_view_renders_detail(self, mock_service_class):
        """CCW-R page should render subscription detail when exact identifier is supplied."""
        detail = type(
            "Detail",
            (),
            {
                "identifier": "205093077",
                "name": "Contract 205093077",
                "status": "ACTIVE",
                "activation_date": None,
                "start_date": None,
                "end_date": None,
                "renewal_date": None,
                "has_auto_renewal": False,
                "billing_preference": "",
                "end_customer_name": "AHEPA GENERAL HOSPITAL",
                "end_customer_id": "1084635571",
                "bill_to_name": "SPACE HELLAS SA",
                "bill_to_id": "30402848",
                "install_site_name": "AHEPA GENERAL HOSPITAL",
                "install_site_id": "1084635571",
                "lines": [],
                "filtered_lines": lambda self_filters: [],
            },
        )()
        mock_service_class.return_value.get_detail.return_value = detail
        response = self.client.get(
            reverse("plugins:nbcot:subscription_search"),
            {
                "environment": "prod",
                "subscription_identifier": "205093077",
                "from_date": "2022-01-01",
                "to_date": "2035-12-31",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "205093077")
        mock_service_class.assert_called_once_with(environment_override="prod")

    @patch("nbcot.views.CiscoOrderSynchronizer")
    def test_refresh_view_redirects_back_to_order(self, mock_sync_class):
        """Refresh action should redirect back to the order detail."""
        mock_sync = mock_sync_class.return_value
        mock_sync.sync_order_by_number.return_value = (self.order, [])
        response = self.client.get(reverse("plugins:nbcot:ciscoorder_refresh", kwargs={"pk": self.order.pk}))
        self.assertRedirects(response, self.order.get_absolute_url())
        mock_sync_class.assert_called_once_with(environment_override=self.order.environment)

    def test_toggle_tracking_view_flips_boolean(self):
        """Toggle tracking should update the stored flag."""
        self.assertTrue(self.order.is_tracked)
        response = self.client.get(reverse("plugins:nbcot:ciscoorder_toggle_tracking", kwargs={"pk": self.order.pk}))
        self.assertRedirects(response, self.order.get_absolute_url())
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_tracked)
