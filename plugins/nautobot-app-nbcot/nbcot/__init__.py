"""App declaration for nbcot."""

from importlib import metadata

from nautobot.apps import NautobotAppConfig

from nbcot.constants import DEFAULT_TOKEN_URL, PROD_GRAPHQL_ENDPOINT

try:
    __version__ = metadata.version(__name__)
except metadata.PackageNotFoundError:  # pragma: no cover - local editable install gap
    __version__ = "0.1.0"


class NBCOTConfig(NautobotAppConfig):
    """App configuration for the nbcot app."""

    name = "nbcot"
    verbose_name = "NBCOT"
    version = __version__
    author = "Nikos Stamoulis"
    description = "Nautobot Cisco Order Tracking."
    base_url = "nbcot"
    required_settings = []
    default_settings = {
        "environment": "prod",
        "token_url": DEFAULT_TOKEN_URL,
        "graphql_endpoint": PROD_GRAPHQL_ENDPOINT,
        "client_id": "",
        "client_secret": "",
        "tracked_order_refresh_interval_minutes": 60,
        "enable_event_consumer": False,
        "search_query_document": "",
        "order_details_query_document": "",
        "subscription_search_query_document": "",
        "subscription_details_query_document": "",
    }
    docs_view_name = "plugins:nbcot:docs"
    home_view_name = "plugins:nbcot:order_search"
    searchable_models = ["ciscoorder"]


config = NBCOTConfig  # pylint:disable=invalid-name
