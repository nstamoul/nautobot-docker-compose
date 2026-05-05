"""Views for nbcot."""

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from nautobot.apps.ui import (
    Button,
    ObjectDetailContent,
    ObjectFieldsPanel,
    ObjectsTablePanel,
    ObjectTextPanel,
    SectionChoices,
)
from nautobot.apps.views import NautobotUIViewSet

from nbcot import filters, forms, models, tables
from nbcot.api import serializers
from nbcot.choices import ChangeSourceChoices
from nbcot.cisco.client import CiscoSettings
from nbcot.cisco.exceptions import NBCOTConfigurationError
from nbcot.cisco.subscriptions import CiscoSubscriptionService
from nbcot.cisco.sync import CiscoOrderSynchronizer


class OrderSearchView(PermissionRequiredMixin, TemplateView):
    """Render the ad hoc order search workflow."""

    permission_required = "nbcot.view_ciscoorder"
    template_name = "nbcot/order_search.html"

    def get_context_data(self, **kwargs):
        """Populate the search form and optional results."""
        context = super().get_context_data(**kwargs)
        default_environment = CiscoSettings.load().environment
        form = forms.OrderSearchForm(self.request.GET or None, initial={"environment": default_environment})
        results = []
        error_message = None
        selected_environment = default_environment
        if self.request.GET:
            if any(value for key, value in self.request.GET.items() if key != "environment"):
                if form.is_valid():
                    selected_environment = form.selected_environment()
                    try:
                        results = CiscoOrderSynchronizer(environment_override=selected_environment).search_orders(
                            form.cleaned_filters()
                        )
                    except NBCOTConfigurationError as exc:
                        error_message = str(exc)
                    except Exception as exc:  # pragma: no cover - defensive for live API failures
                        error_message = f"Search failed: {exc}"
                else:
                    error_message = "Search form is invalid."
        context.update(
            {
                "form": form,
                "results": results,
                "selected_environment": selected_environment,
                "tracked_orders": models.CiscoOrder.objects.filter(is_tracked=True)[:10],
                "error_message": error_message,
            }
        )
        return context


class TrackCiscoOrderView(PermissionRequiredMixin, View):
    """Track an order returned from ad hoc Cisco search."""

    permission_required = "nbcot.add_ciscoorder"

    def post(self, request):
        """Fetch details for an order and persist it."""
        order_number = request.POST.get("order_number", "").strip()
        environment = request.POST.get("environment", "").strip().lower() or CiscoSettings.load().environment
        if not order_number:
            messages.error(request, "Order number is required to start tracking.")
            return redirect("plugins:nbcot:order_search")

        try:
            order, _changes = CiscoOrderSynchronizer(environment_override=environment).sync_order_by_number(
                order_number=order_number,
                source=ChangeSourceChoices.MANUAL,
            )
        except Exception as exc:  # pragma: no cover - live API failure path
            messages.error(request, f"Unable to track order {order_number}: {exc}")
            return redirect(
                f"{reverse('plugins:nbcot:order_search')}?environment={environment}&order_number={order_number}"
            )

        messages.success(request, f"Order {order.order_number} is now tracked.")
        return redirect(order.get_absolute_url())


class CCWRSubscriptionSearchView(PermissionRequiredMixin, TemplateView):
    """Render the CCW-R subscription lookup workflow."""

    permission_required = "nbcot.view_ciscoorder"
    template_name = "nbcot/subscription_search.html"

    def get_context_data(self, **kwargs):
        """Populate the CCW-R search form, results, and optional detail view."""
        context = super().get_context_data(**kwargs)
        default_environment = CiscoSettings.load().environment
        form = forms.CCWRSubscriptionSearchForm(self.request.GET or None, initial={"environment": default_environment})
        results = []
        detail = None
        detail_lines = []
        error_message = None
        selected_environment = default_environment

        if self.request.GET:
            if any(value for key, value in self.request.GET.items() if key != "environment"):
                if form.is_valid():
                    selected_environment = form.selected_environment()
                    service = CiscoSubscriptionService(environment_override=selected_environment)
                    search_filters = form.cleaned_search_filters()
                    line_filters = form.cleaned_line_filters()
                    try:
                        if search_filters.get("subscription_identifier"):
                            detail = service.get_detail(search_filters)
                            if detail:
                                detail_lines = detail.filtered_lines(line_filters)
                            else:
                                error_message = "No CCW-R subscription details were returned for the supplied identifier."
                        else:
                            results = service.search(search_filters)
                    except NBCOTConfigurationError as exc:
                        error_message = str(exc)
                    except Exception as exc:  # pragma: no cover - defensive for live API failures
                        error_message = f"CCW-R search failed: {exc}"
                else:
                    error_message = "CCW-R search form is invalid."

        context.update(
            {
                "form": form,
                "results": results,
                "detail": detail,
                "detail_lines": detail_lines,
                "selected_environment": selected_environment,
                "error_message": error_message,
            }
        )
        return context


class RefreshCiscoOrderView(PermissionRequiredMixin, View):
    """Refresh a tracked order from Cisco."""

    permission_required = "nbcot.change_ciscoorder"

    def get(self, request, pk):
        """Refresh the selected order and redirect back to the detail page."""
        order = get_object_or_404(models.CiscoOrder, pk=pk)
        try:
            CiscoOrderSynchronizer(environment_override=order.environment).sync_order_by_number(
                order_number=order.order_number,
                source=ChangeSourceChoices.MANUAL,
            )
            messages.success(request, f"Refreshed Cisco order {order.order_number}.")
        except Exception as exc:  # pragma: no cover - live API failure path
            messages.error(request, f"Refresh failed for {order.order_number}: {exc}")
        return redirect(order.get_absolute_url())


class ToggleTrackingView(PermissionRequiredMixin, View):
    """Enable or disable tracking for a persisted order."""

    permission_required = "nbcot.change_ciscoorder"

    def get(self, request, pk):
        """Toggle tracking and redirect back to the order."""
        order = get_object_or_404(models.CiscoOrder, pk=pk)
        order.is_tracked = not order.is_tracked
        order.validated_save()
        action = "enabled" if order.is_tracked else "disabled"
        messages.success(request, f"Tracking {action} for Cisco order {order.order_number}.")
        return redirect(order.get_absolute_url())


class CiscoOrderUIViewSet(NautobotUIViewSet):
    """ViewSet for CiscoOrder views."""

    bulk_update_form_class = forms.CiscoOrderBulkEditForm
    filterset_class = filters.CiscoOrderFilterSet
    filterset_form_class = forms.CiscoOrderFilterForm
    form_class = forms.CiscoOrderForm
    lookup_field = "pk"
    queryset = models.CiscoOrder.objects.prefetch_related("lines", "updates")
    serializer_class = serializers.CiscoOrderSerializer
    table_class = tables.CiscoOrderTable

    object_detail_content = ObjectDetailContent(
        extra_buttons=[
            Button(
                weight=100,
                label="Refresh",
                color="primary",
                icon="mdi-refresh",
                link_name="plugins:nbcot:ciscoorder_refresh",
            ),
            Button(
                weight=110,
                label="Toggle Tracking",
                color="warning",
                icon="mdi-toggle-switch",
                link_name="plugins:nbcot:ciscoorder_toggle_tracking",
            ),
        ],
        panels=[
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                label="Order Summary",
                fields=[
                    "order_number",
                    "environment",
                    "customer_po_number",
                    "account_name",
                    "account_number",
                    "status",
                    "status_detail",
                    "lifecycle_state",
                    "is_tracked",
                    "open_exception_count",
                ],
            ),
            ObjectFieldsPanel(
                weight=110,
                section=SectionChoices.RIGHT_HALF,
                label="Milestones",
                fields=[
                    "requested_delivery_date",
                    "promised_delivery_date",
                    "estimated_delivery_date",
                    "ordered_at",
                    "last_event_at",
                    "last_synced_at",
                    "last_sync_status",
                    "last_sync_message",
                ],
            ),
            ObjectsTablePanel(
                weight=200,
                section=SectionChoices.FULL_WIDTH,
                label="Line Items",
                table_class=tables.CiscoOrderLineTable,
                table_attribute="lines",
                related_field_name="order",
                enable_related_link=False,
            ),
            ObjectsTablePanel(
                weight=210,
                section=SectionChoices.FULL_WIDTH,
                label="Tracked Changes",
                table_class=tables.CiscoOrderUpdateTable,
                table_attribute="updates",
                related_field_name="order",
                enable_related_link=False,
            ),
            ObjectTextPanel(
                weight=220,
                section=SectionChoices.FULL_WIDTH,
                label="Raw Cisco Payload",
                object_field="raw_payload",
                render_as=ObjectTextPanel.RenderOptions.JSON,
            ),
        ],
    )
