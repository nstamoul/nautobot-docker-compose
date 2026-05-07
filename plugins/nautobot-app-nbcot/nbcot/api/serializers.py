"""API serializers for nbcot."""

from nautobot.apps.api import NautobotModelSerializer, TaggedModelSerializerMixin

from nbcot import models


class CiscoOrderLineSerializer(NautobotModelSerializer):
    """Serialize Cisco order line objects."""

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
