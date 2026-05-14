"""Django urlpatterns declaration for nautobot_connectivity_matrix app."""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView

from nautobot.extras.views import ObjectChangeLogView

from nautobot_connectivity_matrix import views
from nautobot_connectivity_matrix.models import ConnectionPlanBatch

app_name = "nautobot_connectivity_matrix"

urlpatterns = [
    # Documentation
    path("docs/", RedirectView.as_view(url=static("nautobot_connectivity_matrix/docs/index.html")), name="docs"),

    # ConnectionPlanBatch views (names must match Nautobot's expected pattern: {model_lowercase}_{action})
    path("batches/", views.BatchListView.as_view(), name="connectionplanbatch_list"),
    path("batches/add/", views.BatchCreateView.as_view(), name="connectionplanbatch_add"),
    path("batches/<uuid:pk>/", views.BatchDetailView.as_view(), name="connectionplanbatch"),
    path("batches/<uuid:pk>/edit/", views.BatchEditView.as_view(), name="connectionplanbatch_edit"),
    path("batches/<uuid:pk>/delete/", views.BatchDeleteView.as_view(), name="connectionplanbatch_delete"),
    path(
        "batches/<uuid:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="connectionplanbatch_changelog",
        kwargs={"model": ConnectionPlanBatch},
    ),

    # Matrix view (the main spreadsheet UI)
    path("batches/<uuid:pk>/matrix/", views.MatrixView.as_view(), name="matrix"),

    # Stack-plan helpers
    path("stack-plan/", views.StackPlanView.as_view(), name="stack_plan"),
    path("device-coverage-export/dlm/", views.DeviceCoverageExportView.as_view(), name="device_coverage_export_dlm"),
    path("device-coverage-export/cf/", views.DeviceCoverageCFExportView.as_view(), name="device_coverage_export_cf"),
]
