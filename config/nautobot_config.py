"""SHMS Nautobot configuration file."""

# pylint: disable=invalid-envvar-default
import logging
import os
import sys
from urllib.parse import quote

import ldap
from django_auth_ldap.config import LDAPGroupQuery, LDAPSearch, NestedActiveDirectoryGroupType
from nautobot.core.settings import *  # noqa: F403  # pylint: disable=wildcard-import,unused-wildcard-import
from nautobot.core.settings_funcs import is_truthy
from kombu import Queue

#
# Debug / Logging
#

DEBUG = is_truthy(os.getenv("NAUTOBOT_DEBUG", False))
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
LOG_LEVEL = "DEBUG" if DEBUG else "INFO"
LOGGER = logging.getLogger(__name__)
TIME_ZONE = os.getenv("NAUTOBOT_TIME_ZONE", os.getenv("TIME_ZONE", "UTC"))
USE_TZ = True
CELERY_TIMEZONE = TIME_ZONE

#
# Redis
#

def build_redis_connection(redis_database):
    """Build a Redis URL while safely encoding credentials."""
    redis_scheme = os.getenv("NAUTOBOT_REDIS_SCHEME")
    if redis_scheme is None:
        redis_scheme = "rediss" if is_truthy(os.getenv("NAUTOBOT_REDIS_SSL", "false")) else "redis"

    redis_host = os.getenv("NAUTOBOT_REDIS_HOST", "localhost")
    redis_port = int(os.getenv("NAUTOBOT_REDIS_PORT", "6379"))
    redis_username = os.getenv("NAUTOBOT_REDIS_USERNAME", "")
    redis_password = os.getenv("NAUTOBOT_REDIS_PASSWORD", "")

    redis_creds = ""
    if redis_username or redis_password:
        redis_creds = f"{quote(redis_username, safe='')}:{quote(redis_password, safe='')}@"

    if redis_scheme == "unix":
        return f"{redis_scheme}://{redis_creds}{redis_host}?db={redis_database}"
    return f"{redis_scheme}://{redis_creds}{redis_host}:{redis_port}/{redis_database}"


_redis_cache_url = build_redis_connection(redis_database=1)
_redis_broker_url = os.getenv("NAUTOBOT_CELERY_BROKER_URL", build_redis_connection(redis_database=0))

CACHES["default"]["LOCATION"] = _redis_cache_url
CACHES["default"]["OPTIONS"]["PASSWORD"] = os.getenv("NAUTOBOT_REDIS_PASSWORD", "")
CELERY_BROKER_URL = _redis_broker_url
CACHEOPS_REDIS = _redis_cache_url

if "job_logs" not in DATABASES:
    DATABASES["job_logs"] = DATABASES["default"].copy()
    DATABASES["job_logs"]["TEST"] = {"MIRROR": "default"}

BASE_URL = os.getenv("NAUTOBOT_BASE_URL", "http://sot3.shms.local")

allowed_hosts = [
    item.strip()
    for item in os.getenv("NAUTOBOT_ALLOWED_HOSTS", "").replace(" ", ",").split(",")
    if item.strip()
]
if allowed_hosts:
    ALLOWED_HOSTS = allowed_hosts

secure_proxy_ssl_header = os.getenv("NAUTOBOT_SECURE_PROXY_SSL_HEADER", "").strip()
if secure_proxy_ssl_header:
    header, value = [item.strip() for item in secure_proxy_ssl_header.split(",", 1)]
    SECURE_PROXY_SSL_HEADER = (header, value)

if is_truthy(os.getenv("NAUTOBOT_MINIO_ENABLED", "false")):
    _minio_bucket = os.getenv("NAUTOBOT_MINIO_BUCKET_NAME", "nautobot")
    _minio_endpoint = os.getenv("NAUTOBOT_MINIO_ENDPOINT_URL", "http://s3.minio.shms.local")
    _minio_region = os.getenv("NAUTOBOT_MINIO_REGION_NAME", "us-east-1")
    _minio_verify_ssl = is_truthy(os.getenv("NAUTOBOT_MINIO_VERIFY_SSL", "false"))
    _minio_common = {
        "access_key": os.getenv("NAUTOBOT_MINIO_ACCESS_KEY", ""),
        "secret_key": os.getenv("NAUTOBOT_MINIO_SECRET_KEY", ""),
        "bucket_name": _minio_bucket,
        "endpoint_url": _minio_endpoint,
        "region_name": _minio_region,
        "default_acl": "private",
        "querystring_auth": True,
        "file_overwrite": False,
        "addressing_style": "path",
        "use_ssl": _minio_endpoint.startswith("https://"),
        "verify": _minio_verify_ssl,
    }
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **_minio_common,
            "location": "media",
        },
    }
    STORAGES["nautobotjobfiles"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **_minio_common,
            "location": "job-files",
        },
    }

csrf_trusted_origins = [
    item.strip()
    for item in os.getenv("NAUTOBOT_CSRF_TRUSTED_ORIGINS", "").split(",")
    if item.strip()
]
if csrf_trusted_origins:
    CSRF_TRUSTED_ORIGINS = csrf_trusted_origins

if os.getenv("NAUTOBOT_AUTH_LDAP_SERVER_URI", "").strip():
    AUTHENTICATION_BACKENDS = [
        "django_auth_ldap.backend.LDAPBackend",
        "nautobot.core.authentication.ObjectPermissionBackend",
    ]
    AUTH_LDAP_SERVER_URI = os.getenv("NAUTOBOT_AUTH_LDAP_SERVER_URI", "")
    AUTH_LDAP_CONNECTION_OPTIONS = {
        ldap.OPT_REFERRALS: 0,
    }
    AUTH_LDAP_BIND_DN = os.getenv("NAUTOBOT_AUTH_LDAP_BIND_DN", "")
    AUTH_LDAP_BIND_PASSWORD = os.getenv("NAUTOBOT_AUTH_LDAP_BIND_PASSWORD", "")
    _ldap_search_dn = os.getenv("NAUTOBOT_AUTH_LDAP_SEARCH_DN", "")
    AUTH_LDAP_USER_SEARCH = LDAPSearch(
        _ldap_search_dn,
        ldap.SCOPE_SUBTREE,
        "(sAMAccountName=%(user)s)",
    )
    AUTH_LDAP_USER_ATTR_MAP = {
        "first_name": "givenName",
        "last_name": "sn",
        "email": "mail",
    }
    AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
        _ldap_search_dn,
        ldap.SCOPE_SUBTREE,
        "(objectClass=group)",
    )
    AUTH_LDAP_GROUP_TYPE = NestedActiveDirectoryGroupType()
    AUTH_LDAP_MIRROR_GROUPS = is_truthy(os.getenv("NAUTOBOT_AUTH_LDAP_MIRROR_GROUPS", "true"))
    AUTH_LDAP_FIND_GROUP_PERMS = is_truthy(os.getenv("NAUTOBOT_AUTH_LDAP_FIND_GROUP_PERMS", "true"))
    AUTH_LDAP_ALWAYS_UPDATE_USER = is_truthy(os.getenv("NAUTOBOT_AUTH_LDAP_ALWAYS_UPDATE_USER", "true"))
    AUTH_LDAP_CACHE_TIMEOUT = int(os.getenv("NAUTOBOT_AUTH_LDAP_CACHE_TIMEOUT", "3600"))

    _ldap_require_group = os.getenv("NAUTOBOT_AUTH_LDAP_REQUIRE_GROUP", "").strip()
    if _ldap_require_group:
        AUTH_LDAP_REQUIRE_GROUP = _ldap_require_group

    _ldap_user_flags_by_group = {}
    _ldap_is_active_dn = os.getenv("NAUTOBOT_AUTH_LDAP_IS_ACTIVE_DN", "").strip()
    _ldap_is_staff_dn = os.getenv("NAUTOBOT_AUTH_LDAP_IS_STAFF_DN", "").strip()
    _ldap_is_superuser_dn = os.getenv("NAUTOBOT_AUTH_LDAP_IS_SUPERUSER_DN", "").strip()

    if _ldap_is_active_dn:
        _ldap_user_flags_by_group["is_active"] = _ldap_is_active_dn
    if _ldap_is_superuser_dn:
        _ldap_user_flags_by_group["is_superuser"] = _ldap_is_superuser_dn
    if _ldap_is_staff_dn and _ldap_is_superuser_dn:
        _ldap_user_flags_by_group["is_staff"] = (
            LDAPGroupQuery(_ldap_is_staff_dn) | LDAPGroupQuery(_ldap_is_superuser_dn)
        )
    elif _ldap_is_staff_dn:
        _ldap_user_flags_by_group["is_staff"] = _ldap_is_staff_dn
    elif _ldap_is_superuser_dn:
        # Superusers must also be staff, otherwise parts of the Nautobot UI disappear.
        _ldap_user_flags_by_group["is_staff"] = _ldap_is_superuser_dn
    if _ldap_user_flags_by_group:
        AUTH_LDAP_USER_FLAGS_BY_GROUP = _ldap_user_flags_by_group

PLUGINS = [
    "nautobot_ssot",
    "welcome_wizard",
    "nautobot_device_onboarding",
    "nautobot_plugin_nornir",
    "nautobot_device_lifecycle_mgmt",
    "nautobot_secrets_providers",
    "nautobot_capacity_metrics",
    "nautobot_golden_config",
    "nautobot_software_lifecycle",
    "nautobot_ui_plugin",
    "nautobot_connectivity_matrix",
    "nbcot",
    "nautobot_vpn_manager",
]

_nornir_num_workers = int(os.getenv("NAUTOBOT_NORNIR_NUM_WORKERS", "50"))
_nornir_runner_plugin = os.getenv("NAUTOBOT_NORNIR_RUNNER_PLUGIN", "threaded")

PLUGINS_CONFIG = {
    "nautobot_golden_config": {
        "enable_postprocessing": True,
    },
    "nbcot": {
        "environment": os.getenv("NBCOT_ENVIRONMENT", "prod"),
        "token_url": os.getenv("NBCOT_TOKEN_URL", "https://id.cisco.com/oauth2/default/v1/token"),
        "graphql_endpoint": os.getenv("NBCOT_GRAPHQL_ENDPOINT", "https://capi.cisco.com/commerce/apis"),
        "client_id": os.getenv("CISCO_MODERN_API_CLIENT_ID", ""),
        "client_secret": os.getenv("CISCO_MODERN_API_SECRET", ""),
        "tracked_order_refresh_interval_minutes": int(os.getenv("NBCOT_REFRESH_INTERVAL_MINUTES", "60")),
        "enable_event_consumer": is_truthy(os.getenv("NBCOT_ENABLE_EVENT_CONSUMER", "false")),
    },
    "nautobot_vpn_manager": {
        "control_api_url": os.getenv("VPN_CONTROL_API_URL", "http://vpn-control-api:5001"),
        "control_api_key": os.getenv("VPN_CONTROL_API_KEY", ""),
        "request_timeout_seconds": int(os.getenv("VPN_CONTROL_API_TIMEOUT", "30")),
    },
    "nautobot_capacity_metrics": {
        "app_metrics": {
            "jobs": True,
            "queues": True,
            "versions": {
                "basic": True,
                "plugins": True,
            },
            "models": {
                "dcim": {
                    "Device": True,
                    "Interface": True,
                    "Location": True,
                    "Manufacturer": True,
                    "Platform": True,
                    "Rack": True,
                    "Site": True,
                },
                "extras": {
                    "GitRepository": True,
                    "Job": True,
                    "JobResult": True,
                },
                "ipam": {
                    "IPAddress": True,
                    "Namespace": True,
                    "Prefix": True,
                    "VRF": True,
                    "VLAN": True,
                },
                "tenancy": {
                    "Tenant": True,
                    "TenantGroup": True,
                },
                "virtualization": {
                    "Cluster": True,
                    "VirtualMachine": True,
                },
            },
        }
    },
    "welcome_wizard": {},
    "nautobot_secrets_providers": {
        "hashicorp_vault": {
            "url": os.getenv("HASHICORP_VAULT_URL", ""),
            "token": os.getenv("HASHICORP_VAULT_TOKEN", ""),
        }
    },
    "nautobot_ssot": {
        "enable_meraki": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_MERAKI", "false")),
        "enable_aci": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_ACI", "false")),
        "enable_bootstrap": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_BOOTSTRAP", "false")),
        "enable_vsphere": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_VSPHERE", "true")),
    },
    "nautobot_plugin_nornir": {
        "use_config_context": {"secrets": False, "connection_options": True},
        "connection_options": {
            "napalm": {
                "extras": {
                    "optional_args": {
                        "global_delay_factor": 1,
                    }
                }
            },
            "netmiko": {
                "extras": {
                    "global_delay_factor": 1,
                }
            },
        },
        "nornir_settings": {
            "credentials": "nautobot_plugin_nornir.plugins.credentials.nautobot_secrets.CredentialsNautobotSecrets",
            "runner": {
                "plugin": _nornir_runner_plugin,
                "options": {
                    "num_workers": _nornir_num_workers,
                },
            },
        },
    },
    "nautobot_device_onboarding": {
        "create_platform_if_missing": True,
        "create_manufacturer_if_missing": True,
        "create_device_type_if_missing": True,
        "create_device_role_if_missing": True,
        "default_device_role": os.getenv(
            "NAUTOBOT_DEVICE_ONBOARDING_DEFAULT_DEVICE_ROLE",
            "placeholder_role",
        ),
    },
}

if is_truthy(os.getenv("NAUTOBOT_RUNTIME_PATCHES_ENABLED", "true")):
    patches_path = os.getenv(
        "NAUTOBOT_RUNTIME_PATCHES_PATH",
        "/opt/nautobot/patches_runtime",
    )
    if os.path.isdir(patches_path):
        if patches_path not in sys.path:
            sys.path.insert(0, patches_path)
        try:
            from nautobot_startup_hook import apply_patches

            apply_patches()
        except Exception as exc:  # pragma: no cover - best-effort startup hook
            LOGGER.warning("Failed to apply SHMS runtime patches: %s", exc, exc_info=True)
    else:
        LOGGER.info("Runtime patch path %s not present, skipping patch load", patches_path)

_existing_queues = globals().get("CELERY_TASK_QUEUES")
if not _existing_queues:
    _existing_queues = (Queue("default"), Queue("celery"))

CELERY_TASK_QUEUES = tuple(_existing_queues) + (Queue("vpn"),)
