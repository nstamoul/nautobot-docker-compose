"""Navigation tests for NBCOT."""

from pathlib import Path

NBCOT_ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = NBCOT_ROOT / "navigation.py"
LIST_TEMPLATE = NBCOT_ROOT / "templates" / "nbcot" / "ciscoorder_list.html"


def test_archived_orders_is_exposed_in_nbcot_navigation_after_tracked_orders():
    """Archived orders should live in the NBCOT navigation, not as a table action."""
    navigation_source = NAVIGATION.read_text()

    tracked_position = navigation_source.index('name="Tracked Orders"')
    archived_position = navigation_source.index('name="Archived Orders"')
    archived_link_position = navigation_source.index('link="plugins:nbcot:ciscoorder_archived_list"')

    assert tracked_position < archived_position
    assert tracked_position < archived_link_position
    assert navigation_source.count('name="Archived Orders"') == 1


def test_active_order_list_does_not_render_archived_orders_action_button():
    """The active list toolbar should not duplicate the Archived Orders navigation item."""
    template = LIST_TEMPLATE.read_text()

    assert "plugins:nbcot:ciscoorder_archived_list" not in template
    assert "Archived Orders" not in template
