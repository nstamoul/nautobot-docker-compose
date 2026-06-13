from __future__ import annotations

import logging
from importlib import import_module
from types import FunctionType
from typing import Any

LOGGER = logging.getLogger(__name__)

_PATCH_ATTR = "_filename_uniqueness_patched"
_ORIGINAL_STATE: dict[str, Any] = {}


def _patched_refresh_git_import_wizard(repository_record, job_result, delete=False):
    module_globals = globals()
    retrieve_from_filesystem = module_globals["retrieve_device_types_from_filesystem"]
    manufacturer_import_model = module_globals["ManufacturerImport"]
    device_type_import_model = module_globals["DeviceTypeImport"]
    log_level_choices = module_globals["LogLevelChoices"]

    if (
        "welcome_wizard.import_wizard" not in repository_record.provided_contents
        or delete
    ):
        return

    manufacturers, device_types = retrieve_from_filesystem(
        repository_record.filesystem_path
    )

    manufacturer_records = {}
    for manufacturer in manufacturers:
        manufacturer_record, _ = manufacturer_import_model.objects.update_or_create(
            name=manufacturer
        )
        manufacturer_records[manufacturer] = manufacturer_record
        job_result.log(
            "Successfully created/updated manufacturer",
            obj=manufacturer_record,
            level_choice=log_level_choices.LOG_INFO,
            grouping="welcome_wizard",
        )

    for filename, device_data in device_types.items():
        manufacturer_name = device_data.get("manufacturer")
        manufacturer_record = manufacturer_records.get(manufacturer_name)
        if manufacturer_record is None and manufacturer_name:
            manufacturer_record, _ = manufacturer_import_model.objects.update_or_create(
                name=manufacturer_name
            )
            manufacturer_records[manufacturer_name] = manufacturer_record

        model_name = device_data.get("model") or filename.rsplit(".", 1)[0]

        device_type_record, _ = device_type_import_model.objects.update_or_create(
            filename=filename,
            defaults={
                "name": model_name,
                "manufacturer": manufacturer_record,
                "device_type_data": device_data,
            },
        )

        job_result.log(
            "Successfully created/updated device_type",
            obj=device_type_record,
            level_choice=log_level_choices.LOG_INFO,
            grouping="welcome_wizard",
        )


def apply_welcome_wizard_import_filename_uniqueness_patch() -> bool:
    global _ORIGINAL_STATE

    try:
        ww_datasources = import_module("welcome_wizard.datasources")

        target = getattr(ww_datasources, "refresh_git_import_wizard", None)
        if not isinstance(target, FunctionType):
            LOGGER.warning(
                "Welcome Wizard patch target is not a Python function: %r", target
            )
            return False

        if getattr(target, _PATCH_ATTR, False):
            LOGGER.debug("Welcome Wizard filename uniqueness patch already applied")
            return True

        _ORIGINAL_STATE = {
            "code": target.__code__,
            "defaults": target.__defaults__,
            "kwdefaults": target.__kwdefaults__,
        }

        target.__code__ = _patched_refresh_git_import_wizard.__code__
        target.__defaults__ = _patched_refresh_git_import_wizard.__defaults__
        target.__kwdefaults__ = _patched_refresh_git_import_wizard.__kwdefaults__
        setattr(target, _PATCH_ATTR, True)

        LOGGER.info(
            "Successfully applied Welcome Wizard filename uniqueness patch "
            "to refresh_git_import_wizard"
        )
        return True

    except ModuleNotFoundError as exc:
        LOGGER.debug("Welcome Wizard plugin unavailable, skipping patch: %s", exc)
        return True
    except Exception as exc:
        LOGGER.error(
            "Failed to apply Welcome Wizard filename uniqueness patch: %s",
            exc,
            exc_info=True,
        )
        return False


def remove_welcome_wizard_import_filename_uniqueness_patch() -> bool:
    try:
        ww_datasources = import_module("welcome_wizard.datasources")

        target = getattr(ww_datasources, "refresh_git_import_wizard", None)
        if not isinstance(target, FunctionType):
            return False

        if not _ORIGINAL_STATE:
            LOGGER.debug(
                "Welcome Wizard filename uniqueness patch not currently applied"
            )
            return True

        target.__code__ = _ORIGINAL_STATE["code"]
        target.__defaults__ = _ORIGINAL_STATE["defaults"]
        target.__kwdefaults__ = _ORIGINAL_STATE["kwdefaults"]
        if hasattr(target, _PATCH_ATTR):
            delattr(target, _PATCH_ATTR)

        LOGGER.info("Successfully removed Welcome Wizard filename uniqueness patch")
        return True
    except Exception as exc:
        LOGGER.error(
            "Failed to remove Welcome Wizard filename uniqueness patch: %s",
            exc,
            exc_info=True,
        )
        return False
