"""Contract tests for deploy_shms_vpn_control_api.sh, driven against a stub `ssh` (no network, no docker).

Recreating vpn-control-api with only docker-compose.shms-vpn.control.yml drops the locator overlay
(127.0.0.1:5011 and the peer key mount): the slot locator goes down and access broker sessions fail.
The script must add the overlay wherever the node has it and must fail when the port is not published.
"""

import json
import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy_shms_vpn_control_api.sh"
CONTROL = "docker-compose.shms-vpn.control.yml"
LOCATOR = "docker-compose.shms-vpn.control.locator.yml"

STUB = textwrap.dedent(
    r'''
    #!/usr/bin/env python3
    """Fake ssh: logs every call and answers like an HA node described by STUB_* variables."""
    import json, os, sys

    node, cmd = sys.argv[-2], sys.argv[-1]
    with open(os.environ["STUB_LOG"], "a") as fh:
        fh.write(json.dumps({"node": node, "cmd": cmd}) + "\n")
    if os.environ.get("STUB_SSH_DOWN") == "1":
        sys.stderr.write("ssh: connect to host: timed out\n")
        sys.exit(255)
    if "then echo absent" in cmd:  # the overlay probe
        print(os.environ.get("STUB_OVERLAY", "overlay"))
    elif cmd.startswith("docker port vpn-control-api"):
        state = os.environ["STUB_STATE"]
        recreated = os.path.exists(state)
        port = os.environ.get("STUB_PORT_AFTER" if recreated else "STUB_PORT_BEFORE", "")
        if port:
            print(port)
    elif " up -d vpn-control-api" in cmd:
        open(os.environ["STUB_STATE"], "w").close()
    sys.exit(0)
    '''
).lstrip()

PUBLISHED = "127.0.0.1:5011"


@pytest.fixture()
def run(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "ssh"
    stub.write_text(STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "ssh.log"

    def _run(*args, **env):
        log.write_text("")
        state = tmp_path / "recreated"
        if state.exists():
            state.unlink()
        base_env = {k: v for k, v in os.environ.items() if k != "NO_LOCATOR_NODES"}
        full_env = {
            **base_env,
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "STUB_LOG": str(log),
            "STUB_STATE": str(state),
            "LOCATOR_WAIT_SECONDS": "0",
            **env,
        }
        proc = subprocess.run(
            ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=full_env, cwd=ROOT, check=False
        )
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        return proc, calls

    return _run


def _up(calls):
    return [c["cmd"] for c in calls if " up -d vpn-control-api" in c["cmd"]]


def test_activate_includes_locator_overlay_and_checks_the_port(run):
    proc, calls = run("nb-ha-01", "--activate", STUB_PORT_BEFORE=PUBLISHED, STUB_PORT_AFTER=PUBLISHED)
    assert proc.returncode == 0, proc.stderr
    (up,) = _up(calls)
    assert f"-f {CONTROL} -f {LOCATOR} up -d vpn-control-api" in up
    assert "--project-name environments" in up
    cmds = [c["cmd"] for c in calls]
    assert any(c.startswith("docker port vpn-control-api 5001/tcp") for c in cmds[cmds.index(up) + 1 :])
    assert "Locator published on nb-ha-01" in proc.stdout


def test_activate_fails_loudly_when_locator_is_not_published(run):
    proc, calls = run("nb-ha-01", "--activate", STUB_PORT_BEFORE=PUBLISHED, STUB_PORT_AFTER="")
    assert proc.returncode != 0
    assert "does not publish 127.0.0.1" in proc.stderr
    assert "DOWN" in proc.stderr
    assert len(_up(calls)) == 1


def test_node_without_overlay_uses_the_control_file_only(run):
    proc, calls = run("nb-ha-01", "--activate", STUB_OVERLAY="absent")
    assert proc.returncode == 0, proc.stderr
    (up,) = _up(calls)
    assert f"-f {CONTROL} up -d vpn-control-api" in up
    assert LOCATOR not in up


def test_mtls_node_does_not_get_the_overlay(run):
    proc, calls = run("nb-ha-02", "--activate", STUB_OVERLAY="not-api-key")
    assert proc.returncode == 0, proc.stderr
    assert LOCATOR not in _up(calls)[0]
    assert "not api-key" in proc.stdout


@pytest.mark.parametrize(
    "env",
    [
        {"STUB_OVERLAY": "absent"},
        {"STUB_OVERLAY": "not-api-key"},
        {"NO_LOCATOR_NODES": "nb-ha-02 nb-ha-01"},
    ],
)
def test_refuses_to_recreate_a_publishing_api_without_the_overlay(run, env):
    proc, calls = run("nb-ha-01", "--activate", STUB_PORT_BEFORE=PUBLISHED, **env)
    assert proc.returncode != 0
    assert "Refusing" in proc.stderr
    assert _up(calls) == []


def test_no_locator_nodes_skips_the_overlay_without_probing(run):
    proc, calls = run("nb-ha-02", "--activate", NO_LOCATOR_NODES="nb-ha-02")
    assert proc.returncode == 0, proc.stderr
    assert LOCATOR not in _up(calls)[0]
    assert not any("then echo absent" in c["cmd"] for c in calls)


def test_unreachable_node_aborts_before_any_change(run):
    proc, calls = run("nb-ha-01", "--activate", STUB_SSH_DOWN="1")
    assert proc.returncode != 0
    assert "nothing was changed" in proc.stderr
    assert _up(calls) == []


def test_pull_uses_the_same_compose_files(run):
    proc, calls = run("nb-ha-01", "--pull")
    assert proc.returncode == 0, proc.stderr
    pulls = [c["cmd"] for c in calls if "pull vpn-control-api" in c["cmd"]]
    assert len(pulls) == 1 and f"-f {CONTROL} -f {LOCATOR} pull vpn-control-api" in pulls[0]
    assert _up(calls) == []


def test_overlay_probe_reads_auth_mode_from_the_node_env():
    text = SCRIPT.read_text()
    assert "VPN_CONTROL_AUTH_MODE=.?api-key.?" in text
    assert f'LOCATOR_COMPOSE_FILE="{LOCATOR}"' in text
