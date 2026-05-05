"""Django urlpatterns declaration for nbcot app."""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView
from nautobot.apps.urls import NautobotUIViewSetRouter

from nbcot import views

app_name = "nbcot"
router = NautobotUIViewSetRouter()
router.register("cisco-orders", views.CiscoOrderUIViewSet)

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="plugins:nbcot:order_search", permanent=False), name="home"),
    path("search/", views.OrderSearchView.as_view(), name="order_search"),
    path("ccwr/", views.CCWRSubscriptionSearchView.as_view(), name="subscription_search"),
    path("search/track/", views.TrackCiscoOrderView.as_view(), name="order_track"),
    path("cisco-orders/<uuid:pk>/refresh/", views.RefreshCiscoOrderView.as_view(), name="ciscoorder_refresh"),
    path(
        "cisco-orders/<uuid:pk>/toggle-tracking/",
        views.ToggleTrackingView.as_view(),
        name="ciscoorder_toggle_tracking",
    ),
    path("docs/", RedirectView.as_view(url=static("nbcot/docs/index.html")), name="docs"),
]

urlpatterns += router.urls
