"""API tests for NBCOT."""

from nautobot.apps.testing import APIViewTestCases

from nbcot import models
from nbcot.tests import fixtures


class CiscoOrderAPIViewTest(APIViewTestCases.APIViewTestCase):
    """Test the API viewsets for CiscoOrder."""

    model = models.CiscoOrder
    choices_fields = ("last_sync_status",)

    @classmethod
    def setUpTestData(cls):
        """Create test data for CiscoOrder API viewset."""
        super().setUpTestData()
        fixtures.create_ciscoorder(order_number="SO-4001")
        fixtures.create_ciscoorder(order_number="SO-4002")
        fixtures.create_ciscoorder(order_number="SO-4003")
        cls.create_data = [
            {
                "order_number": "SO-4101",
                "customer_po_number": "PO-4101",
                "account_name": "API Account One",
                "status": "Submitted",
            },
            {
                "order_number": "SO-4102",
                "customer_po_number": "PO-4102",
                "account_name": "API Account Two",
                "status": "Open",
            },
            {
                "order_number": "SO-4103",
                "customer_po_number": "PO-4103",
                "account_name": "API Account Three",
                "status": "Shipped",
            },
        ]
        cls.update_data = {
            "order_number": "SO-4999",
            "status": "Delivered",
            "account_name": "Updated API Account",
        }
        cls.bulk_update_data = {
            "status": "Closed",
        }
