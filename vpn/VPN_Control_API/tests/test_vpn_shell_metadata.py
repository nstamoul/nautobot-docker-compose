from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_vault_fetch_exports_vpn_client_and_cisco_metadata(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_vault = fake_bin / "vault"
    fake_vault.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1 $2" == "token lookup" ]]; then
  exit 0
fi
if [[ "$1 $2 $3 $4" == "kv metadata get -format=json" ]]; then
  cat <<'JSON'
{"data":{"custom_metadata":{"vpn_type":"cisco-anyconnect","vpn_client":"cisco-secure-client","profile_name":"e-Trikala VPN Profile Admins","usergroup":"RAVPN_Admins","host":"vpn.example.test","port":"443"}}}
JSON
  exit 0
fi
if [[ "$1 $2 $3" == "kv get -format=json" ]]; then
  cat <<'JSON'
{"data":{"data":{"username":"user@example.test","password":"secret"}}}
JSON
  exit 0
fi
exit 1
"""
    )
    fake_vault.chmod(fake_vault.stat().st_mode | stat.S_IXUSR)

    script = REPO_ROOT / "vpn" / "vpn" / "vault_fetch.sh"
    command = (
        f"source {script}; "
        "printf '%s\\n' "
        "\"$VAULT_VPN_CLIENT\" "
        "\"$VAULT_CISCO_PROFILE_NAME\" "
        "\"$VAULT_CISCO_USERGROUP\""
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "VAULT_ADDR": "https://vault.example.test:8200",
            "VAULT_TOKEN": "test-token",
            "VPN_SECRET_PATH": "kv/e-Trikala/vpn",
            "USE_VAULT": "true",
        }
    )

    result = subprocess.run(["bash", "-lc", command], env=env, check=True, capture_output=True, text=True)

    assert result.stdout.splitlines()[-3:] == [
        "cisco-secure-client",
        "e-Trikala VPN Profile Admins",
        "RAVPN_Admins",
    ]


def test_openconnect_entrypoint_supports_anyconnect_usergroup_metadata():
    entrypoint = (REPO_ROOT / "vpn" / "vpn" / "entrypoint.sh").read_text()
    wrapper = (REPO_ROOT / "vpn" / "vpn.sh").read_text()
    dockerfile = (REPO_ROOT / "vpn" / "vpn" / "Dockerfile").read_text()

    assert "VAULT_CISCO_USERGROUP" in entrypoint
    assert "CISCO_USERGROUP" in entrypoint
    assert "--usergroup" in entrypoint
    assert "--usergroup" in wrapper
    assert "CISCO_USERGROUP" in wrapper
    assert "--vpn-client" in wrapper
    assert "--profile-name" in wrapper
    assert "run_cisco_secure_client" in entrypoint
    assert "ensure_cisco_secure_client_profile" in entrypoint
    assert "host-runtime only" not in entrypoint
    assert "cisco-secure-client)" in entrypoint
    assert "cisco-secure-client" in dockerfile
