"""Ensure LDAP-mapped superusers are also staff users."""

import logging


LOGGER = logging.getLogger(__name__)
_PATCHED = False


def apply_ldap_superuser_staff_fix():
    """Patch django-auth-ldap so any superuser also gets is_staff=True."""
    global _PATCHED  # pylint: disable=global-statement
    if _PATCHED:
        return True

    try:
        from django_auth_ldap.backend import LDAPBackend
    except Exception as exc:  # pragma: no cover - defensive runtime patch
        LOGGER.warning("Could not import LDAPBackend for staff fix: %s", exc, exc_info=True)
        return False

    original_authenticate = LDAPBackend.authenticate
    original_populate_user = LDAPBackend.populate_user

    def _ensure_staff(user):
        if user and getattr(user, "is_superuser", False) and not getattr(user, "is_staff", False):
            user.is_staff = True
            try:
                user.save(update_fields=["is_staff"])
            except Exception:  # pragma: no cover - fallback
                user.save()
            LOGGER.info("Elevated LDAP superuser %s to staff", getattr(user, "username", "<unknown>"))
        return user

    def authenticate(self, request, username=None, password=None, **kwargs):
        user = original_authenticate(self, request, username=username, password=password, **kwargs)
        return _ensure_staff(user)

    def populate_user(self, username):
        user = original_populate_user(self, username)
        return _ensure_staff(user)

    LDAPBackend.authenticate = authenticate
    LDAPBackend.populate_user = populate_user
    _PATCHED = True
    LOGGER.info("Applied LDAP superuser=>staff runtime patch")
    return True
