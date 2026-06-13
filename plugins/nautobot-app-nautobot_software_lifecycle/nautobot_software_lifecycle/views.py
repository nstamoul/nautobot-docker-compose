"""Views for nautobot_software_lifecycle."""

from nautobot.apps.views import NautobotUIViewSet
from nautobot.apps.ui import ObjectDetailContent, ObjectFieldsPanel, SectionChoices

from nautobot_software_lifecycle import filters, forms, models, tables
from nautobot_software_lifecycle.api import serializers


class SoftwareLicenseUIViewSet(NautobotUIViewSet):
    """ViewSet for SoftwareLicense views."""

    bulk_update_form_class = forms.SoftwareLicenseBulkEditForm
    filterset_class = filters.SoftwareLicenseFilterSet
    filterset_form_class = forms.SoftwareLicenseFilterForm
    form_class = forms.SoftwareLicenseForm
    lookup_field = "pk"
    queryset = models.SoftwareLicense.objects.all()
    serializer_class = serializers.SoftwareLicenseSerializer
    table_class = tables.SoftwareLicenseTable

    object_detail_content = ObjectDetailContent(
        panels=[
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields=[
                    "tenant",
                    "product_id",
                    "product_description",
                    "product_type",
                    "product_family",
                    "coverage",
                    "covered_line_status",
                    "contract_number",
                    "subscription_id",
                    "serial_number_pak",
                    "item_quantity",
                ],
            ),
            ObjectFieldsPanel(
                weight=200,
                section=SectionChoices.RIGHT_HALF,
                fields=[
                    "covered_line_start_date",
                    "covered_line_end_date",
                    "ship_date",
                    "last_date_of_support",
                    "last_renewal_date",
                    "warranty_end_date",
                    "end_of_product_sale_date",
                    "end_of_software_maintenance_date",
                ],
            ),
        ],
    )
