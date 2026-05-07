"""Tests for interface option selection."""

from nautobot_connectivity_matrix.services.interface_options import collect_reserved_interface_ids


def test_collect_reserved_interface_ids_ignores_closed_plans():
    """Only non-closed connection plans should reserve interface options."""
    rows = [
        {"status": "draft", "interface_a_id": "a1", "interface_b_id": "b1"},
        {"status": "validated", "interface_a_id": "a2", "interface_b_id": None},
        {"status": "approved", "interface_a_id": None, "interface_b_id": "b2"},
        {"status": "conflict", "interface_a_id": "a3", "interface_b_id": ""},
        {"status": "executed", "interface_a_id": "a4", "interface_b_id": "b4"},
        {"status": "failed", "interface_a_id": "a5", "interface_b_id": "b5"},
    ]

    assert collect_reserved_interface_ids(rows) == {"a1", "b1", "a2", "b2", "a3"}
