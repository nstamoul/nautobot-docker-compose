from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_shms_app_compose_uses_vault_agent_token_bootstrap():
    compose = (REPO_ROOT / "environments" / "docker-compose.shms-app.yml").read_text()

    assert "vault-agent-nautobot-web:" in compose
    assert "vault-agent-nautobot-celery:" in compose
    assert "vault-agent-nautobot-beat:" in compose
    assert "shms_vault_agent_web_runtime:/run/shms-vault-web" in compose
    assert "shms_vault_agent_celery_runtime:/run/shms-vault-celery" in compose
    assert "shms_vault_agent_beat_runtime:/run/shms-vault-beat" in compose
    assert "shms-nautobot-entrypoint.sh" in compose
    assert "SHMS_VAULT_AGENT_ENABLED" in compose
    assert "SHMS_VAULT_TOKEN_FILE" in compose
    assert "type: \"tmpfs\"" in compose
    assert "mode=1777" in compose


def test_vault_agent_configs_use_service_specific_roles_and_token_sinks():
    configs = {
        "web": (
            REPO_ROOT / "environments" / "vault-agent-nautobot-web.hcl",
            "shms-nautobot-web",
            "/run/shms-vault-web/nautobot.token",
        ),
        "celery": (
            REPO_ROOT / "environments" / "vault-agent-nautobot-celery.hcl",
            "shms-nautobot-celery",
            "/run/shms-vault-celery/celery.token",
        ),
        "beat": (
            REPO_ROOT / "environments" / "vault-agent-nautobot-beat.hcl",
            "shms-nautobot-beat",
            "/run/shms-vault-beat/beat.token",
        ),
    }
    for path, role, token_path in configs.values():
        config = path.read_text()
        assert 'method "cert"' in config
        assert f'name = "{role}"' in config
        assert "/opt/nautobot/certs/vault-agent/nautobot-service.crt" in config
        assert "/opt/nautobot/certs/vault-agent/nautobot-service.key" in config
        assert 'sink "file"' in config
        assert "mode = 0644" in config
        assert token_path in config


def test_nautobot_entrypoint_exports_hashicorp_vault_token_from_agent_file(tmp_path):
    token_file = tmp_path / "nautobot.token"
    token_file.write_text("agent-token\n")
    script = REPO_ROOT / "scripts" / "shms-nautobot-entrypoint.sh"
    fake_docker_entrypoint = tmp_path / "docker-entrypoint.sh"
    fake_docker_entrypoint.write_text(
        "#!/usr/bin/env sh\n"
        "printf '%s\\n' \"$HASHICORP_VAULT_TOKEN\" \"$VAULT_TOKEN\" \"$@\"\n"
    )
    fake_docker_entrypoint.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "SHMS_VAULT_AGENT_ENABLED": "true",
            "SHMS_VAULT_TOKEN_FILE": str(token_file),
            "SHMS_DOCKER_ENTRYPOINT": str(fake_docker_entrypoint),
        }
    )

    result = subprocess.run(
        ["sh", str(script), "nautobot-server", "start"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == ["agent-token", "agent-token", "nautobot-server", "start"]


def test_upstream_deploy_script_no_longer_renders_static_vault_token():
    script = (REPO_ROOT / "deploy_shms_upstream_node1.sh").read_text()

    assert "HASHICORP_VAULT_TOKEN=__VAULT_NAUTOBOT_TOKEN__" not in script
    assert 'secrets["VAULT_NAUTOBOT_TOKEN"]' not in script
    assert "SHMS_VAULT_AGENT_ENABLED=true" in script
    assert "SHMS_VAULT_TOKEN_FILE=/run/shms-vault-web/nautobot.token" in script
