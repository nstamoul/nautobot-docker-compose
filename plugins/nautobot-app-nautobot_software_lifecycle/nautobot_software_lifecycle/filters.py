"""Filtering for nautobot_software_lifecycle."""

from nautobot.apps.filters import NautobotFilterSet, SearchFilter

from nautobot_software_lifecycle import models


class SoftwareLicenseFilterSet(NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """Filter for SoftwareLicense."""

    q = SearchFilter(
        filter_predicates={
            "product_id": "icontains",
            "product_description": "icontains",
            "contract_number": "icontains",
            "serial_number_pak": "icontains",
        },
    )

    class Meta:
        """Meta attributes for filter."""

        model = models.SoftwareLicense
        fields = [
            "tenant",
            "product_id",
            "product_type",
            "product_family",
            "coverage",
            "covered_line_status",
            "contract_number",
            "subscription_id",
        ]
