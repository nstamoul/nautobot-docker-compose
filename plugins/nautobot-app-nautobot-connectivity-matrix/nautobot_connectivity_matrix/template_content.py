"""Template extensions for Nautobot core pages."""

from django.urls import reverse
from django.utils.html import format_html
from nautobot.apps.ui import TemplateExtension


class DeviceCoverageExportListButtons(TemplateExtension):
    """Add filtered coverage export buttons to the Device list view."""

    model = "dcim.device"

    def list_buttons(self):
        query_string = self.context["request"].GET.urlencode()
        suffix = f"?{query_string}" if query_string else ""
        dlm_url = f"{reverse('plugins:nautobot_connectivity_matrix:device_coverage_export_dlm')}{suffix}"
        cf_url = f"{reverse('plugins:nautobot_connectivity_matrix:device_coverage_export_cf')}{suffix}"

        return format_html(
            """
            <div class="btn-group">
                <a class="btn btn-primary" href="{}">
                    <span class="mdi mdi-download" aria-hidden="true"></span>
                    Export DLM EOX
                </a>
                <a class="btn btn-outline-primary" href="{}">
                    <span class="mdi mdi-download" aria-hidden="true"></span>
                    Export CF EOX
                </a>
            </div>
            """,
            dlm_url,
            cf_url,
        )


template_extensions = [DeviceCoverageExportListButtons]
