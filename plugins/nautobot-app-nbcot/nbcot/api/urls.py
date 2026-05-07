"""Django API urlpatterns declaration for nbcot app."""

from nautobot.apps.api import OrderedDefaultRouter

from nbcot.api import views

router = OrderedDefaultRouter()
router.register("cisco-orders", views.CiscoOrderViewSet)
router.register("cisco-order-lines", views.CiscoOrderLineViewSet)
router.register("cisco-order-updates", views.CiscoOrderUpdateViewSet)

app_name = "nbcot-api"
urlpatterns = router.urls
