"""Create fixtures for tests."""

from nbcot.models import CiscoOrder, CiscoOrderLine, CiscoOrderUpdate


def create_ciscoorder(order_number="SO-1001", **kwargs):
    """Create a tracked Cisco order for tests."""
    defaults = {
        "environment": "poe",
        "customer_po_number": "PO-1001",
        "account_name": "Acme Corp",
        "account_number": "A-1001",
        "status": "Submitted",
        "is_tracked": True,
    }
    defaults.update(kwargs)
    return CiscoOrder.objects.create(order_number=order_number, **defaults)


def create_line(order, line_key="1", **kwargs):
    """Create a Cisco order line for tests."""
    defaults = {
        "line_number": "1",
        "sku": "SKU-1",
        "description": "Test line",
        "status": "Open",
        "quantity_ordered": 1,
        "quantity_fulfilled": 0,
        "quantity_backordered": 1,
    }
    defaults.update(kwargs)
    return CiscoOrderLine.objects.create(order=order, line_key=line_key, **defaults)


def create_update(order, summary="Order created", **kwargs):
    """Create an order update entry for tests."""
    defaults = {
        "update_type": "created",
        "source": "manual",
        "summary": summary,
    }
    defaults.update(kwargs)
    return CiscoOrderUpdate.objects.create(order=order, **defaults)
