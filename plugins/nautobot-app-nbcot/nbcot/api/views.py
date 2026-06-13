"""API views for nbcot."""

from nautobot.apps.api import NautobotModelViewSet

from nbcot import filters, models
from nbcot.api import serializers


class CiscoOrderViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """CiscoOrder viewset."""

    queryset = models.CiscoOrder.objects.prefetch_related("lines", "updates")
    serializer_class = serializers.CiscoOrderSerializer
    filterset_class = filters.CiscoOrderFilterSet


class CiscoOrderLineViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """CiscoOrderLine viewset."""

    queryset = models.CiscoOrderLine.objects.select_related("order")
    serializer_class = serializers.CiscoOrderLineSerializer
    filterset_fields = (
        "order",
        "line_key",
        "line_number",
        "sku",
        "status",
        "shipment_status",
        "serial_number",
        "parent_serial_number",
        "mac_address",
        "imei_number",
        "instance_number",
        "license_key",
        "cloud_id",
        "contract_number",
        "carrier",
        "tracking_number",
        "tracking_url",
        "proof_of_delivery_url",
    )


class CiscoOrderUpdateViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """CiscoOrderUpdate viewset."""

    queryset = models.CiscoOrderUpdate.objects.select_related("order")
    serializer_class = serializers.CiscoOrderUpdateSerializer
    filterset_fields = ("order", "update_type", "source")
