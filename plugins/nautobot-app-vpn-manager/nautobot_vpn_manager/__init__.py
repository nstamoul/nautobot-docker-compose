"""App declaration for the SHMS VPN manager plugin."""

from importlib import metadata

from nautobot.apps import NautobotAppConfig

try:
    __version__ = metadata.version(__name__)
except metadata.PackageNotFoundError:  # pragma: no cover - local editable install gap
    __version__ = "0.1.0"


class NautobotVpnManagerConfig(NautobotAppConfig):
    """App configuration for the SHMS VPN manager."""

    name = "nautobot_vpn_manager"
    verbose_name = "VPN Manager"
    version = __version__
    author = "Nikos Stamoulis"
    description = "Dashboard for SHMS tenant-scoped VPN slots."
    base_url = "vpn-manager"
    required_settings = []
    default_settings = {
        "control_api_url": "http://vpn-control-api:5001",
        "control_api_key": "",
        "piconfig_api_url": "",
        "piconfig_client_cert": "",
        "piconfig_client_key": "",
        "piconfig_ca_bundle": "",
        "piconfig_verify_tls": True,
        "request_timeout_seconds": 30,
    }
    home_view_name = "plugins:nautobot_vpn_manager:dashboard"


config = NautobotVpnManagerConfig  # pylint:disable=invalid-name
