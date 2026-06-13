from __future__ import annotations

import logging
import sys

from django.apps import apps
from django.conf import settings
from django.utils.module_loading import import_string

LOGGER = logging.getLogger(__name__)

_PATCH_ATTR = "_shms_dynamic_jobs_app_config_fix_applied"


def _resolve_app_config(plugin_name):
    try:
        return apps.get_app_config(plugin_name)
    except LookupError:
        pass

    for app_config in apps.get_app_configs():
        if app_config.name == plugin_name:
            return app_config
    return None


def _patched_import_dynamic_jobs_from_apps():
    for plugin_name in settings.PLUGINS:
        app_config = _resolve_app_config(plugin_name)
        if app_config is None:
            LOGGER.warning(
                "Dynamic jobs import skipping missing plugin app config for %s",
                plugin_name,
            )
            continue

        if not getattr(app_config, "provides_dynamic_jobs", False):
            continue

        app_jobs = getattr(app_config, "features", {}).get("jobs", [])
        for job in app_jobs:
            if job.__module__ in sys.modules:
                del sys.modules[job.__module__]

        app_config.features["jobs"] = import_string(
            f"{app_config.__module__}.{app_config.jobs}"
        )


def apply_dynamic_jobs_app_config_fix() -> bool:
    try:
        import nautobot.core.celery as celery_module

        target = getattr(celery_module, "_import_dynamic_jobs_from_apps", None)
        if target is None:
            LOGGER.warning("Dynamic jobs import target not found")
            return False

        if getattr(target, _PATCH_ATTR, False):
            LOGGER.debug("Dynamic jobs app-config fix already applied")
            return True

        setattr(_patched_import_dynamic_jobs_from_apps, _PATCH_ATTR, True)
        celery_module._import_dynamic_jobs_from_apps = _patched_import_dynamic_jobs_from_apps
        LOGGER.info("Applied dynamic jobs app-config resolution fix")
        return True
    except Exception as exc:
        LOGGER.error("Failed to apply dynamic jobs app-config fix: %s", exc, exc_info=True)
        return False
