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
            "status",
            "is_tracked",
            "created",
        ]

    def search(self, queryset, _name, value):
        """Search common order fields."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(order_number__icontains=value)
            | Q(customer_po_number__icontains=value)
            | Q(account_name__icontains=value)
            | Q(account_number__icontains=value)
            | Q(status__icontains=value)
        )
