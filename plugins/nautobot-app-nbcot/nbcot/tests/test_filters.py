"""Filter tests for NBCOT."""

from django.test import TestCase

from nbcot import filters, models
from nbcot.tests import fixtures


class CiscoOrderFilterTest(TestCase):
    """Test tracked-order filtering."""

    @classmethod
    def setUpTestData(cls):
        """Create test orders."""
        fixtures.create_ciscoorder(order_number="SO-1001", account_name="Acme", status="Submitted")
        fixtures.create_ciscoorder(order_number="SO-1002", account_name="Globex", status="Shipped")

    def test_q_filter_searches_multiple_fields(self):
        """Q search should match order number or account name."""
        queryset = models.CiscoOrder.objects.all()
        self.assertEqual(filters.CiscoOrderFilterSet({"q": "Acme"}, queryset).qs.count(), 1)
        self.assertEqual(filters.CiscoOrderFilterSet({"q": "SO-1002"}, queryset).qs.count(), 1)

    def test_status_filter_matches_status(self):
        """Status filter should narrow the queryset."""
        queryset = models.CiscoOrder.objects.all()
        self.assertEqual(filters.CiscoOrderFilterSet({"status": "Ship"}, queryset).qs.count(), 1)

    def test_environment_filter_matches_environment(self):
        """Environment filter should narrow the queryset."""
        queryset = models.CiscoOrder.objects.all()
        self.assertEqual(filters.CiscoOrderFilterSet({"environment": "poe"}, queryset).qs.count(), 2)
