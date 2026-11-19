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

Locator overlay:
  On a node that has environments/docker-compose.shms-vpn.control.locator.yml and runs in
  VPN_CONTROL_AUTH_MODE=api-key, --pull and --activate always add that overlay. It publishes
  127.0.0.1:5011 (the slot locator the access broker calls) and mounts the peer key directory.
  Recreating vpn-control-api without it takes the locator down for every broker session.
  After --activate the script fails unless 127.0.0.1 is published for 5001/tcp.
  NO_LOCATOR_NODES="nb-ha-02" skips the overlay for the listed nodes (mtls mode only).
  LOCATOR_WAIT_SECONDS (default 60) bounds the wait for the port after --activate.

This script never builds images on HA nodes. Build and push images via GitHub Actions.
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

CONTROL_COMPOSE_FILE="docker-compose.shms-vpn.control.yml"
LOCATOR_COMPOSE_FILE="docker-compose.shms-vpn.control.locator.yml"
LOCATOR_WAIT_SECONDS="${LOCATOR_WAIT_SECONDS:-60}"
USE_LOCATOR=""
CONTROL_FILES="-f ${CONTROL_COMPOSE_FILE}"

# Decide once per run whether the locator overlay belongs to this node. The answer comes from the
# node itself; an SSH failure aborts instead of silently dropping the overlay.
resolve_control_files() {
    [[ -z "${USE_LOCATOR}" ]] || return 0
    local env_dir="${TARGET_ROOT}/environments" answer
    case " ${NO_LOCATOR_NODES:-} " in
        *" ${TARGET_HOST} "*)
            USE_LOCATOR="no"
            echo "Locator overlay skipped on ${TARGET_HOST}: listed in NO_LOCATOR_NODES."
            return 0
            ;;
    esac
    answer="$(ssh "${TARGET_HOST}" "if [ ! -f ${env_dir}/${LOCATOR_COMPOSE_FILE} ]; then echo absent; elif grep -Eq '^VPN_CONTROL_AUTH_MODE=.?api-key.?\$' ${env_dir}/.env 2>/dev/null; then echo overlay; else echo not-api-key; fi")" \
        || { echo "ERROR: could not check ${TARGET_HOST} for ${LOCATOR_COMPOSE_FILE}; nothing was changed." >&2; exit 1; }
    case "${answer}" in
        overlay)
            USE_LOCATOR="yes"
            CONTROL_FILES="-f ${CONTROL_COMPOSE_FILE} -f ${LOCATOR_COMPOSE_FILE}"
            echo "Locator overlay included on ${TARGET_HOST} (${LOCATOR_COMPOSE_FILE})."
            ;;
        absent)
            USE_LOCATOR="no"
            echo "Locator overlay not present on ${TARGET_HOST}; using ${CONTROL_COMPOSE_FILE} only."
            ;;
        not-api-key)
            USE_LOCATOR="no"
            echo "Locator overlay present on ${TARGET_HOST} but VPN_CONTROL_AUTH_MODE is not api-key in .env; not used."
            ;;
        *)
            echo "ERROR: unexpected answer from ${TARGET_HOST} while checking the locator overlay: '${answer}'" >&2
            exit 1
            ;;
    esac
}

locator_port() {
    ssh "${TARGET_HOST}" "docker port vpn-control-api 5001/tcp 2>/dev/null || true"
}

# A node whose running API publishes the locator must never be recreated without the overlay.
refuse_dropping_locator() {
    [[ "${USE_LOCATOR}" == "no" ]] || return 0
    case "$(locator_port)" in
        *127.0.0.1:*)
            echo "ERROR: vpn-control-api on ${TARGET_HOST} publishes the slot locator on 127.0.0.1, but this run would recreate it without ${LOCATOR_COMPOSE_FILE}. Refusing; nothing was changed." >&2
            exit 1
            ;;
    esac
}

verify_locator_published() {
    [[ "${USE_LOCATOR}" == "yes" ]] || return 0
    local deadline=$((SECONDS + LOCATOR_WAIT_SECONDS)) port=""
    while :; do
        port="$(locator_port)"
        case "${port}" in
            *127.0.0.1:*)
                echo "Locator published on ${TARGET_HOST}: ${port}"
                return 0
                ;;
        esac
        (( SECONDS >= deadline )) && break
        sleep 3
    done
    echo "ERROR: vpn-control-api on ${TARGET_HOST} does not publish 127.0.0.1 for 5001/tcp after --activate (got: '${port:-nothing}'). The access broker's slot locator is DOWN on this node. Recreate with: docker compose -p environments ${CONTROL_FILES} up -d vpn-control-api" >&2
    exit 1
}

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
    resolve_control_files
    ssh "${TARGET_HOST}" "cd ${TARGET_ROOT}/environments && ${compose_cmd[*]} ${CONTROL_FILES} pull vpn-control-api"
    ssh "${TARGET_HOST}" "cd ${TARGET_ROOT}/environments && ${compose_cmd[*]} -f docker-compose.shms-vpn.service.yml pull vpn"
fi

if [[ "${DO_ACTIVATE}" == "true" ]]; then
    resolve_control_files
    refuse_dropping_locator
    ssh "${TARGET_HOST}" "cd ${TARGET_ROOT}/environments && ${compose_cmd[*]} ${CONTROL_FILES} up -d vpn-control-api"
    verify_locator_published
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
