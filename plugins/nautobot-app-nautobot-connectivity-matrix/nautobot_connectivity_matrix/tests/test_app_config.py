"""Tests for app configuration."""

import importlib


def test_app_imports_from_source_tree(monkeypatch):
    """Importing the app from a git checkout should not require package metadata."""
    metadata = importlib.import_module("importlib.metadata")

    def raise_package_not_found(_name):
        raise metadata.PackageNotFoundError

    monkeypatch.setattr(metadata, "version", raise_package_not_found)

    app_module = importlib.reload(importlib.import_module("nautobot_connectivity_matrix"))

    assert app_module.__version__ == "0.1.0"
