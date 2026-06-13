"""UI views for the Connectivity Matrix Diagram app."""

import logging
import time

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse, HttpResponseBadRequest
from django.urls import reverse
from django.views import View
from django.views.generic import FormView, TemplateView

from nautobot.core.views import generic
from nautobot.dcim.filters import DeviceFilterSet
from nautobot.dcim.models import Device, DeviceType, Location, ModuleType, Platform
from nautobot.extras.models import Role, Status
from nautobot.tenancy.models import Tenant

from .models import ConnectionPlanBatch, ConnectionPlan
from .forms import ConnectionPlanBatchForm, StackPlanImportForm
from .stack_plan import import_stacks_from_xlsx
from .tables import ConnectionPlanBatchTable
from .filters import ConnectionPlanBatchFilterSet

logger = logging.getLogger(__name__)


PRESENTATION_QUERY_PARAMS = {
    "clear_view",
    "display",
    "hide",
    "page",
    "per_page",
    "saved_view",
    "sort",
    "tab",
}


class BatchListView(generic.ObjectListView):
    """List view for connection plan batches."""

    queryset = ConnectionPlanBatch.objects.all()
    table = ConnectionPlanBatchTable
    filterset = ConnectionPlanBatchFilterSet
    action_buttons = ("add",)


class BatchCreateView(generic.ObjectEditView):
    """Create view for connection plan batch."""

    queryset = ConnectionPlanBatch.objects.all()
    model_form = ConnectionPlanBatchForm
    default_return_url = "plugins:nautobot_connectivity_matrix:connectionplanbatch_list"


class BatchDetailView(generic.ObjectView):
    """Detail view for connection plan batch."""

    queryset = ConnectionPlanBatch.objects.all()

    def get_extra_context(self, request, instance):
        """Add connection plans to context."""
        plans = instance.connection_plans.all()
        return {
            "plans": plans,
            "matrix_url": reverse(
                "plugins:nautobot_connectivity_matrix:matrix",
                kwargs={"pk": instance.pk}
            ),
        }


class BatchEditView(generic.ObjectEditView):
    """Edit view for connection plan batch."""

    queryset = ConnectionPlanBatch.objects.all()
    model_form = ConnectionPlanBatchForm


class BatchDeleteView(generic.ObjectDeleteView):
    """Delete view for connection plan batch."""

    queryset = ConnectionPlanBatch.objects.all()
    default_return_url = "plugins:nautobot_connectivity_matrix:connectionplanbatch_list"

class MatrixView(generic.ObjectView):
    """
    The main spreadsheet-like matrix view.

    Uses Tabulator.js for an Excel-like editing experience.
    """

    queryset = ConnectionPlanBatch.objects.all()
    template_name = "nautobot_connectivity_matrix/matrix.html"

    def get_extra_context(self, request, instance):
        """Add data needed for the Tabulator grid."""
        device_ct = ContentType.objects.get(app_label="dcim", model="device")
        device_statuses = list(
            Status.objects.filter(content_types__app_label="dcim", content_types__model="device")
            .order_by("name")
            .distinct()
            .values("id", "name")
        )
        device_roles = list(Role.objects.filter(content_types=device_ct).order_by("name").values("id", "name"))
        return {
            "batch": instance,
            "static_cache_buster": int(time.time()),
            "matrix_config": {
                "batchId": str(instance.pk),
                "apiBaseUrl": "/api/plugins/nautobot-connectivity-matrix",
                "mediumChoices": [
                    {"value": c[0], "label": c[1]}
                    for c in ConnectionPlan._meta.get_field("medium").choices
                ],
                "speedChoices": [
                    {"value": c[0], "label": c[1]}
                    for c in ConnectionPlan._meta.get_field("speed").choices
                ],
                "tenantId": str(instance.tenant.pk) if instance.tenant else None,
                "locationId": str(instance.location.pk) if instance.location else None,
                "deviceStatusChoices": [
                    {"value": str(s["id"]), "label": s["name"]} for s in device_statuses
                ],
                "deviceRoleChoices": [
                    {"value": str(r["id"]), "label": r["name"]} for r in device_roles
                ],
            },
        }


class StackPlanView(LoginRequiredMixin, TemplateView):
    """Online spreadsheet-style UI for planning stack/device creation."""

    template_name = "nautobot_connectivity_matrix/stack_plan.html"

    def get_context_data(self, **kwargs):
        """Add grid choice data for the stack builder."""
        context = super().get_context_data(**kwargs)
        device_ct = ContentType.objects.get(app_label="dcim", model="device")
        statuses = list(
            Status.objects.filter(content_types=device_ct)
            .order_by("name")
            .distinct()
            .values("id", "name")
        )
        planned = next((s for s in statuses if s["name"].lower() == "planned"), statuses[0] if statuses else None)

        def _choices(queryset, label_field="name", extra=None):
            rows = []
            for obj in queryset:
                item = {"value": str(obj.pk), "label": getattr(obj, label_field)}
                if extra:
                    item.update(extra(obj))
                rows.append(item)
            return rows

        context["static_cache_buster"] = int(time.time())
        context["stack_plan_config"] = {
            "apiBaseUrl": "/api/plugins/nautobot-connectivity-matrix",
            "defaults": {
                "status": str(planned["id"]) if planned else "",
            },
            "choices": {
                "tenants": _choices(Tenant.objects.order_by("name")),
                "locations": _choices(
                    Location.objects.select_related("tenant").order_by("name"),
                    extra=lambda location: {"tenant": str(location.tenant_id) if location.tenant_id else ""},
                ),
                "statuses": [{"value": str(s["id"]), "label": s["name"]} for s in statuses],
                "roles": _choices(Role.objects.filter(content_types=device_ct).order_by("name")),
                "platforms": _choices(Platform.objects.order_by("name")),
                "deviceTypes": _choices(DeviceType.objects.order_by("model"), "model"),
                "moduleTypes": _choices(ModuleType.objects.order_by("model"), "model"),
            },
        }
        return context


class DeviceCoverageExportView(LoginRequiredMixin, View):
    """Download a coverage/EOX workbook for the current Device list filters."""

    eox_source = "dlm"
    filename_part = "dlm_eox"

    def get(self, request):
        helpers = self._coverage_helpers()
        now = time.strftime("%d-%m-%Y_%H.%M.%S")

        filter_data = request.GET.copy()
        for key in PRESENTATION_QUERY_PARAMS:
            filter_data.pop(key, None)

        queryset = Device.objects.restrict(request.user, "view").all()
        filterset = DeviceFilterSet(data=filter_data, queryset=queryset, request=request)
        if not filterset.is_valid():
            return HttpResponseBadRequest(filterset.errors.as_json())

        device_pks = list(filterset.qs.values_list("pk", flat=True))
        device_queryset = Device.objects.filter(pk__in=device_pks)
        filter_kwargs = {"pk__in": device_pks}
        module_filter_kwargs = {"device__in": device_queryset}

        if self.eox_source == "cf":
            devices = helpers["get_coverage_and_cf_eox_facts_from_orm"](logger, filter_kwargs)
            module_rows = helpers["get_NB_MODULE_COVERAGE_ROWS"](
                module_filter_kwargs,
                start_device_id=len(devices),
            )
        else:
            devices, inventory_pid_notices = helpers["get_coverage_and_dlm_eox_facts_from_orm"](logger, filter_kwargs)
            module_rows = helpers["get_NB_MODULE_COVERAGE_ROWS_DLM"](
                module_filter_kwargs,
                inventory_pid_notices,
                start_device_id=len(devices),
            )

        coverage_dict = helpers["get_NB_DEVICE_COVERAGE_DICT"](devices)
        for index, module_row in enumerate(module_rows, start=1):
            coverage_dict[f"module:{index}"] = [module_row]

        file_content = helpers["output_NB_DEVICE_COVERAGE_DICT_to_excel"](coverage_dict, now)
        filename = f"device_coverage_inventory_{self.filename_part}_{now}.xlsx"
        response = HttpResponse(
            file_content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @staticmethod
    def _coverage_helpers():
        import sys
        from pathlib import Path

        jobs_repo = Path("/opt/nautobot/git/shms_nautobot_jobs_repo")
        if jobs_repo.exists() and str(jobs_repo) not in sys.path:
            sys.path.insert(0, str(jobs_repo))

        from jobs.device_inventory_coverage import device_inventory_coverage as coverage

        return {
            "get_NB_DEVICE_COVERAGE_DICT": coverage.get_NB_DEVICE_COVERAGE_DICT,
            "get_NB_MODULE_COVERAGE_ROWS": coverage.get_NB_MODULE_COVERAGE_ROWS,
            "get_NB_MODULE_COVERAGE_ROWS_DLM": coverage.get_NB_MODULE_COVERAGE_ROWS_DLM,
            "get_coverage_and_cf_eox_facts_from_orm": coverage.get_coverage_and_cf_eox_facts_from_orm,
            "get_coverage_and_dlm_eox_facts_from_orm": coverage.get_coverage_and_dlm_eox_facts_from_orm,
            "output_NB_DEVICE_COVERAGE_DICT_to_excel": coverage.output_NB_DEVICE_COVERAGE_DICT_to_excel,
        }


class DeviceCoverageCFExportView(DeviceCoverageExportView):
    """Download a custom-field EOX coverage workbook for the current Device list filters."""

    eox_source = "cf"
    filename_part = "cf_eox"
