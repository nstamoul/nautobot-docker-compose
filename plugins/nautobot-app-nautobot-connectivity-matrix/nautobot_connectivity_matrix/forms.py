"""Forms for the Connectivity Matrix Diagram app."""

from django import forms

from nautobot.apps.forms import NautobotModelForm, DynamicModelChoiceField
from nautobot.dcim.models import DeviceType, Location, Platform
from nautobot.extras.models import Role, Status
from nautobot.tenancy.models import Tenant

from .models import ConnectionPlanBatch, ConnectionPlan


class ConnectionPlanBatchForm(NautobotModelForm):
    """Form for creating/editing a connection plan batch."""

    tenant = DynamicModelChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        help_text="Scope this batch to a specific tenant"
    )
    location = DynamicModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        query_params={"tenant": "$tenant"},
        help_text="Scope this batch to a specific location"
    )
    default_device_type = DynamicModelChoiceField(
        queryset=DeviceType.objects.all(),
        required=False,
        help_text="Device type to use when materializing unresolved typed device names",
    )
    default_device_role = DynamicModelChoiceField(
        queryset=Role.objects.all(),
        required=False,
        help_text="Role to use when materializing unresolved typed device names",
    )
    default_platform = DynamicModelChoiceField(
        queryset=Platform.objects.all(),
        required=False,
        help_text="Optional platform to use when materializing unresolved typed device names",
    )
    default_device_status = DynamicModelChoiceField(
        queryset=Status.objects.all(),
        required=False,
        help_text="Status to use when materializing unresolved typed device names",
    )

    class Meta:
        model = ConnectionPlanBatch
        fields = [
            "name",
            "description",
            "tenant",
            "location",
            "default_device_type",
            "default_device_role",
            "default_platform",
            "default_device_status",
            "status",
        ]


class ConnectionPlanForm(NautobotModelForm):
    """Form for creating/editing a single connection plan."""

    class Meta:
        model = ConnectionPlan
        fields = [
            "device_a",
            "device_a_name",
            "interface_a",
            "interface_a_name",
            "sfp_a",
            "device_b",
            "device_b_name",
            "interface_b",
            "interface_b_name",
            "sfp_b",
            "medium",
            "speed",
            "notes",
        ]


class StackPlanImportForm(forms.Form):
    """Upload form for stack-plan XLSX imports."""

    stack_plan_file = forms.FileField(required=True, help_text="Upload a stack-plan XLSX (sheet 'stack_plan').")


class MatrixImportForm(forms.Form):
    """Upload form for importing matrix XLSX into a batch."""

    matrix_file = forms.FileField(required=True, help_text="Upload a matrix XLSX (sheet 'matrix').")
    replace_existing = forms.BooleanField(required=False, initial=False, help_text="Delete existing rows first.")
