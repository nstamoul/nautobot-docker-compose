"""URL routing for the VPN manager app."""

from django.urls import path
from django.views.generic import RedirectView

from nautobot_vpn_manager import views

app_name = "nautobot_vpn_manager"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="plugins:nautobot_vpn_manager:dashboard", permanent=False), name="home"),
    path("dashboard/", views.VpnDashboardView.as_view(), name="dashboard"),
    path("workers/", views.VpnWorkerSteeringView.as_view(), name="workers"),
    path("workers/<str:worker_name>/", views.VpnWorkerDetailView.as_view(), name="worker_detail"),
    path("action/", views.VpnActionView.as_view(), name="action"),
]
