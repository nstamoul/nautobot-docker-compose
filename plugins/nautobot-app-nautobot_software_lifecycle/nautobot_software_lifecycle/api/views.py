"""API views for nautobot_software_lifecycle."""

from nautobot.apps.api import NautobotModelViewSet

from nautobot_software_lifecycle import filters, models
from nautobot_software_lifecycle.api import serializers


class SoftwareLicenseViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """SoftwareLicense viewset."""

    queryset = models.SoftwareLicense.objects.all()
    serializer_class = serializers.SoftwareLicenseSerializer
    filterset_class = filters.SoftwareLicenseFilterSet
