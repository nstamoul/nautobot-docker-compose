"""Django urlpatterns declaration for nautobot_software_lifecycle app."""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView
from nautobot.apps.urls import NautobotUIViewSetRouter


from nautobot_software_lifecycle import views


app_name = "nautobot_software_lifecycle"
router = NautobotUIViewSetRouter()

router.register("software-licenses", views.SoftwareLicenseUIViewSet)


urlpatterns = [
    path("docs/", RedirectView.as_view(url=static("nautobot_software_lifecycle/docs/index.html")), name="docs"),
]

urlpatterns += router.urls
