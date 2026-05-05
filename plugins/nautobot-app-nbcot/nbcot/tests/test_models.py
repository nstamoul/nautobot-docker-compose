"""Model tests for NBCOT."""

from django.test import TestCase

from nbcot.tests import fixtures


class CiscoOrderModelTest(TestCase):
    """Test model behavior."""

    def test_create_order_with_defaults(self):
        """Create a Cisco order and validate key defaults."""
        order = fixtures.create_ciscoorder(order_number="SO-2001")
        self.assertEqual(order.order_number, "SO-2001")
        self.assertEqual(order.status, "Submitted")
        self.assertTrue(order.is_tracked)
        self.assertEqual(str(order), "SO-2001")

    def test_related_line_and_update_stringification(self):
        """Create related line/update records."""
        order = fixtures.create_ciscoorder()
        line = fixtures.create_line(order, line_key="10")
        update = fixtures.create_update(order, summary="Dates changed")
        self.assertIn("line", str(line))
        self.assertIn(order.order_number, str(update))
