"""Tests for SHMS production image authority guardrails."""

import sys
import types

import pytest


invoke = types.ModuleType("invoke")


class Collection:
    """Minimal invoke.Collection stub for importing tasks.py in unit tests."""

    def __init__(self, *_args, **_kwargs):
        self.tasks = []

    def configure(self, *_args, **_kwargs):
        return None

    def add_task(self, task_func):
        self.tasks.append(task_func)


def invoke_task(*args, **_kwargs):
    """Minimal invoke.task stub supporting both decorator forms."""
    if args and callable(args[0]):
        return args[0]

    def decorator(function):
        return function

    return decorator


invoke.Collection = Collection
invoke.task = invoke_task
sys.modules.setdefault("invoke", invoke)

import tasks  # noqa: E402  pylint: disable=wrong-import-position


def test_nautobot_pin_rejects_old_compose_built_image():
    """The legacy compose-built Nautobot namespace must not be promotable."""
    with pytest.raises(ValueError) as exc:
        tasks._validate_image_pin(
            "SHMS_NAUTOBOT_IMAGE",
            "ghcr.io/nstamoul/nautobot-docker-compose/shms-nautobot:e27a47bf",
        )

    message = str(exc.value)
    assert "SHMS_NAUTOBOT_IMAGE must use canonical image repository ghcr.io/nstamoul/shms-nautobot" in message
    assert "old compose-built Nautobot image namespace" in message


def test_nautobot_pin_accepts_canonical_digest():
    """Digest-pinned canonical shms-nautobot images are valid."""
    tasks._validate_image_pin(
        "SHMS_NAUTOBOT_IMAGE",
        "ghcr.io/nstamoul/shms-nautobot@sha256:0123456789abcdef",
    )


def test_resolve_image_updates_uses_canonical_nautobot_repo(monkeypatch):
    """Promotion digest resolution must write the canonical Nautobot package."""
    monkeypatch.setattr(tasks, "_gh_digest", lambda package, tag: "sha256:abc123")

    updates, selected = tasks._resolve_image_updates("main-deadbee", "nautobot")

    assert selected == ["nautobot"]
    assert updates == {"SHMS_NAUTOBOT_IMAGE": "ghcr.io/nstamoul/shms-nautobot@sha256:abc123"}


def test_remote_env_update_rejects_bad_image_before_ssh(monkeypatch):
    """Remote promotion must fail locally before touching production env files."""
    called = False

    def fake_ssh(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(tasks, "_ssh", fake_ssh)

    with pytest.raises(ValueError):
        tasks._remote_update_env(
            "nb-ha-01",
            {
                "SHMS_NAUTOBOT_IMAGE": (
                    "ghcr.io/nstamoul/nautobot-docker-compose/shms-nautobot:e27a47bf"
                )
            },
        )

    assert called is False
