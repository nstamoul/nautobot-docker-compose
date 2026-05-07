"""NBCOT jobs."""

from nautobot.apps.jobs import Job, ObjectVar, register_jobs

from nbcot.choices import ChangeSourceChoices
from nbcot.models import CiscoOrder

from .cisco.sync import CiscoOrderSynchronizer

name = "NBCOT"  # pylint: disable=invalid-name


class RefreshCiscoOrderJob(Job):
    """Refresh one tracked Cisco order."""

    order = ObjectVar(model=CiscoOrder, description="Tracked Cisco order to refresh.")

    class Meta:
        """Job metadata."""

        name = "Refresh tracked Cisco order"
        description = "Fetch the latest Cisco Commerce details for one tracked order."
        has_sensitive_variables = False

    def run(self, order):
        """Refresh the selected tracked order."""
        synchronizer = CiscoOrderSynchronizer(environment_override=order.environment)
        try:
            _, changes = synchronizer.sync_order_by_number(order.order_number, source=ChangeSourceChoices.MANUAL)
        except Exception as exc:
            synchronizer.record_sync_error(order, exc, source=ChangeSourceChoices.MANUAL)
            self.logger.exception("Failed refreshing %s: %s", order.order_number, exc)
            raise
        self.logger.info("Refreshed %s with %s detected changes.", order.order_number, len(changes))


class RefreshTrackedOrdersJob(Job):
    """Refresh all tracked Cisco orders."""

    class Meta:
        """Job metadata."""

        name = "Refresh all tracked Cisco orders"
        description = "Poll Cisco Commerce for every tracked order and update the local snapshots."
        has_sensitive_variables = False

    def run(self):
        """Refresh all tracked orders."""
        count = 0
        failures = 0
        for order in CiscoOrder.objects.filter(is_tracked=True).order_by("order_number"):
            synchronizer = CiscoOrderSynchronizer(environment_override=order.environment)
            try:
                _, changes = synchronizer.sync_order_by_number(order.order_number, source=ChangeSourceChoices.POLL)
                self.logger.info("Refreshed %s with %s changes.", order.order_number, len(changes))
                count += 1
            except Exception as exc:
                failures += 1
                synchronizer.record_sync_error(order, exc, source=ChangeSourceChoices.POLL)
                self.logger.exception("Failed refreshing %s: %s", order.order_number, exc)
        self.logger.info("Finished refreshing %s tracked orders with %s failures.", count, failures)


register_jobs(RefreshCiscoOrderJob, RefreshTrackedOrdersJob)
