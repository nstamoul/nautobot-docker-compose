#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# SHMS VPN Helper Script
# ==============================================================================
# Manages tenant-scoped outbound VPN appliance + dedicated worker pairs.
#
# Expected caller-provided env:
#   CUSTOMER
#   VPN_QUEUE
#   VPN_COMPOSE_PROJECT
#   VPN_CONTAINER_NAME
#   VPN_WORKER_CONTAINER_NAME
#   VPN_WORKER_NAME
#   VPN_SLOT_SLUG
#   VPN_TENANT_NAME
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT_CONTAINER="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT_HOST="${VPN_PROJECT_ROOT_HOST:-$PROJECT_ROOT_CONTAINER}"
ENV_DIR_CONTAINER="$PROJECT_ROOT_CONTAINER/environments"
ENV_DIR_HOST="$PROJECT_ROOT_HOST/environments"

VPN_SERVICE_COMPOSE_FILE="${VPN_SERVICE_COMPOSE_FILE:-docker-compose.shms-vpn.service.yml}"
VPN_QUEUE_COMPOSE_FILE="${VPN_QUEUE_COMPOSE_FILE:-docker-compose.shms-vpn.queue.yml}"
VPN_COMPOSE_PROJECT="${VPN_COMPOSE_PROJECT:-shms-vpn}"
VPN_WORKER_SVC="${VPN_WORKER_SVC:-celery_worker_vpn}"
VPN_SERVICE_NAME="${VPN_SERVICE_NAME:-vpn}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD_MAGENTA='\033[1;35m'
NC='\033[0m'

log() { echo -e "${GREEN}[vpn]${NC} $*"; }
warn() { echo -e "${YELLOW}[vpn]${NC} $*"; }
error() { echo -e "${RED}[vpn]${NC} $*" >&2; }
die() { error "$*"; exit 1; }

print_cli_command() {
    local formatted=""
    for arg in "$@"; do
        formatted+=" $(printf '%q' "$arg")"
    done
    formatted="${formatted# }"
    echo -e "${BOLD_MAGENTA}[vpn-cli] ${formatted}${NC}"
}

source_env_file() {
    local path="$1"
    [[ -f "$path" ]] || return 0

    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        [[ -n "$line" ]] || continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" == *=* ]] || continue

        local key="${line%%=*}"
        local value="${line#*=}"

        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"

        if [[ "$value" == \"*\" && "$value" == *\" ]]; then
            value="${value:1:-1}"
        elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
            value="${value:1:-1}"
        fi

        export "$key=$value"
    done <"$path"
}

# Load SHMS env files if present. Caller-provided overrides win.
source_env_file "$ENV_DIR_CONTAINER/local.shms.env"
source_env_file "$ENV_DIR_CONTAINER/creds.shms.env"

# SHMS stores Vault settings under HASHICORP_VAULT_* for Nautobot. Reuse them
# for the VPN tooling instead of maintaining a second token/config surface.
if [[ -z "${VAULT_ADDR:-}" && -n "${HASHICORP_VAULT_URL:-}" ]]; then
    export VAULT_ADDR="${HASHICORP_VAULT_URL}"
fi
if [[ -z "${VAULT_TOKEN:-}" && -n "${HASHICORP_VAULT_TOKEN:-}" ]]; then
    export VAULT_TOKEN="${HASHICORP_VAULT_TOKEN}"
fi
if [[ -z "${VAULT_NAMESPACE:-}" && -n "${HASHICORP_VAULT_NAMESPACE:-}" ]]; then
    export VAULT_NAMESPACE="${HASHICORP_VAULT_NAMESPACE}"
fi
if [[ -z "${VAULT_CACERT:-}" && -n "${REQUESTS_CA_BUNDLE:-}" ]]; then
    export VAULT_CACERT="${REQUESTS_CA_BUNDLE}"
fi
if [[ -z "${VAULT_CACERT:-}" && -n "${SSL_CERT_FILE:-}" ]]; then
    export VAULT_CACERT="${SSL_CERT_FILE}"
fi

VPN_SERVICE_COMPOSE_ARGS=(
  --project-name "$VPN_COMPOSE_PROJECT"
  --project-directory "$ENV_DIR_HOST"
  -f "$ENV_DIR_HOST/$VPN_SERVICE_COMPOSE_FILE"
)

VPN_WORKER_COMPOSE_ARGS=(
  --project-name "$VPN_COMPOSE_PROJECT"
  --project-directory "$ENV_DIR_HOST"
  -f "$ENV_DIR_HOST/$VPN_SERVICE_COMPOSE_FILE"
  -f "$ENV_DIR_HOST/$VPN_QUEUE_COMPOSE_FILE"
)

vpn_service_compose() {
    local cmd=(docker compose "${VPN_SERVICE_COMPOSE_ARGS[@]}" "$@")
    print_cli_command "${cmd[@]}"
    "${cmd[@]}"
}

vpn_worker_compose() {
    local cmd=(docker compose "${VPN_WORKER_COMPOSE_ARGS[@]}" "$@")
    print_cli_command "${cmd[@]}"
    "${cmd[@]}"
}

cleanup_artifacts() {
    local files=(
        "$SCRIPT_DIR/certs/client.crt"
        "$SCRIPT_DIR/certs/client.key"
        "$SCRIPT_DIR/certs/ca.crt"
        "$SCRIPT_DIR/configs/client.ovpn"
    )

    for path in "${files[@]}"; do
        [[ -f "$path" ]] || continue
        rm -f "$path" || warn "Unable to remove ${path#$SCRIPT_DIR/}"
    done
}

current_customer() {
    local container_id
    container_id=$(docker compose "${VPN_SERVICE_COMPOSE_ARGS[@]}" ps -q "$VPN_SERVICE_NAME" 2>/dev/null || true)
    if [[ -n "$container_id" ]]; then
        docker inspect -f '{{range .Config.Env}}{{if eq (index (split . "=") 0) "CUSTOMER"}}{{index (split . "=") 1}}{{end}}{{end}}' "$container_id" 2>/dev/null || true
    fi
}

vpn_running() {
    local container_id
    container_id=$(docker compose "${VPN_SERVICE_COMPOSE_ARGS[@]}" ps -q "$VPN_SERVICE_NAME" 2>/dev/null || true)
    [[ -n "$container_id" ]] || return 1
    [[ "$(docker inspect -f '{{.State.Status}}' "$container_id" 2>/dev/null || true)" == "running" ]]
}

vpn_worker_running() {
    local worker_id
    worker_id=$(docker compose "${VPN_WORKER_COMPOSE_ARGS[@]}" ps -q "$VPN_WORKER_SVC" 2>/dev/null || true)
    [[ -n "$worker_id" ]]
}

start_vpn_worker() {
    vpn_worker_compose up --detach --no-deps --force-recreate "$VPN_WORKER_SVC"
    log "Dedicated VPN worker (${VPN_WORKER_SVC}) started for queue ${VPN_QUEUE:-vpn}"
}

stop_vpn_worker() {
    vpn_worker_compose rm -sf "$VPN_WORKER_SVC" || warn "Failed to remove ${VPN_WORKER_SVC}"
}

list_customers() {
    [[ -n "${VAULT_ADDR:-}" ]] || die "VAULT_ADDR is not set"
    [[ -n "${VAULT_TOKEN:-}" ]] || die "VAULT_TOKEN is not set"

    export VAULT_ADDR VAULT_TOKEN
    [[ -n "${VAULT_NAMESPACE:-}" ]] && export VAULT_NAMESPACE

    local list_path="${VAULT_LIST_PATH:-kv}"
    list_path="${list_path%/}/"
    vault kv list "${list_path}"
}

cmd="${1:-help}"
shift || true

case "$cmd" in
    start)
        customer="${1:-${CUSTOMER:-}}"
        [[ -z "$customer" ]] && die "Usage: $0 start <customer> [--vpn-client NAME] [--profile-name NAME] [--otp CODE] [--authgroup NAME] [--usergroup NAME] [--banner-response TEXT] [--extra-args 'ARGS']"
        shift || true

        vpn_client=""
        profile_name=""
        otp=""
        authgroup=""
        usergroup=""
        banner_response="yes"
        extra_args_cli=""

        while [[ $# -gt 0 ]]; do
            case "$1" in
                --vpn-client)
                    [[ -n "${2:-}" ]] || die "--vpn-client requires a value"
                    vpn_client="$2"
                    shift 2
                    ;;
                --profile-name)
                    [[ -n "${2:-}" ]] || die "--profile-name requires a value"
                    profile_name="$2"
                    shift 2
                    ;;
                --otp|--mfa)
                    [[ -n "${2:-}" ]] || die "--otp requires a value"
                    otp="$2"
                    shift 2
                    ;;
                --authgroup)
                    [[ -n "${2:-}" ]] || die "--authgroup requires a value"
                    authgroup="$2"
                    shift 2
                    ;;
                --usergroup)
                    [[ -n "${2:-}" ]] || die "--usergroup requires a value"
                    usergroup="$2"
                    shift 2
                    ;;
                --banner|--banner-response)
                    [[ -n "${2:-}" ]] || die "--banner-response requires a value"
                    banner_response="$2"
                    shift 2
                    ;;
                --extra-args)
                    [[ -n "${2:-}" ]] || die "--extra-args requires a value"
                    extra_args_cli+=" $2"
                    shift 2
                    ;;
                --)
                    shift
                    break
                    ;;
                *)
                    die "Unknown option for start: $1"
                    ;;
            esac
        done

        existing_customer=$(current_customer)
        if [[ -n "$existing_customer" ]] && vpn_running; then
            log "VPN is already connected to $existing_customer for project $VPN_COMPOSE_PROJECT"
            if vpn_worker_running; then
                log "Dedicated worker is already running."
            else
                start_vpn_worker
            fi
            exit 0
        fi

        cleanup_artifacts
        export CUSTOMER="$customer"
        [[ -n "$vpn_client" ]] && export VPN_CLIENT="$vpn_client"
        [[ -n "$profile_name" ]] && export CISCO_PROFILE_NAME="$profile_name"
        export OPENCONNECT_SECOND_PASSWORD="$otp"
        export CISCO_SECOND_PASSWORD="$otp"
        export OPENCONNECT_BANNER_RESPONSE="$banner_response"
        export CISCO_BANNER_RESPONSE="$banner_response"
        [[ -n "$authgroup" ]] && export CISCO_AUTHGROUP="$authgroup" FORTI_REALM="$authgroup"
        [[ -n "$usergroup" ]] && export CISCO_USERGROUP="$usergroup"
        [[ -n "${extra_args_cli# }" ]] && export EXTRA_ARGS="${EXTRA_ARGS:-} ${extra_args_cli# }"

        vpn_service_compose up -d --force-recreate "$VPN_SERVICE_NAME"
        log "Waiting briefly for VPN initialization..."
        sleep 3
        vpn_service_compose logs --tail=50 "$VPN_SERVICE_NAME" || true
        start_vpn_worker
        ;;

    start-worker)
        start_vpn_worker
        ;;

    stop-worker)
        stop_vpn_worker
        ;;

    stop)
        stop_vpn_worker
        vpn_service_compose down -v
        cleanup_artifacts
        ;;

    status)
        log "VPN container status:"
        vpn_service_compose ps "$VPN_SERVICE_NAME"
        customer_name=$(current_customer)
        [[ -n "$customer_name" ]] && log "Current customer: $customer_name"
        if vpn_worker_running; then
            log "Dedicated worker status:"
            vpn_worker_compose ps "$VPN_WORKER_SVC"
        else
            warn "Dedicated worker is not running"
        fi
        ;;

    logs)
        follow="${1:--f}"
        vpn_service_compose logs $follow "$VPN_SERVICE_NAME"
        ;;

    exec)
        [[ -z "${1:-}" ]] && die "Usage: $0 exec <command>"
        vpn_service_compose exec "$VPN_SERVICE_NAME" "$@"
        ;;

    list)
        list_customers
        ;;

    *)
        cat <<EOF
Usage: $0 <command>

Commands:
  start <customer> [--vpn-client NAME] [--profile-name NAME] [--otp CODE] [--authgroup NAME] [--usergroup NAME] [--banner-response TEXT] [--extra-args 'ARGS']
  start-worker
  stop
  stop-worker
  status
  logs [-f]
  exec <command>
  list
EOF
        ;;
esac
