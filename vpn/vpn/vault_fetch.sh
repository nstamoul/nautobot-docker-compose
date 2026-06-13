#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# Vault Secret Fetcher
# ==============================================================================
# Retrieves credentials and certificates from HashiCorp Vault using token auth
#
# Environment variables:
#   VAULT_ADDR      - Vault server address (e.g., https://vault.example.com:8200)
#   VAULT_TOKEN     - Vault authentication token
#   VAULT_NAMESPACE - (Optional) Vault namespace for Enterprise
#   VPN_SECRET_PATH - Path to secrets in Vault (e.g., secret/vpn/forti)
#   USE_VAULT       - Set to "true" to enable Vault integration
# ==============================================================================

log() { echo "[vault] $*"; }
die() { echo "[vault] ERROR: $*" >&2; exit 1; }

# Check if Vault is enabled
if [[ "${USE_VAULT:-false}" != "true" ]]; then
  log "Vault integration disabled (USE_VAULT != true)"
  return 0 2>/dev/null || true
fi

# Validate required Vault configuration
[[ -n "${VAULT_ADDR:-}" ]] || die "VAULT_ADDR is required when USE_VAULT=true"
[[ -n "${VAULT_TOKEN:-}" ]] || die "VAULT_TOKEN is required when USE_VAULT=true"
[[ -n "${VPN_SECRET_PATH:-}" ]] || die "VPN_SECRET_PATH is required when USE_VAULT=true"

log "Connecting to Vault at ${VAULT_ADDR}"
export VAULT_ADDR

# Set namespace if provided (Vault Enterprise)
if [[ -n "${VAULT_NAMESPACE:-}" ]]; then
  export VAULT_NAMESPACE
  log "Using namespace: ${VAULT_NAMESPACE}"
fi

# Test Vault connectivity and authentication
if ! vault token lookup >/dev/null 2>&1; then
  die "Failed to authenticate with Vault (check VAULT_TOKEN)"
fi

log "Successfully authenticated with Vault"

# Fetch and display metadata
log "Fetching metadata from: ${VPN_SECRET_PATH}"
METADATA_JSON=$(vault kv metadata get -format=json "${VPN_SECRET_PATH}" 2>&1)
METADATA_EXIT_CODE=$?

if [[ $METADATA_EXIT_CODE -ne 0 ]]; then
  log "Warning: Could not fetch metadata (exit code: $METADATA_EXIT_CODE)"
  log "Error output: ${METADATA_JSON}"
  METADATA_JSON=""
fi

if [[ -n "${METADATA_JSON:-}" ]]; then
  # Debug: show JSON structure to understand the format
  log "DEBUG: Metadata keys: $(echo "$METADATA_JSON" | jq -c 'keys' 2>&1 || echo "parse error")"
  log "DEBUG: First 200 chars: ${METADATA_JSON:0:200}"

  # Try both possible paths: .data.custom_metadata (KV v2) or .custom_metadata (direct)
  CUSTOMER_NAME=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.customer_name // .custom_metadata.customer_name // empty')
  VPN_TYPE_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.vpn_type // .custom_metadata.vpn_type // empty')
  VPN_CLIENT_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.vpn_client // .custom_metadata.vpn_client // empty')
  HOST_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.host // .custom_metadata.host // empty')
  PORT_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.port // .custom_metadata.port // empty')
  TRUSTED_CERT_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.trusted_cert // .custom_metadata.trusted_cert // empty')
  AUTH_METHOD=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.auth_method // .custom_metadata.auth_method // empty')
  REQUIRES_CERT=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.requires_cert // .custom_metadata.requires_cert // empty')
  CISCO_PROFILE_NAME_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.profile_name // .custom_metadata.profile_name // empty')
  CISCO_USERGROUP_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.usergroup // .custom_metadata.usergroup // empty')
  CLIENT_RUNTIME_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.client_runtime // .custom_metadata.client_runtime // empty')
  WORKER_NETWORK_MODE_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.worker_network_mode // .custom_metadata.worker_network_mode // empty')

  [[ -n "$CUSTOMER_NAME" ]] && log "  Customer: ${CUSTOMER_NAME}"
  [[ -n "$VPN_TYPE_META" ]] && log "  VPN Type: ${VPN_TYPE_META}" && export VAULT_VPN_TYPE="$VPN_TYPE_META"
  [[ -n "$VPN_CLIENT_META" ]] && log "  VPN Client: ${VPN_CLIENT_META}" && export VAULT_VPN_CLIENT="$VPN_CLIENT_META"
  [[ -n "$HOST_META" ]] && log "  Host: ${HOST_META}" && export VAULT_HOST="$HOST_META"
  [[ -n "$PORT_META" ]] && log "  Port: ${PORT_META}" && export VAULT_PORT="$PORT_META"
  [[ -n "$CISCO_PROFILE_NAME_META" ]] && log "  Cisco Profile Name: ${CISCO_PROFILE_NAME_META}" && export VAULT_CISCO_PROFILE_NAME="$CISCO_PROFILE_NAME_META"
  [[ -n "$CISCO_USERGROUP_META" ]] && log "  Cisco User Group: ${CISCO_USERGROUP_META}" && export VAULT_CISCO_USERGROUP="$CISCO_USERGROUP_META"
  [[ -n "$CLIENT_RUNTIME_META" ]] && log "  Client Runtime: ${CLIENT_RUNTIME_META}" && export VAULT_CLIENT_RUNTIME="$CLIENT_RUNTIME_META"
  [[ -n "$WORKER_NETWORK_MODE_META" ]] && log "  Worker Network Mode: ${WORKER_NETWORK_MODE_META}" && export VAULT_WORKER_NETWORK_MODE="$WORKER_NETWORK_MODE_META"

  # Auto-detect certificate fingerprint if not provided in metadata
  if [[ -z "$TRUSTED_CERT_META" && -n "$HOST_META" && -n "$PORT_META" ]]; then
    log "  Trusted Cert not in metadata, auto-detecting from ${HOST_META}:${PORT_META}..."
    detected_vpn_type=${VPN_TYPE_META:-${VAULT_VPN_TYPE:-}}
    log "  Detected VPN type for fingerprint: ${detected_vpn_type:-unknown}"
    DETECTED_CERT=""
    if [[ -n "$detected_vpn_type" && "$detected_vpn_type" == forti-* ]]; then
      raw_cert=$(timeout 10 bash -c "echo | openssl s_client -connect '${HOST_META}:${PORT_META}' -servername '${HOST_META}' 2>/dev/null | openssl x509 -noout -fingerprint -sha256" || true)
      if [[ -n "$raw_cert" ]]; then
        raw_cert=${raw_cert##*=}
        raw_cert=${raw_cert// /}
        raw_cert=${raw_cert//:/}
        DETECTED_CERT=${raw_cert,,}
      fi
    else
      DETECTED_CERT=$(timeout 10 bash -c "echo | openssl s_client -connect '${HOST_META}:${PORT_META}' -servername '${HOST_META}' 2>/dev/null | openssl x509 -pubkey -noout 2>/dev/null | openssl pkey -pubin -outform der 2>/dev/null | openssl dgst -sha256 -binary 2>/dev/null | openssl base64 2>/dev/null" || true)
      if [[ -n "$DETECTED_CERT" ]]; then
        DETECTED_CERT="pin-sha256:${DETECTED_CERT}"
      fi
    fi

    if [[ -n "$DETECTED_CERT" ]]; then
      log "  Auto-detected Trusted Cert: ${DETECTED_CERT}"
      export VAULT_TRUSTED_CERT="$DETECTED_CERT"
    else
      log "  Warning: Could not auto-detect certificate fingerprint (timeout or error)"
    fi
  elif [[ -n "$TRUSTED_CERT_META" ]]; then
    log "  Trusted Cert: ${TRUSTED_CERT_META}"
    export VAULT_TRUSTED_CERT="$TRUSTED_CERT_META"
  fi

  [[ -n "$AUTH_METHOD" ]] && log "  Auth Method: ${AUTH_METHOD}"
  [[ -n "$REQUIRES_CERT" ]] && log "  Requires Certificate: ${REQUIRES_CERT}"
else
  log "Warning: No metadata found or metadata is empty"
fi

# Fetch the secret and parse JSON
log "Fetching secrets from path: ${VPN_SECRET_PATH}"
SECRET_JSON=$(vault kv get -format=json "${VPN_SECRET_PATH}" 2>/dev/null) || \
  die "Failed to read secret at path: ${VPN_SECRET_PATH}"

# Extract credentials (secrets only - host/port come from metadata)
export VAULT_USERNAME=$(echo "$SECRET_JSON" | jq -r '.data.data.username // empty')
export VAULT_PASSWORD=$(echo "$SECRET_JSON" | jq -r '.data.data.password // empty')
export VAULT_REALM=$(echo "$SECRET_JSON" | jq -r '.data.data.realm // empty')
# Only override trusted_cert from data if not already set from metadata
VAULT_TRUSTED_CERT_DATA=$(echo "$SECRET_JSON" | jq -r '.data.data.trusted_cert // empty')
[[ -z "${VAULT_TRUSTED_CERT:-}" && -n "$VAULT_TRUSTED_CERT_DATA" ]] && export VAULT_TRUSTED_CERT="$VAULT_TRUSTED_CERT_DATA"
export VAULT_COOKIE=$(echo "$SECRET_JSON" | jq -r '.data.data.cookie // empty')
export VAULT_OPENCONNECT_EXTRA_INPUT=$(echo "$SECRET_JSON" | jq -r '.data.data.openconnect_extra_input // empty')
export VAULT_OPENCONNECT_SECOND_PASSWORD=$(echo "$SECRET_JSON" | jq -r '.data.data.openconnect_second_password // empty')
export VAULT_OPENCONNECT_BANNER_RESPONSE=$(echo "$SECRET_JSON" | jq -r '.data.data.openconnect_banner_response // empty')

# Allow host/port override from secret data (backward compatibility)
VAULT_HOST_SECRET=$(echo "$SECRET_JSON" | jq -r '.data.data.host // empty')
VAULT_PORT_SECRET=$(echo "$SECRET_JSON" | jq -r '.data.data.port // empty')
[[ -n "$VAULT_HOST_SECRET" ]] && export VAULT_HOST="$VAULT_HOST_SECRET"
[[ -n "$VAULT_PORT_SECRET" ]] && export VAULT_PORT="$VAULT_PORT_SECRET"

log "Retrieved credentials from Vault"
[[ -n "$VAULT_USERNAME" ]] && log "  - username: ${VAULT_USERNAME}"
[[ -n "$VAULT_REALM" ]] && log "  - realm: ${VAULT_REALM}"
[[ -n "${VAULT_TRUSTED_CERT:-}" ]] && log "  - trusted_cert: present"
[[ -n "$VAULT_COOKIE" ]] && log "  - cookie: present"

# --- Handle certificates ---
# Check for client certificate (base64-encoded PEM)
CLIENT_CERT=$(echo "$SECRET_JSON" | jq -r '.data.data.client_cert // empty')
if [[ -n "$CLIENT_CERT" ]]; then
  log "Extracting client certificate..."
  echo "$CLIENT_CERT" | base64 -d > /vpn/certs/client.crt
  chmod 600 /vpn/certs/client.crt
  export VAULT_CLIENT_CERT="/vpn/certs/client.crt"
  log "  - client_cert: /vpn/certs/client.crt"
fi

# Check for client key (base64-encoded PEM)
CLIENT_KEY=$(echo "$SECRET_JSON" | jq -r '.data.data.client_key // empty')
if [[ -n "$CLIENT_KEY" ]]; then
  log "Extracting client key..."
  echo "$CLIENT_KEY" | base64 -d > /vpn/certs/client.key
  chmod 600 /vpn/certs/client.key
  export VAULT_CLIENT_KEY="/vpn/certs/client.key"
  log "  - client_key: /vpn/certs/client.key"
fi

# Check for CA certificate (base64-encoded PEM)
CA_CERT=$(echo "$SECRET_JSON" | jq -r '.data.data.ca_cert // empty')
if [[ -n "$CA_CERT" ]]; then
  log "Extracting CA certificate..."
  echo "$CA_CERT" | base64 -d > /vpn/certs/ca.crt
  chmod 644 /vpn/certs/ca.crt
  export VAULT_CA_CERT="/vpn/certs/ca.crt"
  log "  - ca_cert: /vpn/certs/ca.crt"
fi

# Check for OpenVPN config file (base64-encoded)
OVPN_CONFIG=$(echo "$SECRET_JSON" | jq -r '.data.data.ovpn_config // empty')
if [[ -n "$OVPN_CONFIG" ]]; then
  log "Extracting OpenVPN config..."
  echo "$OVPN_CONFIG" | base64 -d > /vpn/configs/client.ovpn
  chmod 600 /vpn/configs/client.ovpn
  export VAULT_OVPN_CONFIG="/vpn/configs/client.ovpn"
  log "  - ovpn_config: /vpn/configs/client.ovpn"
fi

# Export a flag indicating Vault secrets were loaded
export VAULT_SECRETS_LOADED="true"

log "Vault secrets successfully retrieved and exported"
log "Exported environment variables:"
log "  VAULT_USERNAME, VAULT_PASSWORD, VAULT_REALM, VAULT_TRUSTED_CERT,"
log "  VAULT_COOKIE, VAULT_CLIENT_CERT, VAULT_CLIENT_KEY, VAULT_CA_CERT,"
log "  VAULT_OVPN_CONFIG, VAULT_SECRETS_LOADED, VAULT_OPENCONNECT_EXTRA_INPUT"
log "  VAULT_OPENCONNECT_SECOND_PASSWORD, VAULT_OPENCONNECT_BANNER_RESPONSE"
log "  VAULT_VPN_CLIENT, VAULT_CISCO_PROFILE_NAME, VAULT_CISCO_USERGROUP,"
log "  VAULT_CLIENT_RUNTIME, VAULT_WORKER_NETWORK_MODE"

# Return to entrypoint (do not exit since this script is sourced)
return 0 2>/dev/null || true
