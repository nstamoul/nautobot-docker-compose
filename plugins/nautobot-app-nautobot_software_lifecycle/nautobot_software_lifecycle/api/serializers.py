"""API serializers for nautobot_software_lifecycle."""

from nautobot.apps.api import NautobotModelSerializer, TaggedModelSerializerMixin

from nautobot_software_lifecycle import models


class SoftwareLicenseSerializer(NautobotModelSerializer, TaggedModelSerializerMixin):  # pylint: disable=too-many-ancestors
    """SoftwareLicense Serializer."""

    class Meta:
        """Meta attributes."""

        model = models.SoftwareLicense
        fields = "__all__"
