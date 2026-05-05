"""Tables for nautobot_software_lifecycle."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, ButtonsColumn, ToggleColumn

from nautobot_software_lifecycle import models


class SoftwareLicenseTable(BaseTable):
    # pylint: disable=R0903
    """Table for list view."""

    pk = ToggleColumn()
    product_id = tables.Column(linkify=True)
    tenant = tables.Column(linkify=True)
    actions = ButtonsColumn(
        models.SoftwareLicense,
        pk_field="pk",
    )

    class Meta(BaseTable.Meta):
        """Meta attributes."""

        model = models.SoftwareLicense
        fields = (
            "pk",
            "tenant",
            "product_id",
            "product_description",
            "product_type",
            "coverage",
            "covered_line_status",
            "contract_number",
            "subscription_id",
            "covered_line_start_date",
            "covered_line_end_date",
            "last_date_of_support",
            "warranty_end_date",
            "item_quantity",
        )

        default_columns = (
            "pk",
            "tenant",
            "product_id",
            "product_description",
            "product_type",
            "coverage",
            "covered_line_end_date",
            "last_date_of_support",
        )
