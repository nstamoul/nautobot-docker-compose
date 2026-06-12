from pathlib import Path


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "nbcot"
    / "inc"
    / "order_line_tree.html"
)


def test_line_tree_sticky_stack_sits_outside_horizontal_scroll_container():
    template = TEMPLATE.read_text()

    sticky_stack = template.index('data-line-sticky-stack')
    controls = template.index('data-line-sticky-controls')
    header_scroll = template.index('data-line-header-scroll')
    body_scroll = template.index('data-line-body-scroll')
    heading_row = template.index('class="nbcot-line-heading-row"')
    filter_row = template.index('class="nbcot-line-filter-row"')
    body_table = template.index('class="table table-hover table-condensed nbcot-line-body-table"')

    assert sticky_stack < body_scroll
    assert sticky_stack < controls < header_scroll < heading_row < filter_row < body_scroll < body_table
    assert 'class="nbcot-line-controls-row"' not in template
    assert "thead tr:first-child th" not in template
    assert "thead tr:nth-child(2) th" not in template


def test_line_tree_header_widths_and_horizontal_scroll_are_synced():
    template = TEMPLATE.read_text()

    assert "function syncHeaderWidths()" in template
    assert 'tree.querySelector("[data-line-header-scroll]")' in template
    assert 'tree.querySelector("[data-line-body-scroll]")' in template
    assert "headerScroll.scrollLeft = bodyScroll.scrollLeft" in template
    assert "bodyScroll.scrollLeft = headerScroll.scrollLeft" in template


def test_line_tree_columns_have_explicit_minimum_widths_for_horizontal_scroll():
    template = TEMPLATE.read_text()

    assert "function columnMinWidth(key)" in template
    assert "minWidth = Math.max(width, columnMinWidth(key))" in template
    assert '"description": 420' in template
    assert '"proof_of_delivery": 260' in template
    assert "width: max-content" in template


def test_line_tree_uses_fixed_scroll_controller_for_vertical_context():
    template = TEMPLATE.read_text()

    assert 'data-line-sticky-spacer' in template
    assert ".nbcot-line-sticky-stack.is-fixed" in template
    assert "function updateFixedStickyStack()" in template
    assert "window.addEventListener(\"scroll\", updateFixedStickyStack" in template
    assert "stickyStack.classList.add(\"is-fixed\")" in template
