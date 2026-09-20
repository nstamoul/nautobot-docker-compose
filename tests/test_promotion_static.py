from unittest.mock import patch
import tasks


def test_collect_static_uses_vault_aware_entrypoint():
    with patch.object(tasks, "_ssh") as ssh:
        tasks._remote_collect_static("nb-ha-01")
    ssh.assert_called_once_with("nb-ha-01", "docker exec nautobot /usr/local/bin/shms-nautobot-entrypoint.sh nautobot-server collectstatic --noinput")
