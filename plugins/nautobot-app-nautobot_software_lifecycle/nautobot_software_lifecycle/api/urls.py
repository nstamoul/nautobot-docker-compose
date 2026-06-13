"""Django API urlpatterns declaration for nautobot_software_lifecycle app."""

from nautobot.apps.api import OrderedDefaultRouter

from nautobot_software_lifecycle.api import views

router = OrderedDefaultRouter()
router.register("software-licenses", views.SoftwareLicenseViewSet)

app_name = "nautobot_software_lifecycle-api"
urlpatterns = router.urls
