"""API serializers for nbcot."""

from nautobot.apps.api import NautobotModelSerializer, TaggedModelSerializerMixin
from rest_framework import serializers

from nbcot import models


class CiscoOrderLineSerializer(NautobotModelSerializer):
    """Serialize Cisco order line objects."""

    serial_numbers = serializers.SerializerMethodField()
    parent_serial_numbers = serializers.SerializerMethodField()
    mac_addresses = serializers.SerializerMethodField()

    def get_serial_numbers(self, obj):
        """Return all serial numbers from Cisco serialNumberAttributes."""
        return obj.serial_numbers

    def get_parent_serial_numbers(self, obj):
        """Return all parent serial numbers from Cisco serialNumberAttributes."""
        return obj.parent_serial_numbers

    def get_mac_addresses(self, obj):
        """Return all MAC addresses from Cisco serialNumberAttributes."""
        return obj.mac_addresses

    class Meta:
        """Meta attributes."""

        model = models.CiscoOrderLine
        fields = "__all__"


class CiscoOrderUpdateSerializer(NautobotModelSerializer):
    """Serialize Cisco order update objects."""

    class Meta:
        """Meta attributes."""

        model = models.CiscoOrderUpdate
        fields = "__all__"


class CiscoOrderSerializer(NautobotModelSerializer, TaggedModelSerializerMixin):  # pylint: disable=too-many-ancestors
    """CiscoOrder serializer."""

    lines = CiscoOrderLineSerializer(many=True, read_only=True)
    updates = CiscoOrderUpdateSerializer(many=True, read_only=True)

    class Meta:
        """Meta attributes."""

        model = models.CiscoOrder
        fields = "__all__"
