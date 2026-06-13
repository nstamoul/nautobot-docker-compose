"""Views for nbcot."""

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView
from nautobot.core.views import generic
from nautobot.apps.ui import (
    Button,
    ObjectDetailContent,
    ObjectFieldsPanel,
    ObjectTextPanel,
    ObjectsTablePanel,
    Panel,
    SectionChoices,
)
from nautobot.apps.views import NautobotUIViewSet

from nbcot import filters, forms, models, tables
from nbcot.api import serializers
from nbcot.choices import ChangeSourceChoices
from nbcot.cisco.client import CiscoSettings
from nbcot.cisco.exceptions import NBCOTConfigurationError
from nbcot.cisco.line_items import build_line_tree
from nbcot.cisco.subscriptions import CiscoSubscriptionService
from nbcot.cisco.sync import CiscoOrderSynchronizer
from nbcot.exports import build_order_workbook, build_orders_workbook


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

        tracked_line_keys = request.POST.getlist("line_keys")
        if not tracked_line_keys and not request.POST.get("line_selection_submitted"):
            tracked_line_keys = None
        try:
            order, _changes = CiscoOrderSynchronizer(environment_override=environment).sync_order_by_number(
                order_number=order_number,
                source=ChangeSourceChoices.MANUAL,
                tracked_line_keys=tracked_line_keys,
            )
        except Exception as exc:  # pragma: no cover - live API failure path
            messages.error(request, f"Unable to track order {order_number}: {exc}")
            return redirect(
                f"{reverse('plugins:nbcot:order_search')}?environment={environment}&order_number={order_number}"
            )

        messages.success(request, f"Order {order.order_number} is now tracked.")
        return redirect(order.get_absolute_url())


class OrderPreviewView(PermissionRequiredMixin, TemplateView):
    """Render Cisco order details without tracking the order."""

    permission_required = "nbcot.view_ciscoorder"
    template_name = "nbcot/order_preview.html"

    def get_context_data(self, **kwargs):
        """Populate a read-only Cisco order preview."""
        context = super().get_context_data(**kwargs)
        default_environment = CiscoSettings.load().environment
        environment = self.request.GET.get("environment", default_environment).strip().lower() or default_environment
        order_number = self.request.GET.get("order_number", "").strip()
        snapshot = None
        error_message = None

        if order_number:
            try:
                snapshot = CiscoOrderSynchronizer(environment_override=environment).preview_order_by_number(order_number)
            except NBCOTConfigurationError as exc:
                error_message = str(exc)
            except Exception as exc:  # pragma: no cover - defensive for live API failures
                error_message = f"Unable to open order {order_number}: {exc}"
        else:
            error_message = "Order number is required to preview an order."

        context.update(
            {
                "error_message": error_message,
                "line_rows": build_line_tree(snapshot.lines) if snapshot else [],
                "order_number": order_number,
                "selected_environment": environment,
                "snapshot": snapshot,
            }
        )
        return context


class CiscoOrderLineTreePanel(Panel):
    """Render persisted Cisco order lines with the same controls as preview."""

    def render_body_content(self, context):
        """Render the reusable line tree partial for a saved order."""
        order = context.get("object") or context.get("obj")
        if order is None:
            return ""
        return render_to_string(
            "nbcot/inc/order_line_tree.html",
            {
                "empty_message": "No line items are stored for this order.",
                "line_rows": build_line_tree(order.lines.all()),
                "line_tree_id": f"nbcot-order-lines-{order.pk}",
                "tracking_form_action": reverse("plugins:nbcot:ciscoorder_line_tracking", kwargs={"pk": order.pk}),
                "tracking_mode": True,
                "tracking_submit_label": "Save Line Tracking",
            },
            request=context["request"],
        )


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


class ArchiveCiscoOrderView(PermissionRequiredMixin, View):
    """Archive a tracked order without deleting its history."""

    permission_required = "nbcot.change_ciscoorder"

    def get(self, request, pk):
        """Mark the order archived and redirect back to the order."""
        order = get_object_or_404(models.CiscoOrder, pk=pk)
        order.is_archived = True
        order.is_tracked = False
        order.validated_save()
        messages.success(request, f"Archived Cisco order {order.order_number}.")
        return redirect(order.get_absolute_url())


class UnarchiveCiscoOrderView(PermissionRequiredMixin, View):
    """Unarchive a Cisco order without re-enabling tracking implicitly."""

    permission_required = "nbcot.change_ciscoorder"

    def get(self, request, pk):
        """Mark the order unarchived and redirect back to the order."""
        order = get_object_or_404(models.CiscoOrder, pk=pk)
        order.is_archived = False
        order.validated_save()
        messages.success(request, f"Unarchived Cisco order {order.order_number}.")
        return redirect(order.get_absolute_url())


def _selected_orders(request):
    """Return the selected Cisco orders from a bulk action request."""
    pk_values = request.POST.getlist("pk")
    if not pk_values:
        return models.CiscoOrder.objects.none()
    return models.CiscoOrder.objects.filter(pk__in=pk_values).order_by("order_number")


def _bulk_return_url(request, action):
    """Return to the page that initiated the bulk action."""
    posted_return_url = request.POST.get("return_url", "")
    if posted_return_url.startswith("/"):
        return posted_return_url
    if action == "unarchive":
        return reverse("plugins:nbcot:ciscoorder_archived_list")
    return reverse("plugins:nbcot:ciscoorder_list")


class BulkCiscoOrderActionView(PermissionRequiredMixin, View):
    """Execute selected-order bulk actions."""

    permission_required = "nbcot.change_ciscoorder"
    allowed_actions = {"refresh", "archive", "unarchive", "untrack"}

    def post(self, request, action):
        """Apply a bulk action to selected Cisco orders."""
        if action not in self.allowed_actions:
            return HttpResponseBadRequest(f"Unsupported bulk action: {action}")
        orders = list(_selected_orders(request))
        if not orders:
            messages.warning(request, "Select at least one Cisco order first.")
            return redirect(_bulk_return_url(request, action))

        if action == "refresh":
            refreshed, failures = self._refresh_orders(orders)
            if failures:
                messages.warning(request, f"Refreshed {refreshed} Cisco orders with {failures} failures.")
            else:
                messages.success(request, f"Refreshed {refreshed} Cisco orders.")
        elif action == "archive":
            for order in orders:
                order.is_archived = True
                order.is_tracked = False
                order.validated_save()
            messages.success(request, f"Archived {len(orders)} Cisco orders.")
        elif action == "unarchive":
            for order in orders:
                order.is_archived = False
                order.validated_save()
            messages.success(request, f"Unarchived {len(orders)} Cisco orders.")
        elif action == "untrack":
            for order in orders:
                order.is_tracked = False
                order.validated_save()
            messages.success(request, f"Untracked {len(orders)} Cisco orders.")

        return redirect(_bulk_return_url(request, action))

    @staticmethod
    def _refresh_orders(orders):
        """Refresh selected orders and record sync errors without stopping the whole batch."""
        refreshed = 0
        failures = 0
        for order in orders:
            synchronizer = CiscoOrderSynchronizer(environment_override=order.environment)
            try:
                synchronizer.sync_order_by_number(order.order_number, source=ChangeSourceChoices.MANUAL)
                refreshed += 1
            except Exception as exc:  # pragma: no cover - live API failure path
                failures += 1
                synchronizer.record_sync_error(order, exc, source=ChangeSourceChoices.MANUAL)
        return refreshed, failures


def _xlsx_response(content: bytes, filename: str) -> HttpResponse:
    """Return an Excel response."""
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class ExportCiscoOrderView(PermissionRequiredMixin, View):
    """Export one tracked order to Excel."""

    permission_required = "nbcot.view_ciscoorder"

    def get(self, _request, pk):
        """Return an XLSX workbook for the selected order."""
        order = get_object_or_404(models.CiscoOrder.objects.prefetch_related("lines"), pk=pk)
        content = build_order_workbook(order)
        filename = f"Cisco_Order_{order.order_number}_{timezone.now():%Y%m%d%H%M%S}.xlsx"
        return _xlsx_response(content, filename)


class ExportSelectedCiscoOrdersView(PermissionRequiredMixin, View):
    """Export selected or filtered tracked orders to Excel."""

    permission_required = "nbcot.view_ciscoorder"

    def get(self, request):
        """Return an XLSX workbook for selected pks or the current filtered queryset."""
        pk_values = request.GET.getlist("pk")
        queryset = models.CiscoOrder.objects.prefetch_related("lines")
        if pk_values:
            queryset = queryset.filter(pk__in=pk_values)
        else:
            queryset = filters.CiscoOrderFilterSet(request.GET, queryset).qs
        content = build_orders_workbook(queryset.order_by("order_number"))
        filename = f"Cisco_Orders_{timezone.now():%Y%m%d%H%M%S}.xlsx"
        return _xlsx_response(content, filename)


class ArchivedCiscoOrderListView(generic.ObjectListView):
    """List archived Cisco orders."""

    queryset = models.CiscoOrder.objects.filter(is_archived=True).prefetch_related("lines", "updates")
    table = tables.CiscoOrderTable
    filterset = filters.ArchivedCiscoOrderFilterSet
    filterset_form = forms.CiscoOrderFilterForm
    template_name = "nbcot/ciscoorder_list.html"
    action_buttons = ()

    def get_extra_context(self, request, *args, **kwargs):
        """Add page metadata for the shared Cisco order list template."""
        return {
            "nbcot_archived_page": True,
            "title": "Archived Cisco Orders",
        }


class UpdateCiscoOrderLineTrackingView(PermissionRequiredMixin, View):
    """Persist per-line tracking selections for a saved Cisco order."""

    permission_required = "nbcot.change_ciscoorder"

    def post(self, request, pk):
        """Update the is_tracked flag on every line in the selected order."""
        order = get_object_or_404(models.CiscoOrder, pk=pk)
        selected_line_keys = set(request.POST.getlist("line_keys"))
        changed_count = 0

        with transaction.atomic():
            for line in order.lines.all():
                next_is_tracked = line.line_key in selected_line_keys
                if line.is_tracked == next_is_tracked:
                    continue
                line.is_tracked = next_is_tracked
                line.validated_save()
                changed_count += 1

            if selected_line_keys and not order.is_tracked:
                order.is_tracked = True
                order.validated_save()

        messages.success(
            request,
            f"Saved line tracking for Cisco order {order.order_number}: "
            f"{len(selected_line_keys)} selected, {changed_count} changed.",
        )
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
            Button(
                weight=120,
                label="Export",
                color="secondary",
                icon="mdi-download",
                link_name="plugins:nbcot:ciscoorder_export",
            ),
            Button(
                weight=130,
                label="Archive",
                color="danger",
                icon="mdi-archive",
                link_name="plugins:nbcot:ciscoorder_archive",
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
                    "project_number",
                    "account_name",
                    "account_number",
                    "status",
                    "status_detail",
                    "lifecycle_state",
                    "is_tracked",
                    "is_archived",
                    "web_order_url",
                    "cisco_sales_order_url",
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
            ObjectFieldsPanel(
                weight=115,
                section=SectionChoices.RIGHT_HALF,
                label="Local Tracking",
                fields=[
                    "notes",
                    "notification_recipients",
                    "notification_teams_webhook_url",
                ],
            ),
            CiscoOrderLineTreePanel(
                weight=200,
                section=SectionChoices.FULL_WIDTH,
                label="Line Items",
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
