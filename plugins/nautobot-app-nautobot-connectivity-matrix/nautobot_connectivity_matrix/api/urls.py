"""REST API URL configuration for the Connectivity Matrix Diagram app."""

from nautobot.apps.api import OrderedDefaultRouter

from .views import (
    ConnectionPlanViewSet,
    ConnectionPlanBatchViewSet,
    AvailableInterfacesView,
    AvailableDevicesView,
    StackPlanTemplateView,
    StackPlanImportView,
    StackPlanMaterializeView,
)

router = OrderedDefaultRouter()
router.register("batches", ConnectionPlanBatchViewSet)
router.register("plans", ConnectionPlanViewSet)

urlpatterns = router.urls

# Add non-viewset endpoints
from django.urls import path

urlpatterns += [
    path(
        "available-interfaces/",
        AvailableInterfacesView.as_view(),
        name="available-interfaces"
    ),
    path(
        "available-devices/",
        AvailableDevicesView.as_view(),
        name="available-devices"
    ),
    path(
        "stack-plan/template-xlsx/",
        StackPlanTemplateView.as_view(),
        name="stack-plan-template-xlsx",
    ),
    path(
        "stack-plan/import-xlsx/",
        StackPlanImportView.as_view(),
        name="stack-plan-import-xlsx",
    ),
    path(
        "stack-plan/materialize/",
        StackPlanMaterializeView.as_view(),
        name="stack-plan-materialize",
    ),
]
