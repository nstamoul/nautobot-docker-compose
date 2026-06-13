from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_vpn_manager_exposes_cisco_client_fields():
    forms = (
        REPO_ROOT
        / "plugins"
        / "nautobot-app-vpn-manager"
        / "nautobot_vpn_manager"
        / "forms.py"
    ).read_text()
    views = (
        REPO_ROOT
        / "plugins"
        / "nautobot-app-vpn-manager"
        / "nautobot_vpn_manager"
        / "views.py"
    ).read_text()
    template = (
        REPO_ROOT
        / "plugins"
        / "nautobot-app-vpn-manager"
        / "nautobot_vpn_manager"
        / "templates"
        / "nautobot_vpn_manager"
        / "dashboard.html"
    ).read_text()

    for field_name in ("vpn_client", "profile_name", "usergroup"):
        assert field_name in forms
        assert f'"{field_name}"' in views
        assert f"form.{field_name}" in template
