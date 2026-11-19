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


# --- vpn-control-api must never be recreated without the locator overlay -----------------------------------------

CONTROL = tasks.VPN_CONTROL_COMPOSE_FILE
LOCATOR = tasks.VPN_CONTROL_LOCATOR_COMPOSE_FILE


class _FakeNode:
    """Answers tasks._ssh like an HA node: the overlay probe, `docker port`, and compose commands."""

    def __init__(self, overlay="overlay", port_before="127.0.0.1:5011", port_after="127.0.0.1:5011"):
        self.overlay, self.port_before, self.port_after = overlay, port_before, port_after
        self.commands = []
        self.recreated = False

    def __call__(self, node, cmd, check=True, capture=False):
        import subprocess

        self.commands.append(cmd)
        out = ""
        if "then echo absent" in cmd:
            out = self.overlay + "\n"
        elif cmd.startswith("docker port vpn-control-api"):
            out = (self.port_after if self.recreated else self.port_before) + "\n"
        elif " up -d vpn-control-api" in cmd:
            self.recreated = True
        return subprocess.CompletedProcess(["ssh", node, cmd], 0, stdout=out, stderr="")

    @property
    def ups(self):
        return [c for c in self.commands if " up -d vpn-control-api" in c]


def test_remote_restart_includes_locator_overlay_and_verifies_port(monkeypatch):
    monkeypatch.delenv("NO_LOCATOR_NODES", raising=False)
    node = _FakeNode()
    with patch.object(tasks, "_ssh", node):
        tasks._remote_restart_vpn_control("nb-ha-01")
    (up,) = node.ups
    assert f"docker compose -f {CONTROL} -f {LOCATOR} up -d vpn-control-api" in up
    assert node.commands[-1].startswith("docker port vpn-control-api 5001/tcp")


def test_remote_restart_fails_loudly_when_locator_is_not_published(monkeypatch):
    import pytest

    monkeypatch.delenv("NO_LOCATOR_NODES", raising=False)
    monkeypatch.setattr(tasks, "VPN_CONTROL_LOCATOR_WAIT_SECONDS", 0)
    node = _FakeNode(port_after="")
    with patch.object(tasks, "_ssh", node), patch.object(tasks.time, "sleep"):
        with pytest.raises(RuntimeError, match="does not publish 127.0.0.1.*DOWN"):
            tasks._remote_restart_vpn_control("nb-ha-01")
    assert len(node.ups) == 1


def test_remote_restart_refuses_to_drop_a_published_locator(monkeypatch):
    import pytest

    for env, overlay in (("", "absent"), ("", "not-api-key"), ("nb-ha-01", "overlay")):
        monkeypatch.setenv("NO_LOCATOR_NODES", env)
        node = _FakeNode(overlay=overlay)
        with patch.object(tasks, "_ssh", node):
            with pytest.raises(RuntimeError, match="Refusing"):
                tasks._remote_restart_vpn_control("nb-ha-01")
        assert node.ups == []


def test_remote_restart_without_overlay_on_a_node_that_never_had_it(monkeypatch):
    monkeypatch.delenv("NO_LOCATOR_NODES", raising=False)
    node = _FakeNode(overlay="absent", port_before="", port_after="")
    with patch.object(tasks, "_ssh", node):
        tasks._remote_restart_vpn_control("nb-ha-02")
    (up,) = node.ups
    assert f"docker compose -f {CONTROL} up -d vpn-control-api" in up and LOCATOR not in up


def test_remote_pull_uses_the_same_compose_files(monkeypatch):
    monkeypatch.delenv("NO_LOCATOR_NODES", raising=False)
    node = _FakeNode()
    with patch.object(tasks, "_ssh", node):
        tasks._remote_pull_vpn_control("nb-ha-01")
    assert f"docker compose -f {CONTROL} -f {LOCATOR} pull vpn-control-api" in node.commands[-1]


def test_unexpected_probe_answer_is_an_error(monkeypatch):
    import pytest

    monkeypatch.delenv("NO_LOCATOR_NODES", raising=False)
    with patch.object(tasks, "_ssh", _FakeNode(overlay="")):
        with pytest.raises(RuntimeError, match="unexpected answer"):
            tasks._remote_vpn_control_files("nb-ha-01")


def test_local_compose_files_follow_overlay_and_auth_mode(tmp_path):
    (tmp_path / CONTROL).write_text("services: {}\n")
    assert tasks._local_vpn_control_files(tmp_path) == [CONTROL]
    (tmp_path / LOCATOR).write_text("services: {}\n")
    (tmp_path / ".env").write_text("VPN_CONTROL_AUTH_MODE=mtls\n")
    assert tasks._local_vpn_control_files(tmp_path) == [CONTROL]
    (tmp_path / ".env").write_text("FOO=1\nVPN_CONTROL_AUTH_MODE=api-key\n")
    assert tasks._local_vpn_control_files(tmp_path) == [CONTROL, LOCATOR]
