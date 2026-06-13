from pathlib import Path


APP = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "nautobot-app-nautobot-connectivity-matrix"
    / "nautobot_connectivity_matrix"
)


def test_device_list_template_extension_adds_filtered_export_buttons():
    source = (APP / "template_content.py").read_text()

    assert "class DeviceCoverageExportListButtons(TemplateExtension):" in source
    assert 'model = "dcim.device"' in source
    assert "def list_buttons(self):" in source
    assert "request\"].GET.urlencode()" in source
    assert "device_coverage_export_dlm" in source
    assert "device_coverage_export_cf" in source


def test_connectivity_matrix_app_registers_template_extensions():
    source = (APP / "__init__.py").read_text()

    assert (
        'template_extensions = "nautobot_connectivity_matrix.template_content.template_extensions"'
        in source
    )


def test_device_coverage_export_urls_and_views_exist():
    urls = (APP / "urls.py").read_text()
    views = (APP / "views.py").read_text()

    assert 'path("device-coverage-export/dlm/", views.DeviceCoverageExportView.as_view()' in urls
    assert 'path("device-coverage-export/cf/", views.DeviceCoverageCFExportView.as_view()' in urls
    assert "class DeviceCoverageExportView(LoginRequiredMixin, View):" in views
    assert "DeviceFilterSet(data=filter_data, queryset=queryset, request=request)" in views
    assert 'filter_kwargs = {"pk__in": device_pks}' in views
    assert 'module_filter_kwargs = {"device__in": device_queryset}' in views
    assert 'Path("/opt/nautobot/git/shms_nautobot_jobs_repo")' in views
    assert "Content-Disposition" in views
