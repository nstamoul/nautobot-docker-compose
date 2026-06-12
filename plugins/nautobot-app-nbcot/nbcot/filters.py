"""Filtering for nbcot."""

import django_filters
from django.db.models import Q
from nautobot.apps.filters import NautobotFilterSet

from nbcot import models


class CiscoOrderFilterSet(NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """Filter for CiscoOrder."""

    q = django_filters.CharFilter(method="search", label="Search")
    environment = django_filters.CharFilter(lookup_expr="iexact")
    order_number = django_filters.CharFilter(lookup_expr="icontains")
    customer_po_number = django_filters.CharFilter(lookup_expr="icontains")
    account_name = django_filters.CharFilter(lookup_expr="icontains")
    project_number = django_filters.CharFilter(lookup_expr="icontains")
    status = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        """Meta attributes for filter."""

        model = models.CiscoOrder
        fields = [
            "id",
            "environment",
            "order_number",
            "customer_po_number",
            "account_name",
            "project_number",
            "status",
            "is_tracked",
            "is_archived",
            "created",
        ]

    @property
    def qs(self):
        """Hide archived orders by default in the tracked-order list."""
        queryset = super().qs
        if "is_archived" not in self.data:
            queryset = queryset.filter(is_archived=False)
        return queryset

    def search(self, queryset, _name, value):
        """Search common order fields."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(order_number__icontains=value)
            | Q(customer_po_number__icontains=value)
            | Q(account_name__icontains=value)
            | Q(account_number__icontains=value)
            | Q(project_number__icontains=value)
            | Q(notes__icontains=value)
            | Q(status__icontains=value)
            | Q(status_detail__icontains=value)
            | Q(lifecycle_state__icontains=value)
            | Q(last_sync_status__icontains=value)
            | Q(last_sync_message__icontains=value)
            | Q(lines__line_number__icontains=value)
            | Q(lines__sku__icontains=value)
            | Q(lines__description__icontains=value)
            | Q(lines__status__icontains=value)
            | Q(lines__shipment_status__icontains=value)
            | Q(lines__serial_number__icontains=value)
            | Q(lines__mac_address__icontains=value)
            | Q(lines__instance_number__icontains=value)
            | Q(lines__ship_set__icontains=value)
            | Q(lines__carrier__icontains=value)
            | Q(lines__tracking_number__icontains=value)
            | Q(lines__tracking_url__icontains=value)
        ).distinct()


class ArchivedCiscoOrderFilterSet(CiscoOrderFilterSet):
    """Filter for archived CiscoOrder list views."""

    @property
    def qs(self):
        """Show archived orders by default on the archived-order list."""
        queryset = super(CiscoOrderFilterSet, self).qs
        if "is_archived" not in self.data:
            queryset = queryset.filter(is_archived=True)
        return queryset
