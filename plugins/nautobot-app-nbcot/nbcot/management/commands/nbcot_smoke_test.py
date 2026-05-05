"""Run a basic Cisco Commerce smoke test."""

import json

from django.core.management.base import BaseCommand, CommandError

from nbcot.cisco.sync import CiscoOrderSynchronizer


class Command(BaseCommand):
    """Smoke-test Cisco auth plus one useful API call."""

    help = "Authenticate to Cisco Commerce and run one search or detail call."

    def add_arguments(self, parser):
        """Add CLI arguments."""
        parser.add_argument("--environment", choices=["poe", "prod", "uat"], default="poe", help="Cisco environment.")
        parser.add_argument("--order-number", help="Cisco order number to fetch and normalize.")
        parser.add_argument("--customer-po-number", help="Customer PO number to search.")
        parser.add_argument("--account-name", help="Account name to search.")
        parser.add_argument("--status", help="Status to search.")

    def handle(self, *args, **options):
        """Run the smoke test."""
        synchronizer = CiscoOrderSynchronizer(environment_override=options["environment"])
        if options["order_number"]:
            order, changes = synchronizer.sync_order_by_number(options["order_number"], source="manual")
            self.stdout.write(self.style.SUCCESS(f"Fetched order {order.order_number}"))
            self.stdout.write(json.dumps({"changes": len(changes), "payload_keys": sorted(order.raw_payload.keys())}, indent=2))
            return

        search_filters = {
            key: options[key]
            for key in ("customer_po_number", "account_name", "status")
            if options.get(key)
        }
        if not search_filters:
            raise CommandError("Provide --order-number or at least one search filter.")

        results = synchronizer.search_orders(search_filters)
        self.stdout.write(self.style.SUCCESS(f"Received {len(results)} search results."))
        preview = [result.__dict__ for result in results[:5]]
        self.stdout.write(json.dumps(preview, default=str, indent=2))
