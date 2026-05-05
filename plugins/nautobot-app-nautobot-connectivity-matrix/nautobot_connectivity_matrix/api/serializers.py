"""REST API serializers for the Connectivity Matrix Diagram app."""

from rest_framework import serializers
from django.db.models import Q

from nautobot.apps.api import NautobotModelSerializer
from nautobot.dcim.models import Device, Interface

from ..models import ConnectionPlan, ConnectionPlanBatch


class ConnectionPlanBatchSerializer(NautobotModelSerializer):
    """Serializer for ConnectionPlanBatch model."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:nautobot_connectivity_matrix-api:connectionplanbatch-detail"
    )

    # Read-only computed fields
    connection_count = serializers.IntegerField(read_only=True)
    validated_count = serializers.IntegerField(read_only=True)
    executed_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ConnectionPlanBatch
        fields = [
            "id",
            "url",
            "name",
            "description",
            "tenant",
            "location",
            "default_device_type",
            "default_device_role",
            "default_platform",
            "default_device_status",
            "status",
            "connection_count",
            "validated_count",
            "executed_count",
            "created",
            "last_updated",
        ]


class ConnectionPlanSerializer(NautobotModelSerializer):
    """Serializer for ConnectionPlan model."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:nautobot_connectivity_matrix-api:connectionplan-detail"
    )

    # Display names for the grid
    device_a_display = serializers.CharField(read_only=True)
    device_b_display = serializers.CharField(read_only=True)
    interface_a_display = serializers.CharField(read_only=True)
    interface_b_display = serializers.CharField(read_only=True)

    class Meta:
        model = ConnectionPlan
        fields = [
            "id",
            "url",
            "batch",
            "row_order",
            "device_a",
            "device_a_name",
            "device_a_display",
            "interface_a",
            "interface_a_name",
            "interface_a_display",
            "sfp_a",
            "device_b",
            "device_b_name",
            "device_b_display",
            "interface_b",
            "interface_b_name",
            "interface_b_display",
            "sfp_b",
            "medium",
            "speed",
            "status",
            "validation_errors",
            "validation_warnings",
            "created_cable",
            "notes",
            "row_color",
            "created",
            "last_updated",
        ]


class ConnectionPlanGridSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for the Tabulator grid.

    Optimized for fast loading and inline editing.
    """

    # Display values for the grid
    device_a_display = serializers.CharField(read_only=True)
    device_b_display = serializers.CharField(read_only=True)
    interface_a_display = serializers.CharField(read_only=True)
    interface_b_display = serializers.CharField(read_only=True)

    # IDs for setting values
    device_a_id = serializers.PrimaryKeyRelatedField(
        source="device_a",
        queryset=Device.objects.all(),
        required=False,
        allow_null=True
    )
    device_b_id = serializers.PrimaryKeyRelatedField(
        source="device_b",
        queryset=Device.objects.all(),
        required=False,
        allow_null=True
    )
    interface_a_id = serializers.PrimaryKeyRelatedField(
        source="interface_a",
        queryset=Interface.objects.all(),
        required=False,
        allow_null=True
    )
    interface_b_id = serializers.PrimaryKeyRelatedField(
        source="interface_b",
        queryset=Interface.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = ConnectionPlan
        fields = [
            "id",
            "row_order",
            "device_a_id",
            "device_a_name",
            "device_a_display",
            "interface_a_id",
            "interface_a_name",
            "interface_a_display",
            "sfp_a",
            "device_b_id",
            "device_b_name",
            "device_b_display",
            "interface_b_id",
            "interface_b_name",
            "interface_b_display",
            "sfp_b",
            "medium",
            "speed",
            "status",
            "validation_errors",
            "validation_warnings",
            "notes",
            "row_color",
        ]
        read_only_fields = ["row_order"]

    def validate(self, attrs):
        attrs = super().validate(attrs)

        instance = getattr(self, "instance", None)
        instance_pk = getattr(instance, "pk", None)

        interface_a = attrs.get("interface_a", getattr(instance, "interface_a", None))
        interface_b = attrs.get("interface_b", getattr(instance, "interface_b", None))

        if interface_a and interface_b and interface_a == interface_b:
            raise serializers.ValidationError({"interface_b_id": "Interface B cannot be the same as Interface A."})

        qs = ConnectionPlan.objects.exclude(status__in=["executed", "failed"])
        if instance_pk:
            qs = qs.exclude(pk=instance_pk)

        def _conflict_exists(iface):
            return qs.filter(Q(interface_a=iface) | Q(interface_b=iface)).exists()

        if interface_a and _conflict_exists(interface_a):
            raise serializers.ValidationError(
                {"interface_a_id": f"Interface '{interface_a}' is already used in another pending plan."}
            )

        if interface_b and _conflict_exists(interface_b):
            raise serializers.ValidationError(
                {"interface_b_id": f"Interface '{interface_b}' is already used in another pending plan."}
            )

        return attrs


class AvailableInterfaceSerializer(serializers.Serializer):
    """Serializer for available interface dropdown options."""

    value = serializers.UUIDField(source="id")
    label = serializers.CharField(source="name")
    type = serializers.CharField(source="type")


class BulkConnectionPlanSerializer(serializers.Serializer):
    """Serializer for bulk creating connection plans."""

    batch_id = serializers.UUIDField()
    rows = ConnectionPlanGridSerializer(many=True)


class BatchActionResultSerializer(serializers.Serializer):
    """Serializer for batch action results."""

    success_count = serializers.IntegerField()
    error_count = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.DictField())
