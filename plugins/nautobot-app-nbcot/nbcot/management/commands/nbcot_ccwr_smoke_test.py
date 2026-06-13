"""Run a basic CCW-R subscription smoke test."""

import json

from django.core.management.base import BaseCommand, CommandError

from nbcot.cisco.subscriptions import CiscoSubscriptionService


class Command(BaseCommand):
    """Smoke-test CCW-R subscription lookups."""

    help = "Query Cisco CCW-R subscription search/detail operations."

    def add_arguments(self, parser):
        """Add CLI arguments."""
        parser.add_argument("--environment", choices=["prod", "poe", "uat"], default="prod", help="Cisco environment.")
        parser.add_argument("--subscription-identifier", help="Exact subscription ID / contract number candidate.")
        parser.add_argument("--end-customer-name", help="End customer party name.")
        parser.add_argument("--end-customer-site-id", help="End customer install site ID.")
        parser.add_argument("--bill-to-id", help="Bill-to party ID.")
        parser.add_argument("--from-date", default="2022-01-01", help="From date for CCW-R search.")
        parser.add_argument("--to-date", default="2035-12-31", help="To date for CCW-R search.")
        parser.add_argument("--status", help="Optional subscription status.")
        parser.add_argument("--pak-serial-number", help="Local line filter for serial/PAK/instance.")
        parser.add_argument("--so-mso-number", help="Local line filter for sales/web order.")
        parser.add_argument("--po-mpo-number", help="Local line filter for purchase order.")
        parser.add_argument("--line-end-customer", help="Local line filter for line end customer.")

    def handle(self, *args, **options):
        """Run the smoke test."""
        service = CiscoSubscriptionService(environment_override=options["environment"])
        search_filters = {
            key: options[key]
            for key in (
                "subscription_identifier",
                "end_customer_name",
                "end_customer_site_id",
                "bill_to_id",
                "from_date",
                "to_date",
                "status",
            )
            if options.get(key)
        }
        line_filters = {
            key: options[key]
            for key in ("pak_serial_number", "so_mso_number", "po_mpo_number", "line_end_customer")
            if options.get(key)
        }

        if options.get("subscription_identifier"):
            try:
                detail = service.get_detail(search_filters)
            except Exception as exc:
                raise CommandError(str(exc)) from exc
            if not detail:
                raise CommandError("No subscription detail returned.")
            lines = detail.filtered_lines(line_filters)
            self.stdout.write(self.style.SUCCESS(f"Fetched CCW-R detail for {detail.identifier}"))
            self.stdout.write(
                json.dumps(
                    {
                        "identifier": detail.identifier,
                        "name": detail.name,
                        "status": detail.status,
                        "line_count": len(lines),
                        "lines": [line.__dict__ for line in lines[:5]],
                    },
                    default=str,
                    indent=2,
                )
            )
            return

        if not search_filters:
            raise CommandError("Provide at least one search filter or an exact --subscription-identifier.")

        try:
            results = service.search(search_filters)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Received {len(results)} CCW-R search results."))
        self.stdout.write(json.dumps([result.__dict__ for result in results[:10]], default=str, indent=2))
