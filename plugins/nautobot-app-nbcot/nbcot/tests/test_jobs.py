"""Job tests for NBCOT."""

from unittest.mock import patch

from django.test import TestCase

from nbcot.jobs import RefreshCiscoOrderJob, RefreshTrackedOrdersJob
from nbcot.tests import fixtures


class NBCOTJobTest(TestCase):
    """Test refresh jobs."""

    def setUp(self):
        """Create tracked orders for job tests."""
        self.order = fixtures.create_ciscoorder(order_number="SO-10001")
        fixtures.create_ciscoorder(order_number="SO-10002")

    @patch("nbcot.jobs.CiscoOrderSynchronizer")
    def test_refresh_single_order_job(self, mock_sync_class):
        """Single-order job should refresh the provided order."""
        mock_sync = mock_sync_class.return_value
        mock_sync.sync_order_by_number.return_value = (self.order, [])
        job = RefreshCiscoOrderJob()
        job.run(order=self.order)
        mock_sync_class.assert_called_once_with(environment_override=self.order.environment)
        mock_sync.sync_order_by_number.assert_called_once_with("SO-10001", source="manual")

    @patch("nbcot.jobs.CiscoOrderSynchronizer")
    def test_refresh_all_tracked_orders_job(self, mock_sync_class):
        """Bulk job should refresh all tracked orders."""
        mock_sync = mock_sync_class.return_value
        mock_sync.sync_order_by_number.return_value = (self.order, [])
        job = RefreshTrackedOrdersJob()
        job.run()
        self.assertEqual(mock_sync_class.call_count, 2)
        self.assertEqual(mock_sync.sync_order_by_number.call_count, 2)
