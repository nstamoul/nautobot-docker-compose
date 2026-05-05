#!/usr/bin/env bash
set -Eeuo pipefail

log() { echo "[cisco-secure-client-host] $*"; }
die() { echo "[cisco-secure-client-host] ERROR: $*" >&2; exit 1; }

VPN_BIN="${CISCO_SECURE_CLIENT_BIN:-/opt/cisco/secureclient/bin/vpn}"
CUSTOMER=""
ACTION="${1:-help}"
shift || true

if [[ "${ACTION}" != "help" ]]; then
    CUSTOMER="${1:-${CUSTOMER:-}}"
    [[ -n "${CUSTOMER}" ]] || die "Usage: $0 <start|stop|status> <customer> [--profile-name NAME] [--usergroup GROUP] [--banner-response TEXT]"
    shift || true
fi

PROFILE_NAME="${CISCO_PROFILE_NAME:-}"
USERGROUP="${CISCO_USERGROUP:-}"
BANNER_RESPONSE="${CISCO_BANNER_RESPONSE:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile-name)
            [[ -n "${2:-}" ]] || die "--profile-name requires a value"
            PROFILE_NAME="$2"
            shift 2
            ;;
        --usergroup)
            [[ -n "${2:-}" ]] || die "--usergroup requires a value"
            USERGROUP="$2"
            shift 2
            ;;
        --banner|--banner-response)
            [[ -n "${2:-}" ]] || die "--banner-response requires a value"
            BANNER_RESPONSE="$2"
            shift 2
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
done

vault_secret_path() {
    echo "${VPN_SECRET_PATH:-kv/${CUSTOMER}/vpn}"
}

metadata_value() {
    local key="$1"
    local metadata_json="${2:-}"
    [[ -n "${metadata_json}" ]] || return 0
    jq -r --arg key "$key" '.data.custom_metadata[$key] // .custom_metadata[$key] // empty' <<< "${metadata_json}"
}

secret_value() {
    local key="$1"
    local secret_json="$2"
    jq -r --arg key "$key" '.data.data[$key] // empty' <<< "${secret_json}"
}

load_profile_metadata() {
    local metadata_json=""
    metadata_json=$(vault kv metadata get -format=json "$(vault_secret_path)" 2>/dev/null || true)
    if [[ -n "${metadata_json}" ]]; then
        [[ -z "${PROFILE_NAME}" ]] && PROFILE_NAME="$(metadata_value profile_name "${metadata_json}")"
        [[ -z "${USERGROUP}" ]] && USERGROUP="$(metadata_value usergroup "${metadata_json}")"
        [[ -z "${PROFILE_NAME}" ]] && PROFILE_NAME="$(metadata_value host "${metadata_json}")"
    fi
}

require_vault_env() {
    [[ -n "${VAULT_ADDR:-${HASHICORP_VAULT_URL:-}}" ]] || die "VAULT_ADDR is not set"
    [[ -n "${VAULT_TOKEN:-${HASHICORP_VAULT_TOKEN:-}}" ]] || die "VAULT_TOKEN is not set"
    if [[ -z "${VAULT_ADDR:-}" && -n "${HASHICORP_VAULT_URL:-}" ]]; then
        export VAULT_ADDR="${HASHICORP_VAULT_URL}"
    fi
    if [[ -z "${VAULT_TOKEN:-}" && -n "${HASHICORP_VAULT_TOKEN:-}" ]]; then
        export VAULT_TOKEN="${HASHICORP_VAULT_TOKEN}"
    fi
    [[ -n "${HASHICORP_VAULT_NAMESPACE:-}" && -z "${VAULT_NAMESPACE:-}" ]] && export VAULT_NAMESPACE="${HASHICORP_VAULT_NAMESPACE}"
    [[ -n "${REQUESTS_CA_BUNDLE:-}" && -z "${VAULT_CACERT:-}" ]] && export VAULT_CACERT="${REQUESTS_CA_BUNDLE}"
    [[ -n "${SSL_CERT_FILE:-}" && -z "${VAULT_CACERT:-}" ]] && export VAULT_CACERT="${SSL_CERT_FILE}"
}

ensure_vpn_bin() {
    [[ -x "${VPN_BIN}" ]] || die "Cisco Secure Client CLI not executable at ${VPN_BIN}"
}

case "${ACTION}" in
    start)
        require_vault_env
        ensure_vpn_bin
        load_profile_metadata
        [[ -n "${PROFILE_NAME}" ]] || die "Cisco Secure Client profile name is required"

        secret_json=$(vault kv get -format=json "$(vault_secret_path)" 2>/dev/null) || die "Failed to read Vault VPN secret"
        username="$(secret_value username "${secret_json}")"
        password="$(secret_value password "${secret_json}")"
        [[ -n "${username}" ]] || die "VPN username is missing"
        [[ -n "${password}" ]] || die "VPN password is missing"

        log "Connecting customer ${CUSTOMER} with Cisco Secure Client profile '${PROFILE_NAME}'"
        [[ -n "${USERGROUP}" ]] && log "Using configured user group '${USERGROUP}'"
        stdin_payload="${username}"$'\n'"${password}"
        if [[ -n "${BANNER_RESPONSE}" ]]; then
            stdin_payload+=$'\n'"${BANNER_RESPONSE}"
        fi

        output=$(printf '%s\n' "${stdin_payload}" | "${VPN_BIN}" -s connect "${PROFILE_NAME}" 2>&1) || {
            printf '%s\n' "${output}" >&2
            die "Cisco Secure Client connect command failed"
        }
        printf '%s\n' "${output}"
        if grep -Eiq 'state:[[:space:]]*Connected|notice:[[:space:]]*Connected' <<< "${output}"; then
            exit 0
        fi
        die "Cisco Secure Client did not report a connected state"
        ;;

    stop)
        ensure_vpn_bin
        "${VPN_BIN}" disconnect
        ;;

    status)
        ensure_vpn_bin
        "${VPN_BIN}" state
        ;;

    help|*)
        cat <<'USAGE'
Usage:
  cisco_secure_client_host.sh start <customer> [--profile-name NAME] [--usergroup GROUP] [--banner-response TEXT]
  cisco_secure_client_host.sh stop <customer>
  cisco_secure_client_host.sh status <customer>
USAGE
        ;;
esac
