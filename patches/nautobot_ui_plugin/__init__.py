"""App declaration for nautobot_ui_plugin (Nautobot v3 compatibility)."""

from importlib import metadata

from nautobot.apps import NautobotAppConfig

try:
    __version__ = metadata.version(__name__)
except metadata.PackageNotFoundError:
    __version__ = "0.0.0+shms"


class NautobotUIConfig(NautobotAppConfig):
    name = "nautobot_ui_plugin"
    verbose_name = "Nautobot UI"
    description = "A topology visualization plugin for Nautobot powered by NextUI Toolkit."
    version = __version__
    author = "Gesellschaft für wissenschaftliche Datenverarbeitung mbH Göttingen"
    author_email = "netzadmin@gwdg.de"
    base_url = "nautobot-ui"
    required_settings = []
    default_settings = {}
    caching_config = {"*": None}


config = NautobotUIConfig
