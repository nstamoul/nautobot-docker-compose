from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_vpn_image_dockerfile_selects_vault_and_cisco_packages_by_target_architecture():
    dockerfile = (REPO_ROOT / "vpn" / "vpn" / "Dockerfile").read_text()

    assert "ARG TARGETARCH" in dockerfile
    assert "case \"${TARGETARCH}\"" in dockerfile
    assert "amd64) VAULT_ARCH=\"amd64\"; DEB_ARCH=\"amd64\"" in dockerfile
    assert "arm64) VAULT_ARCH=\"arm64\"; DEB_ARCH=\"arm64\"" in dockerfile
    assert "vault_${VAULT_VERSION}_linux_${VAULT_ARCH}.zip" in dockerfile
    assert "cisco-secure-client-vpn-cli_*_${DEB_ARCH}.deb" in dockerfile
    assert "cisco-secure-client-vpn-cli_*_amd64.deb" not in dockerfile


def test_shms_vpn_compose_uses_registry_images_instead_of_node_local_builds():
    vpn_service = (REPO_ROOT / "environments" / "docker-compose.shms-vpn.service.yml").read_text()
    control = (REPO_ROOT / "environments" / "docker-compose.shms-vpn.control.yml").read_text()
    env_example = (REPO_ROOT / "environments" / "local.shms.example.env").read_text()
    upstream_deploy = (REPO_ROOT / "deploy_shms_upstream_node1.sh").read_text()

    assert 'image: "${SHMS_VPN_IMAGE:?set SHMS_VPN_IMAGE}"' in vpn_service
    assert "context: ../vpn/vpn" not in vpn_service
    assert 'image: "${SHMS_VPN_CONTROL_API_IMAGE:?set SHMS_VPN_CONTROL_API_IMAGE}"' in control
    assert "context: ../vpn/VPN_Control_API" not in control
    assert "SHMS_VPN_IMAGE=" in env_example
    assert "SHMS_VPN_CONTROL_API_IMAGE=" in env_example
    assert "SHMS_VPN_IMAGE" in upstream_deploy
    assert "SHMS_VPN_CONTROL_API_IMAGE" in upstream_deploy


def test_vpn_control_api_image_contains_application_code_without_workspace_source():
    dockerfile = (REPO_ROOT / "vpn" / "VPN_Control_API" / "Dockerfile").read_text()

    assert dockerfile.startswith("FROM python:3.11-slim")
    assert "COPY app.py" in dockerfile
    assert "COPY __init__.py" in dockerfile
    assert "/opt/vpn-control/vpn/VPN_Control_API" in dockerfile
    assert 'PYTHONPATH="/workspace/vpn:/opt/vpn-control/vpn"' in dockerfile


def test_vpn_control_deploy_script_is_explicit_and_does_not_build_on_ha_nodes():
    script = (REPO_ROOT / "deploy_shms_vpn_control_api.sh").read_text()

    assert 'TARGET_HOST="${1:-nb-ha-01}"' not in script
    assert '[[ -n "${TARGET_HOST}" ]]' in script
    assert "--pull" in script
    assert "--activate" in script
    assert "pull vpn-control-api" in script
    assert "pull vpn" in script
    assert "up -d --build" not in script


def test_gitlab_ci_builds_and_pushes_release_images_with_tracked_cisco_artifacts():
    ci = (REPO_ROOT / ".gitlab-ci.yml").read_text()
    artifact_readme = (REPO_ROOT / "vpn" / "vpn" / "cisco-secure-client" / "README.md").read_text()
    artifact_gitignore = (REPO_ROOT / "vpn" / "vpn" / "cisco-secure-client" / ".gitignore").read_text()

    assert "build:shms-vpn:" in ci
    assert "build:shms-vpn-control-api:" in ci
    assert "CISCO_SECURE_CLIENT_AMD64_TGZ" not in ci
    assert "CISCO_SECURE_CLIENT_ARM64_TGZ" not in ci
    assert "cisco-secure-client-linux64-5.1.17.3382-predeploy-deb-k9.tgz" in ci
    assert "cisco-secure-client-linux-arm64-5.1.17.3382-predeploy-deb-k9.tgz" in ci
    assert "CI_COMMIT_REF_PROTECTED" in ci
    assert "when: manual" in ci
    assert "docker buildx build" in ci
    assert "--push" in ci
    assert "CI_REGISTRY_IMAGE" in ci
    assert "linux/amd64,linux/arm64" in ci
    assert "tonistiigi/binfmt --install amd64,arm64" in ci
    assert "approved Linux predeploy tarballs should be tracked here" in artifact_readme
    assert "!cisco-secure-client-linux64-*-predeploy-deb-k9.tgz" in artifact_gitignore
    assert "!cisco-secure-client-linux-arm64-*-predeploy-deb-k9.tgz" in artifact_gitignore
