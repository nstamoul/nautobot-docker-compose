"""FilterSets for the Connectivity Matrix Diagram app."""

import django_filters

from nautobot.apps.filters import NautobotFilterSet, SearchFilter
from nautobot.dcim.models import Location
from nautobot.tenancy.models import Tenant

from .models import ConnectionPlanBatch, ConnectionPlan


class ConnectionPlanBatchFilterSet(NautobotFilterSet):
    """FilterSet for ConnectionPlanBatch model."""

    q = SearchFilter(filter_predicates={"name": "icontains"})

    tenant = django_filters.ModelChoiceFilter(
        queryset=Tenant.objects.all(),
        field_name="tenant",
        label="Tenant",
    )
    location = django_filters.ModelChoiceFilter(
        queryset=Location.objects.all(),
        field_name="location",
        label="Location",
    )
    status = django_filters.ChoiceFilter(
        choices=[
            ("pending", "Pending Review"),
            ("approved", "Approved"),
            ("executing", "Executing"),
            ("completed", "Completed"),
            ("partial", "Partially Completed"),
        ]
    )

    class Meta:
        model = ConnectionPlanBatch
        fields = ["name", "tenant", "location", "status"]


class ConnectionPlanFilterSet(NautobotFilterSet):
    """FilterSet for ConnectionPlan model."""

    batch = django_filters.ModelChoiceFilter(
        queryset=ConnectionPlanBatch.objects.all(),
        field_name="batch",
        label="Batch",
    )
    status = django_filters.ChoiceFilter(
        choices=[
            ("draft", "Draft"),
            ("validated", "Validated"),
            ("approved", "Approved"),
            ("executed", "Executed"),
            ("conflict", "Conflict"),
            ("failed", "Failed"),
        ]
    )
    medium = django_filters.ChoiceFilter(
        choices=[
            ("RJ45", "RJ45/Copper"),
            ("SMF", "Singlemode Fiber"),
            ("MMF", "Multimode Fiber"),
            ("DAC", "Direct Attach Copper"),
            ("AOC", "Active Optical Cable"),
            ("STACK", "Stack Cable"),
        ]
    )

    class Meta:
        model = ConnectionPlan
        fields = ["batch", "status", "medium", "speed"]
