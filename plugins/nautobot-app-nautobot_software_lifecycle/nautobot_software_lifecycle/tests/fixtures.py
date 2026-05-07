"""Create fixtures for tests."""

from nautobot_software_lifecycle.models import Nautobot_Software_LifecycleExampleModel


def create_nautobot_software_lifecycleexamplemodel():
    """Fixture to create necessary number of Nautobot_Software_LifecycleExampleModel for tests."""
    Nautobot_Software_LifecycleExampleModel.objects.create(name="Test One")
    Nautobot_Software_LifecycleExampleModel.objects.create(name="Test Two")
    Nautobot_Software_LifecycleExampleModel.objects.create(name="Test Three")
