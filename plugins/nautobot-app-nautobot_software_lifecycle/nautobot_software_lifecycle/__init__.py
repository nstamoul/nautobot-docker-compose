"""App declaration for nautobot_software_lifecycle."""

# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

from nautobot.apps import NautobotAppConfig

__version__ = metadata.version(__name__)


class Nautobot_Software_LifecycleConfig(NautobotAppConfig):
    """App configuration for the nautobot_software_lifecycle app."""

    name = "nautobot_software_lifecycle"
    verbose_name = "Nautobot Software Lifecycle"
    version = __version__
    author = "Nikolaos Stamoulos"
    description = "Software License Lifecycle Management application."
    base_url = "nautobot_software_lifecycle"
    required_settings = []
    default_settings = {}
    docs_view_name = "plugins:nautobot_software_lifecycle:docs"
    searchable_models = ["softwarelicense"]


config = Nautobot_Software_LifecycleConfig  # pylint:disable=invalid-name
