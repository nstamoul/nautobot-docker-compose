"""Lightweight Nautobot configuration for local NBCOT tests."""

from pathlib import Path

from development.nautobot_config import *  # noqa: F403,F401

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASES = {  # noqa: F405
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / "development" / "nbcot-test.sqlite3"),
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "nbcot-testing",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CONSTANCE_BACKEND = "constance.backends.memory.MemoryBackend"
