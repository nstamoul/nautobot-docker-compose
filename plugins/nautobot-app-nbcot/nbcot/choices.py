"""Choice sets for NBCOT."""

from nautobot.apps.choices import ChoiceSet


class CiscoEnvironmentChoices(ChoiceSet):
    """Cisco API environments supported by NBCOT."""

    POE = "poe"
    PROD = "prod"
    UAT = "uat"

    CHOICES = (
        (POE, "POE"),
        (PROD, "PROD"),
        (UAT, "UAT"),
    )


class SyncStatusChoices(ChoiceSet):
    """Order synchronization status."""

    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"

    CHOICES = (
        (SUCCESS, "Success"),
        (ERROR, "Error"),
        (PENDING, "Pending"),
    )


class ChangeSourceChoices(ChoiceSet):
    """Source that produced an order update."""

    MANUAL = "manual"
    POLL = "poll"
    EVENT = "event"

    CHOICES = (
        (MANUAL, "Manual"),
        (POLL, "Poll"),
        (EVENT, "Event"),
    )


class OrderUpdateTypeChoices(ChoiceSet):
    """Type of tracked order change."""

    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    DATE_CHANGED = "date_changed"
    EXCEPTION_CHANGED = "exception_changed"
    SYNC_ERROR = "sync_error"

    CHOICES = (
        (CREATED, "Created"),
        (STATUS_CHANGED, "Status Changed"),
        (DATE_CHANGED, "Date Changed"),
        (EXCEPTION_CHANGED, "Exception Changed"),
        (SYNC_ERROR, "Sync Error"),
    )
