"""Tests for materialized interface naming/type helpers."""

from nautobot_connectivity_matrix.services.interface_finalization import (
    infer_interface_type_from_name,
    replace_first_number,
)


def test_replace_first_number_retargets_stack_member_only():
    """Stack member substitution changes the first numeric run only."""
    assert replace_first_number("TwentyFiveGigE1/{module}/1", "2") == "TwentyFiveGigE2/{module}/1"
    assert replace_first_number("GigabitEthernet1/0/48", "3") == "GigabitEthernet3/0/48"


def test_infer_interface_type_from_matrix_names():
    """Old matrix interface names get useful concrete interface types."""
    assert infer_interface_type_from_name("TwentyFiveGigE1/0/1") == "25gbase-x-sfp28"
    assert infer_interface_type_from_name("TenGigabitEthernet1/1/1") == "10gbase-x-sfpp"
    assert infer_interface_type_from_name("GigabitEthernet1/0/1") == "1000base-t"
    assert infer_interface_type_from_name("Vlan100") == "virtual"
