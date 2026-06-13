from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_active_worker_button_links_to_worker_detail_page():
    dashboard_template = (
        PLUGIN_ROOT / "nautobot_vpn_manager/templates/nautobot_vpn_manager/dashboard.html"
    ).read_text()

    assert "{% url 'plugins:nautobot_vpn_manager:worker_detail' worker.worker_id %}" in dashboard_template


def test_dashboard_uses_worker_status_fields_consistently_with_steering_page():
    dashboard_template = (
        PLUGIN_ROOT / "nautobot_vpn_manager/templates/nautobot_vpn_manager/dashboard.html"
    ).read_text()

    assert "{% if worker.is_online %}" in dashboard_template
    assert "{% elif worker.stale %}" in dashboard_template
    assert "{{ worker.status|default:\"unknown\"|upper }}" in dashboard_template
    assert "{{ worker.status_source|default:\"piconfig heartbeat\" }}" in dashboard_template
    assert "Rendered {% now \"Y-m-d H:i:s T\" %}." in dashboard_template
    assert "{{ worker.heartbeat_age_seconds }}s ago" in dashboard_template
    assert "worker.status|default:\"online\"" not in dashboard_template
    assert '<div class="vpn-card__title">\n                  <span class="vpn-led vpn-led--up"></span>' not in dashboard_template


def test_dashboard_worker_steering_and_detail_show_queue_drift_state():
    dashboard_template = (
        PLUGIN_ROOT / "nautobot_vpn_manager/templates/nautobot_vpn_manager/dashboard.html"
    ).read_text()
    workers_template = (PLUGIN_ROOT / "nautobot_vpn_manager/templates/nautobot_vpn_manager/workers.html").read_text()
    worker_detail_template = (
        PLUGIN_ROOT / "nautobot_vpn_manager/templates/nautobot_vpn_manager/worker_detail.html"
    ).read_text()

    for template in (dashboard_template, workers_template, worker_detail_template):
        assert "Queue drift" in template
        assert "{{ worker.queue_drift_status|default:\"unknown\"|upper }}" in template
        assert "{{ worker.queue_drift_summary|default:\"-\" }}" in template


def test_worker_steering_filters_are_live_multiselect_and_date_only():
    workers_template = (PLUGIN_ROOT / "nautobot_vpn_manager/templates/nautobot_vpn_manager/workers.html").read_text()

    assert 'data-live-filter-form' in workers_template
    assert 'data-filter-menu' in workers_template
    assert 'type="checkbox" name="queue"' in workers_template
    assert 'type="checkbox" name="status"' in workers_template
    assert 'checkedValues("queue")' in workers_template
    assert 'checkedValues("status")' in workers_template
    assert 'type="date" name="assignment_from"' in workers_template
    assert 'type="date" name="assignment_to"' in workers_template
    assert 'type="date" name="heartbeat_from"' in workers_template
    assert 'type="date" name="heartbeat_to"' in workers_template
    assert "var assignmentFrom =" in workers_template
    assert "var assignmentTo =" in workers_template
    assert "row.dataset.workerAssignment" in workers_template
    assert "function matchesWildcard" in workers_template
    assert 'select id="worker_queue"' not in workers_template
    assert '<section class="vpn-panel vpn-panel--filters">\n    <div class="vpn-panel__body">\n      <form' in workers_template
    assert 'overflow: visible' in workers_template
    assert 'worker.last_assignment|default:"-"|slice:":10"' in workers_template
    assert 'worker.last_heartbeat|default:"never"|slice:":10"' in workers_template


def test_worker_steering_table_columns_are_sortable():
    workers_template = (PLUGIN_ROOT / "nautobot_vpn_manager/templates/nautobot_vpn_manager/workers.html").read_text()

    for key in ("worker", "status", "host", "current", "desired", "assignment", "heartbeat"):
        assert f'data-sort-button="{key}"' in workers_template
        assert f'data-sort-{key}="' in workers_template

    assert 'data-sort-direction="none"' in workers_template
    assert "function applyTableSort" in workers_template
    assert "compareSortValues" in workers_template
