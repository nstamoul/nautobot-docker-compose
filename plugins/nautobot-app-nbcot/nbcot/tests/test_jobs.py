"""Job tests for NBCOT."""

from unittest.mock import patch

from django.test import TestCase

from nbcot.jobs import RefreshCiscoOrderJob, RefreshSelectedCiscoOrdersJob, RefreshTrackedOrdersJob
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
        """Bulk job should refresh all tracked non-archived orders."""
        fixtures.create_ciscoorder(order_number="SO-10003", is_archived=True)
        fixtures.create_ciscoorder(order_number="SO-10004", is_tracked=False)
        mock_sync = mock_sync_class.return_value
        mock_sync.sync_order_by_number.return_value = (self.order, [])
        job = RefreshTrackedOrdersJob()
        job.run()
        self.assertEqual(mock_sync_class.call_count, 2)
        self.assertEqual(mock_sync.sync_order_by_number.call_count, 2)

    @patch("nbcot.jobs.CiscoOrderSynchronizer")
    def test_refresh_selected_orders_job(self, mock_sync_class):
        """Selected-order job should refresh only the supplied orders."""
        other_order = fixtures.create_ciscoorder(order_number="SO-10003")
        skipped_order = fixtures.create_ciscoorder(order_number="SO-10004")
        mock_sync = mock_sync_class.return_value
        mock_sync.sync_order_by_number.return_value = (self.order, [])

        job = RefreshSelectedCiscoOrdersJob()
        job.run(orders=[self.order, other_order])

        self.assertEqual(mock_sync_class.call_count, 2)
        refreshed_order_numbers = [
            call.args[0] for call in mock_sync.sync_order_by_number.call_args_list
        ]
        self.assertEqual(refreshed_order_numbers, ["SO-10001", "SO-10003"])
        self.assertNotIn(skipped_order.order_number, refreshed_order_numbers)
