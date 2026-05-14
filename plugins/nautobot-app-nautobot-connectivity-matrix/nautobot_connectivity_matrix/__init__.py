"""App declaration for nautobot_connectivity_matrix."""

# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

from nautobot.apps import NautobotAppConfig

try:
    __version__ = metadata.version(__name__)
except metadata.PackageNotFoundError:
    __version__ = "0.1.0"


class NautobotConnectivityMatrixConfig(NautobotAppConfig):
    """App configuration for the nautobot_connectivity_matrix app."""

    name = "nautobot_connectivity_matrix"
    verbose_name = "Connectivity Matrix"
    version = __version__
    author = "Network Automation Team"
    description = "Excel-like UI for planning and documenting device connectivity."
    base_url = "nautobot-connectivity-matrix"
    required_settings = []
    default_settings = {}
    docs_view_name = "plugins:nautobot_connectivity_matrix:docs"
    searchable_models = []
    template_extensions = "nautobot_connectivity_matrix.template_content.template_extensions"


config = NautobotConnectivityMatrixConfig  # pylint:disable=invalid-name
