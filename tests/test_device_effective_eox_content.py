from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace


def load_template_content_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "plugins"
        / "nautobot_ui_plugin"
        / "template_content.py"
    )
    spec = importlib.util.spec_from_file_location("template_content_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hardware_section_exposes_dlm_record_url(monkeypatch):
    module = load_template_content_module()
    notice = SimpleNamespace(
        release_date=None,
        end_of_sale=None,
        end_of_support=None,
        end_of_sw_releases=None,
        end_of_security_patches=None,
        documentation_url="https://www.cisco.com/example",
        comments="Lifecycle note",
        expired=False,
        custom_field_data={},
        get_absolute_url=lambda: "/plugins/nautobot-device-lifecycle-mgmt/hardware/abc/",
    )
    content = module.DeviceEffectiveEOXContent(context={"object": object()})
    monkeypatch.setattr(content, "_hardware_notice", lambda device: notice)

    section = content._hardware_section(SimpleNamespace(device_type="C9200-24T"))

    assert section["record_url"] == "/plugins/nautobot-device-lifecycle-mgmt/hardware/abc/"


def test_software_section_exposes_dlm_record_url(monkeypatch):
    module = load_template_content_module()
    notice = SimpleNamespace(
        release_date=None,
        end_of_support=None,
        documentation_url="https://www.cisco.com/example",
        long_term_support=False,
        pre_release=False,
        expired=False,
        custom_field_data={},
        get_absolute_url=lambda: "/plugins/nautobot-device-lifecycle-mgmt/software/def/",
    )
    software_version = SimpleNamespace(platform="cisco_xe", version="17.9.5")
    content = module.DeviceEffectiveEOXContent(context={"object": object()})
    monkeypatch.setattr(content, "_software_notice", lambda device: notice)

    section = content._software_section(SimpleNamespace(software_version=software_version))

    assert section["record_url"] == "/plugins/nautobot-device-lifecycle-mgmt/software/def/"


def test_plugin_config_loads_without_installed_distribution_metadata(monkeypatch):
    module_path = (
        Path(__file__).resolve().parents[1]
        / "plugins"
        / "nautobot_ui_plugin"
        / "__init__.py"
    )
    nautobot_module = types.ModuleType("nautobot")
    nautobot_apps_module = types.ModuleType("nautobot.apps")

    class FakeNautobotAppConfig:
        pass

    nautobot_apps_module.NautobotAppConfig = FakeNautobotAppConfig
    monkeypatch.setitem(sys.modules, "nautobot", nautobot_module)
    monkeypatch.setitem(sys.modules, "nautobot.apps", nautobot_apps_module)

    spec = importlib.util.spec_from_file_location("nautobot_ui_plugin_config_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.__version__
    assert module.config.name == "nautobot_ui_plugin"


def test_ui_plugin_template_extensions_are_versioned_with_plugin_source():
    module = load_template_content_module()

    extension_names = {extension.__name__ for extension in module.template_extensions}

    assert extension_names == {"LocationTopologyButtons", "DeviceEffectiveEOXContent"}


def test_dockerfile_installs_versioned_ui_plugin_source():
    dockerfile = Path(__file__).resolve().parents[1] / "environments" / "Dockerfile"
    dockerfile_text = dockerfile.read_text()

    assert "COPY ../plugins/nautobot_ui_plugin/__init__.py" in dockerfile_text
    assert "COPY ../plugins/nautobot_ui_plugin/template_content.py" in dockerfile_text
    assert "COPY ../patches/nautobot_ui_plugin/__init__.py" not in dockerfile_text
    assert "COPY ../patches/nautobot_ui_plugin/template_content.py" not in dockerfile_text
