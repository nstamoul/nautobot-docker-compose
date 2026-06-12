from pathlib import Path


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "nbcot"
    / "inc"
    / "order_line_tree.html"
)


def test_line_tree_controls_are_part_of_sticky_table_header_stack():
    template = TEMPLATE.read_text()

    controls_row = template.index('class="nbcot-line-controls-row"')
    heading_row = template.index('class="nbcot-line-heading-row"')
    filter_row = template.index('class="nbcot-line-filter-row"')
    controls_marker = template.index('data-line-sticky-controls')
    table = template.index("<table")

    assert table < controls_row < heading_row < filter_row
    assert controls_row < controls_marker < heading_row
    assert "thead tr:first-child th" not in template
    assert "thead tr:nth-child(2) th" not in template
