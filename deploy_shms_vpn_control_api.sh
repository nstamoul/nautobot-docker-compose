#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${1:-nb-ha-01}"
TARGET_ROOT="/opt/nautobot"

copy_file() {
    local src="$1"
    local dst="$2"
    scp "$src" "${TARGET_HOST}:${dst}"
}

ssh "${TARGET_HOST}" "mkdir -p ${TARGET_ROOT}/vpn/VPN_Control_API"
ssh "${TARGET_HOST}" "mkdir -p ${TARGET_ROOT}/scripts"
ssh "${TARGET_HOST}" "mkdir -p ${TARGET_ROOT}/git"

copy_file "./vpn/VPN_Control_API/app.py" "${TARGET_ROOT}/vpn/VPN_Control_API/app.py"
copy_file "./vpn/VPN_Control_API/Dockerfile" "${TARGET_ROOT}/vpn/VPN_Control_API/Dockerfile"
copy_file "./vpn/VPN_Control_API/requirements.txt" "${TARGET_ROOT}/vpn/VPN_Control_API/requirements.txt"
copy_file "./vpn/VPN_Control_API/__init__.py" "${TARGET_ROOT}/vpn/VPN_Control_API/__init__.py"
copy_file "./vpn/VPN_Control_API/README.md" "${TARGET_ROOT}/vpn/VPN_Control_API/README.md"
copy_file "./vpn/vpn.sh" "${TARGET_ROOT}/vpn/vpn.sh"
copy_file "./scripts/bootstrap_shms_git_repositories.py" "${TARGET_ROOT}/scripts/bootstrap_shms_git_repositories.py"
copy_file "./environments/docker-compose.shms-vpn.service.yml" "${TARGET_ROOT}/environments/docker-compose.shms-vpn.service.yml"
copy_file "./environments/docker-compose.shms-vpn.queue.yml" "${TARGET_ROOT}/environments/docker-compose.shms-vpn.queue.yml"
copy_file "./environments/docker-compose.shms-vpn.control.yml" "${TARGET_ROOT}/environments/docker-compose.shms-vpn.control.yml"

ssh "${TARGET_HOST}" "chmod +x ${TARGET_ROOT}/vpn/vpn.sh && cd ${TARGET_ROOT}/environments && docker compose --project-name environments --project-directory ${TARGET_ROOT}/environments -f docker-compose.shms-vpn.control.yml up -d --build vpn-control-api"
ssh "${TARGET_HOST}" '
for src in celery_worker nautobot; do
    if docker ps --format "{{.Names}}" | grep -qx "$src"; then
        docker cp "$src:/opt/nautobot/git/." "'"${TARGET_ROOT}"'/git/" 2>/dev/null || true
        exit 0
    fi
done
'
