from unittest.mock import patch
import tasks


def test_collect_static_uses_vault_aware_entrypoint():
    with patch.object(tasks, "_ssh") as ssh:
        tasks._remote_collect_static("nb-ha-01")
    ssh.assert_called_once_with("nb-ha-01", "docker exec nautobot /usr/local/bin/shms-nautobot-entrypoint.sh nautobot-server collectstatic --noinput")


def test_vpn_only_promotion_refreshes_controller_without_restarting_tenants():
    from invoke import Context, Config
    context = Context(Config({"nautobot_docker_compose": {"nodes": ["nb-ha-01"]}}))
    with patch.object(tasks, "_resolve_image_updates", return_value=({"SHMS_VPN_IMAGE": "new"}, ["vpn"])), patch.object(tasks, "_remote_update_env"), patch.object(tasks, "_remote_restart_vpn_control") as restart, patch.object(tasks, "_remote_wait_healthy") as healthy, patch.object(tasks, "_remote_restart_app") as app_restart:
        tasks.promote_nodes.body(context, "test", components="vpn", yes=True)
    restart.assert_called_once_with("nb-ha-01")
    healthy.assert_called_once_with("nb-ha-01", "vpn-control-api")
    app_restart.assert_not_called()
