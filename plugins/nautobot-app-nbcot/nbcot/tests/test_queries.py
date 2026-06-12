"""Tests for Cisco GraphQL query documents."""

from unittest import TestCase

from nbcot.cisco.queries import DEFAULT_ORDER_DETAILS_QUERY


class CiscoQueryTest(TestCase):
    """Test Cisco GraphQL query documents."""

    def test_order_details_query_omits_unsupported_parent_serial_number(self):
        """Cisco production schema rejects parentSerialNumber on SerialNumberAttributes."""
        self.assertNotIn("parentSerialNumber", DEFAULT_ORDER_DETAILS_QUERY)
        self.assertIn("serialNumber", DEFAULT_ORDER_DETAILS_QUERY)
        self.assertIn("macAddresses", DEFAULT_ORDER_DETAILS_QUERY)
        self.assertIn("trackingNumber", DEFAULT_ORDER_DETAILS_QUERY)
        self.assertIn("freightCarrierUrl", DEFAULT_ORDER_DETAILS_QUERY)
