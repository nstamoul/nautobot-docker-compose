#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat >&2 <<'EOF'
Usage:
  deploy_shms_vpn_control_api.sh <nb-ha-01|nb-ha-02> [--root /opt/nautobot] [--sync] [--pull] [--activate]

Safe HA workflow:
  # Pre-stage both nodes without starting or restarting anything.
  deploy_shms_vpn_control_api.sh nb-ha-01 --sync --pull
  deploy_shms_vpn_control_api.sh nb-ha-02 --sync --pull

  # Activate only the current app-active node.
  deploy_shms_vpn_control_api.sh nb-ha-01 --activate

  # During failover, stop tenant VPN slots on the old node, then activate the new node.
  deploy_shms_vpn_control_api.sh nb-ha-02 --activate

Actions:
  --sync      Copy runtime compose/scripts to the target node.
  --pull      Pull registry images referenced by the compose files.
  --activate  Start or update vpn-control-api on the explicitly named node.

This script never builds images on HA nodes. Build and push images via GitLab CI.
EOF
    exit 2
}

[[ $# -gt 0 ]] || usage
TARGET_HOST="$1"
shift
[[ -n "${TARGET_HOST}" ]] || usage

TARGET_ROOT="/opt/nautobot"
DO_SYNC="false"
DO_PULL="false"
DO_ACTIVATE="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --root)
            [[ -n "${2:-}" ]] || usage
            TARGET_ROOT="$2"
            shift 2
            ;;
        --sync)
            DO_SYNC="true"
            shift
            ;;
        --pull)
            DO_PULL="true"
            shift
            ;;
        --activate)
            DO_ACTIVATE="true"
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

if [[ "${DO_SYNC}" != "true" && "${DO_PULL}" != "true" && "${DO_ACTIVATE}" != "true" ]]; then
    echo "No action selected. Use --sync, --pull, and/or --activate." >&2
    usage
fi

copy_file() {
    local src="$1"
    local dst="$2"
    scp "$src" "${TARGET_HOST}:${dst}"
}

compose_cmd=(
    docker compose
    --project-name environments
    --project-directory "${TARGET_ROOT}/environments"
)

if [[ "${DO_SYNC}" == "true" ]]; then
    ssh "${TARGET_HOST}" "mkdir -p ${TARGET_ROOT}/vpn ${TARGET_ROOT}/scripts ${TARGET_ROOT}/git ${TARGET_ROOT}/environments"

    copy_file "./vpn/vpn.sh" "${TARGET_ROOT}/vpn/vpn.sh"
    copy_file "./scripts/bootstrap_shms_git_repositories.py" "${TARGET_ROOT}/scripts/bootstrap_shms_git_repositories.py"
    copy_file "./environments/docker-compose.shms-vpn.service.yml" "${TARGET_ROOT}/environments/docker-compose.shms-vpn.service.yml"
    copy_file "./environments/docker-compose.shms-vpn.queue.yml" "${TARGET_ROOT}/environments/docker-compose.shms-vpn.queue.yml"
    copy_file "./environments/docker-compose.shms-vpn.control.yml" "${TARGET_ROOT}/environments/docker-compose.shms-vpn.control.yml"

    ssh "${TARGET_HOST}" "chmod +x ${TARGET_ROOT}/vpn/vpn.sh"
fi

if [[ "${DO_PULL}" == "true" ]]; then
    ssh "${TARGET_HOST}" "cd ${TARGET_ROOT}/environments && ${compose_cmd[*]} -f docker-compose.shms-vpn.control.yml pull vpn-control-api"
    ssh "${TARGET_HOST}" "cd ${TARGET_ROOT}/environments && ${compose_cmd[*]} -f docker-compose.shms-vpn.service.yml pull vpn"
fi

if [[ "${DO_ACTIVATE}" == "true" ]]; then
    ssh "${TARGET_HOST}" "cd ${TARGET_ROOT}/environments && ${compose_cmd[*]} -f docker-compose.shms-vpn.control.yml up -d vpn-control-api"
fi

if [[ "${DO_SYNC}" == "true" ]]; then
    ssh "${TARGET_HOST}" '
for src in celery_worker nautobot; do
    if docker ps --format "{{.Names}}" | grep -qx "$src"; then
        docker cp "$src:/opt/nautobot/git/." "'"${TARGET_ROOT}"'/git/" 2>/dev/null || true
        exit 0
    fi
done
'
fi
