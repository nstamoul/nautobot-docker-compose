#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# Unified VPN Entrypoint
# ==============================================================================
# Supports multiple VPN types with HashiCorp Vault integration
#
# VPN Types (set VPN_TYPE):
#   - forti-saml      : FortiNet with SAML authentication
#   - forti-password  : FortiNet with username/password
#   - cisco-anyconnect: Cisco/Meraki AnyConnect-family VPN
#   - openvpn         : OpenVPN with cert or password auth
#   - wireguard       : WireGuard VPN
# ==============================================================================

# --------- Helpers ----------
log() { echo "[vpn] $*"; }

die() {
  echo "[vpn] ERROR: $*" >&2
  exit 1
}

BOLD_MAGENTA='\033[1;35m'
NC='\033[0m'

print_runtime_command() {
  local -a sanitized=()
  local redact_next="false"

  for arg in "$@"; do
    if [[ "$redact_next" == "true" ]]; then
      sanitized+=("*****")
      redact_next="false"
      continue
    fi

    case "$arg" in
      -p|--password|--passwd|--cookie|--user-key|--private-key)
        sanitized+=("$arg")
        redact_next="true"
        continue
        ;;
      --password=*|--passwd=*|--cookie=*|--private-key=*|--user-key=*|--cert-password=*|--secret=*|--token=*)
        sanitized+=("${arg%%=*}=*****")
        continue
        ;;
    esac

    sanitized+=("$arg")
  done

  local formatted=""
  for arg in "${sanitized[@]}"; do
    formatted+=" $(printf '%q' "$arg")"
  done
  formatted="${formatted# }"
  echo -e "${BOLD_MAGENTA}[vpn-runtime] ${formatted}${NC}"
}

validate_ca_cert() {
  local path="$1"

  if [[ -z "${path}" ]]; then
    return 1
  fi

  if [[ ! -f "${path}" ]]; then
    log "DEBUG: CA certificate path '${path}' not found; skipping"
    return 1
  fi

  if ! openssl x509 -in "${path}" -noout >/dev/null 2>&1; then
    log "DEBUG: CA certificate at '${path}' failed validation; skipping"
    return 1
  fi

  return 0
}

normalize_server_cert() {
  local raw="$1"
  raw="${raw//$'\n'/}"
  raw="${raw//[$' \t']/}"
  local lower="${raw,,}"

  if [[ "${lower}" == pin-sha256:* ]]; then
    echo "pin-sha256:${raw#pin-sha256:}"
    return
  fi

  if [[ "${lower}" == sha256:* ]]; then
    echo "pin-sha256:${raw#sha256:}"
    return
  fi

  local hex="${raw//:/}"
  if [[ "${hex}" =~ ^[0-9A-Fa-f]{64}$ ]]; then
    local converted
    converted=$(python3 - <<'PY'
import base64
import re
import sys

hex_fp = sys.argv[1]
if not re.fullmatch(r"[0-9A-Fa-f]{64}", hex_fp):
    raise SystemExit(1)

print(base64.b64encode(bytes.fromhex(hex_fp)).decode())
PY
"${hex}")
    if [[ -n "${converted}" ]]; then
      echo "pin-sha256:${converted}"
      return
    fi
  fi

  echo "${raw}"
}

# --------- Config (env) ----------
# Customer selection (auto-constructs Vault path)
CUSTOMER="${CUSTOMER:-}"
USE_VAULT="${USE_VAULT:-false}"

unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,.shms.local,vault.shms.local,172.20.11.214}"
export no_proxy="${no_proxy:-$NO_PROXY}"

if [[ -z "${VAULT_TOKEN:-}" && -n "${HASHICORP_VAULT_TOKEN:-}" ]]; then
  export VAULT_TOKEN="${HASHICORP_VAULT_TOKEN}"
fi
if [[ -z "${VAULT_ADDR:-}" && -n "${HASHICORP_VAULT_URL:-}" ]]; then
  export VAULT_ADDR="${HASHICORP_VAULT_URL}"
fi
if [[ -z "${VAULT_CACERT:-}" && -n "${REQUESTS_CA_BUNDLE:-}" ]]; then
  export VAULT_CACERT="${REQUESTS_CA_BUNDLE}"
fi
if [[ -z "${VAULT_CACERT:-}" && -n "${SSL_CERT_FILE:-}" ]]; then
  export VAULT_CACERT="${SSL_CERT_FILE}"
fi

# Auto-construct VPN_SECRET_PATH from CUSTOMER if not provided
if [[ -n "${CUSTOMER}" && "${USE_VAULT}" == "true" ]]; then
  VPN_SECRET_PATH="${VPN_SECRET_PATH:-kv/${CUSTOMER}/vpn}"
  log "Using customer: ${CUSTOMER}"
  log "Vault path: ${VPN_SECRET_PATH}"
fi

VPN_TYPE="${VPN_TYPE:-}"
VPN_CLIENT="${VPN_CLIENT:-}"
# Unified DNS control knob across VPN implementations.
# true  -> VPN client manages resolv.conf (default behavior)
# false -> prevent VPN client from modifying resolv.conf
VPN_SET_DNS="${VPN_SET_DNS:-true}"

# FortiNet specific
FORTI_HOST="${FORTI_HOST:-}"
FORTI_PORT="${FORTI_PORT:-443}"
FORTI_USERNAME="${FORTI_USERNAME:-}"
FORTI_PASSWORD="${FORTI_PASSWORD:-}"
FORTI_REALM="${FORTI_REALM:-}"
FORTI_TRUSTED_CERT="${FORTI_TRUSTED_CERT:-}"
FORTI_COOKIE="${FORTI_COOKIE:-}"
EXTRA_ARGS="${EXTRA_ARGS:-}"
CALLBACK_PORT="${CALLBACK_PORT:-8020}"
COOKIE_FILE="/run/forti_cookie"

# Cisco AnyConnect/OpenConnect specific
CISCO_USERGROUP="${CISCO_USERGROUP:-}"
CISCO_PROFILE_NAME="${CISCO_PROFILE_NAME:-}"

# OpenVPN specific
OVPN_CONFIG="${OVPN_CONFIG:-}"
OVPN_USERNAME="${OVPN_USERNAME:-}"
OVPN_PASSWORD="${OVPN_PASSWORD:-}"

# WireGuard specific
WG_CONFIG="${WG_CONFIG:-/etc/wireguard/wg0.conf}"

# General
HEALTHCHECK_TARGET="${HEALTHCHECK_TARGET:-1.1.1.1}"
ALLOW_UNTRUSTED_CERT="${ALLOW_UNTRUSTED_CERT:-false}"

# --------- Vault Integration ----------
if [[ "${USE_VAULT}" == "true" ]]; then
  log "Fetching secrets from Vault..."
  source /usr/local/bin/vault_fetch.sh

  # Auto-detect VPN_TYPE from metadata if not explicitly set
  [[ -z "${VPN_TYPE}" && -n "${VAULT_VPN_TYPE:-}" ]] && VPN_TYPE="$VAULT_VPN_TYPE"
  [[ -z "${VPN_CLIENT}" && -n "${VAULT_VPN_CLIENT:-}" ]] && VPN_CLIENT="$VAULT_VPN_CLIENT"

  # Override local env with Vault values if present
  [[ -n "${VAULT_USERNAME:-}" ]] && FORTI_USERNAME="$VAULT_USERNAME" && OVPN_USERNAME="$VAULT_USERNAME"
  [[ -n "${VAULT_PASSWORD:-}" ]] && FORTI_PASSWORD="$VAULT_PASSWORD" && OVPN_PASSWORD="$VAULT_PASSWORD"
  [[ -n "${VAULT_HOST:-}" ]] && FORTI_HOST="$VAULT_HOST"
  [[ -n "${VAULT_PORT:-}" ]] && FORTI_PORT="$VAULT_PORT"
  [[ -n "${VAULT_REALM:-}" ]] && FORTI_REALM="$VAULT_REALM"
  [[ -n "${VAULT_TRUSTED_CERT:-}" ]] && FORTI_TRUSTED_CERT="$VAULT_TRUSTED_CERT"
  [[ -n "${VAULT_COOKIE:-}" ]] && FORTI_COOKIE="$VAULT_COOKIE"

  # Cisco AnyConnect specific overrides
  [[ -n "${CISCO_AUTHGROUP:-}" ]] && FORTI_REALM="$CISCO_AUTHGROUP"
  [[ -n "${VAULT_CISCO_USERGROUP:-}" ]] && CISCO_USERGROUP="$VAULT_CISCO_USERGROUP"
  [[ -n "${VAULT_CISCO_PROFILE_NAME:-}" ]] && CISCO_PROFILE_NAME="$VAULT_CISCO_PROFILE_NAME"
  [[ -n "${VAULT_OVPN_CONFIG:-}" ]] && OVPN_CONFIG="$VAULT_OVPN_CONFIG"
fi

# Validate VPN_TYPE is set
[[ -z "${VPN_TYPE}" ]] && die "VPN_TYPE must be set (either via env or Vault metadata)"
if [[ "${VPN_TYPE}" == "cisco-anyconnect" && -z "${VPN_CLIENT}" ]]; then
  VPN_CLIENT="openconnect"
fi

# --------- DNS Orchestration Setup ----------
start_dns_orchestration() {
  log "Starting DNS orchestration layer..."
  /usr/local/bin/dns_orchestrator.sh --monitor &
  DNS_ORCH_PID=$!
  log "DNS orchestrator started (PID: ${DNS_ORCH_PID})"
}

# --------- Network Monitor Setup ----------
start_network_monitor() {
  if [[ "${VPN_ENABLE_AUTO_RESTART:-true}" != "true" ]]; then
    log "Network monitor disabled (VPN_ENABLE_AUTO_RESTART=false)"
    return 0
  fi

  if [[ ! -S /var/run/docker.sock ]]; then
    log "WARNING: Docker socket not available, network monitor disabled"
    log "         To enable auto-restart: mount /var/run/docker.sock"
    return 0
  fi

  log "Starting network monitor for dependent container auto-restart..."
  /usr/local/bin/network_monitor.sh &
  NETWORK_MONITOR_PID=$!
  log "Network monitor started (PID: ${NETWORK_MONITOR_PID})"
}

# Start DNS orchestration before anything else
start_dns_orchestration

# Wait for dnsmasq to initialize
sleep 2

# Start network monitor (after DNS orchestration)
start_network_monitor

# --------- Restart Dependent Containers on VPN Start ----------
restart_dependent_containers_on_start() {
  if [[ "${VPN_RESTART_DEPENDENTS_ON_START:-true}" != "true" ]]; then
    log "Skipping dependent container restart on start (VPN_RESTART_DEPENDENTS_ON_START=false)"
    return 0
  fi

  if [[ ! -S /var/run/docker.sock ]]; then
    log "WARNING: Docker socket not available, cannot restart dependent containers"
    return 0
  fi

  log "Restarting dependent containers to re-attach to this VPN container..."
  # Give VPN container a moment to fully initialize
  sleep 3

  if /usr/local/bin/container_restarter.sh; then
    log "✓ Dependent containers restarted successfully"
  else
    log "⚠ Failed to restart dependent containers (they may need manual restart)"
  fi
}

# Restart dependent containers in background (don't block VPN startup)
restart_dependent_containers_on_start &

# --------- Net debug (early) ----------
log "VPN_TYPE: ${VPN_TYPE}"
[[ -n "${VPN_CLIENT}" ]] && log "VPN_CLIENT: ${VPN_CLIENT}"
log "container ip route:"
ip route || true
log "container resolv.conf (after dns-orch init):"
log "Testing local DNS:"
dig @127.0.0.1 redis +short 2>/dev/null || log "DEBUG: redis not yet resolvable (expected during startup)"
cat /etc/resolv.conf || true

enable_ip_forwarding() {
  local current
  current=$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo 0)
  if [[ "$current" != "1" ]]; then
    log "Enabling IPv4 forwarding"
    sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || echo 1 > /proc/sys/net/ipv4/ip_forward
  fi
}

setup_nat() {
  enable_ip_forwarding
  local egress_ifaces=("ppp+" "tun+" "wg0")
  for iface in "${egress_ifaces[@]}"; do
    iptables -t nat -C POSTROUTING -o "$iface" -j MASQUERADE 2>/dev/null || \
      iptables -t nat -A POSTROUTING -o "$iface" -j MASQUERADE
    iptables -C FORWARD -i "$iface" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
      iptables -A FORWARD -i "$iface" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
    iptables -C FORWARD -o "$iface" -j ACCEPT 2>/dev/null || \
      iptables -A FORWARD -o "$iface" -j ACCEPT
  done
  # Allow traffic between docker-attached interfaces
  for lan_if in eth0 eth1; do
    [[ -d "/sys/class/net/${lan_if}" ]] || continue
    iptables -C FORWARD -i "$lan_if" -j ACCEPT 2>/dev/null || \
      iptables -A FORWARD -i "$lan_if" -j ACCEPT
    iptables -C FORWARD -o "$lan_if" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
      iptables -A FORWARD -o "$lan_if" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
  done
}

# --------- Tiny cookie catcher (for SAML) ----------
start_cookie_server() {
python3 - <<'PY' &
import http.server, urllib.parse, os, sys

PORT = int(os.environ.get("CALLBACK_PORT","8020"))
COOKIE_FILE = os.environ.get("COOKIE_FILE","/run/forti_cookie")

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stdout.write("[saml] " + (format%args) + "\n")

    def _ok(self, body="ok\n"):
        self.send_response(200)
        self.send_header("Content-Type","text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        try:
            q = urllib.parse.urlparse(self.path).query
            qs = urllib.parse.parse_qs(q)
            cookie = (qs.get("cookie") or [None])[0]
            if cookie:
                with open(COOKIE_FILE,"w") as f: f.write(cookie.strip())
                self._ok("cookie saved\n")
            else:
                self._ok("send cookie via ?cookie=SVPNCOOKIE...\n")
        except Exception as e:
            self.send_error(400, str(e))

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length','0'))
            body = self.rfile.read(length).decode()
            qs = urllib.parse.parse_qs(body)
            cookie = (qs.get("cookie") or [None])[0]
            if cookie:
                with open(COOKIE_FILE,"w") as f: f.write(cookie.strip())
                self._ok("cookie saved\n")
            else:
                self.send_error(400,"missing cookie")
        except Exception as e:
            self.send_error(400, str(e))

http.server.ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
PY
COOKIE_SRV_PID=$!
log "SAML cookie server pid=${COOKIE_SRV_PID} listening on ${CALLBACK_PORT}"
}

# --------- VPN Type Implementations ----------

run_forti_saml() {
  [[ -n "${FORTI_HOST}" ]] || die "FORTI_HOST is required"
  [[ "${FORTI_PORT}" =~ ^[0-9]+$ ]] || die "FORTI_PORT must be numeric"

  setup_nat

  # Build command
  cmd=( openfortivpn "${FORTI_HOST}:${FORTI_PORT}" )

  # DNS orchestrator handles DNS management dynamically

  # Certificate validation (prioritize trusted cert if provided)
  if [[ -n "${FORTI_TRUSTED_CERT}" ]]; then
    log "Using trusted certificate: ${FORTI_TRUSTED_CERT}"
    cmd+=( --trusted-cert="${FORTI_TRUSTED_CERT}" )
  elif [[ "${ALLOW_UNTRUSTED_CERT}" == "true" ]]; then
    log "Warning: No trusted cert provided and ALLOW_UNTRUSTED_CERT=true"
    log "ERROR: openfortivpn does not support --insecure flag. You must provide a trusted certificate."
    die "Please add trusted_cert to Vault metadata or set ALLOW_UNTRUSTED_CERT=false"
  fi

  [[ -n "${FORTI_REALM}" ]] && cmd+=( --realm="${FORTI_REALM}" )
  [[ -n "${EXTRA_ARGS}" ]] && cmd+=( ${EXTRA_ARGS} )

  # SAML flow
  if [[ -n "${FORTI_COOKIE}" ]]; then
    log "using SAML cookie from environment"
    cmd+=( --cookie="${FORTI_COOKIE}" )
  elif [[ -f "${COOKIE_FILE}" && -s "${COOKIE_FILE}" ]]; then
    log "using SAML cookie from ${COOKIE_FILE}"
    cookie="$(tr -d '\r\n' < "${COOKIE_FILE}")"
    cmd+=( --cookie="${cookie}" )
  else
    start_cookie_server
    log "Authenticate here: https://${FORTI_HOST}:${FORTI_PORT}/remote/saml/start?redirect=1"
    log "Then paste SVPNCOOKIE to: http://<this-host>:${CALLBACK_PORT}/?cookie=SVPNCOOKIE..."
    log "waiting for SAML cookie..."
    for i in $(seq 1 180); do
      [[ -s "${COOKIE_FILE}" ]] && break
      sleep 1
    done
    [[ -s "${COOKIE_FILE}" ]] || die "timed out waiting for SAML cookie"
    cookie="$(tr -d '\r\n' < "${COOKIE_FILE}")"
    cmd+=( --cookie="${cookie}" )
  fi

  log "running: openfortivpn ${FORTI_HOST}:${FORTI_PORT} (SAML)"
  print_runtime_command "${cmd[@]}"
  exec "${cmd[@]}"
}

run_forti_password() {
  [[ -n "${FORTI_HOST}" ]] || die "FORTI_HOST is required"
  [[ -n "${FORTI_USERNAME}" ]] || die "FORTI_USERNAME is required"
  [[ -n "${FORTI_PASSWORD}" ]] || die "FORTI_PASSWORD is required"

  setup_nat

  cmd=( openfortivpn "${FORTI_HOST}:${FORTI_PORT}" -u "${FORTI_USERNAME}" -p "${FORTI_PASSWORD}" )

  # DNS orchestrator handles DNS management dynamically

  # Certificate validation (prioritize trusted cert if provided)
  if [[ -n "${FORTI_TRUSTED_CERT}" ]]; then
    log "Using trusted certificate: ${FORTI_TRUSTED_CERT}"
    cmd+=( --trusted-cert="${FORTI_TRUSTED_CERT}" )
  elif [[ "${ALLOW_UNTRUSTED_CERT}" == "true" ]]; then
    log "Warning: No trusted cert provided and ALLOW_UNTRUSTED_CERT=true"
    log "ERROR: openfortivpn does not support --insecure flag. You must provide a trusted certificate."
    die "Please add trusted_cert to Vault metadata or set ALLOW_UNTRUSTED_CERT=false"
  fi

  [[ -n "${FORTI_REALM}" ]] && cmd+=( --realm="${FORTI_REALM}" )

  if [[ -n "${VAULT_CLIENT_CERT:-}" && -n "${VAULT_CLIENT_KEY:-}" ]]; then
    cmd+=( --user-cert="${VAULT_CLIENT_CERT}" --user-key="${VAULT_CLIENT_KEY}" )
    log "Using client certificate/key from Vault"
  elif [[ -n "${VAULT_CLIENT_CERT:-}" || -n "${VAULT_CLIENT_KEY:-}" ]]; then
    log "Warning: client cert/key incomplete; skipping mutual TLS setup"
  fi

  if validate_ca_cert "${VAULT_CA_CERT:-}"; then
    cmd+=( --ca-file="${VAULT_CA_CERT}" )
    log "Using CA certificate from Vault"
  elif [[ -n "${VAULT_CA_CERT:-}" ]]; then
    log "DEBUG: Skipping invalid or missing CA certificate path '${VAULT_CA_CERT}'"
  fi

  [[ -n "${EXTRA_ARGS}" ]] && cmd+=( ${EXTRA_ARGS} )

  log "running: openfortivpn ${FORTI_HOST}:${FORTI_PORT} -u ${FORTI_USERNAME} -p [REDACTED]"
  print_runtime_command "${cmd[@]}"
  exec "${cmd[@]}"
}

run_openvpn() {
  [[ -n "${OVPN_CONFIG}" ]] || die "OVPN_CONFIG is required (path to .ovpn file)"
  [[ -f "${OVPN_CONFIG}" ]] || die "OVPN_CONFIG file not found: ${OVPN_CONFIG}"

  setup_nat

  cmd=( openvpn --config "${OVPN_CONFIG}" )

  # If username/password provided, create auth file
  if [[ -n "${OVPN_USERNAME}" && -n "${OVPN_PASSWORD}" ]]; then
    AUTH_FILE="/run/ovpn_auth"
    echo "${OVPN_USERNAME}" > "${AUTH_FILE}"
    echo "${OVPN_PASSWORD}" >> "${AUTH_FILE}"
    chmod 600 "${AUTH_FILE}"
    cmd+=( --auth-user-pass "${AUTH_FILE}" )
    log "running: openvpn --config ${OVPN_CONFIG} --auth-user-pass [REDACTED]"
  else
    log "running: openvpn --config ${OVPN_CONFIG}"
  fi

  print_runtime_command "${cmd[@]}"
  exec "${cmd[@]}"
}

run_cisco_anyconnect() {
  [[ -n "${FORTI_HOST}" ]] || die "VPN host is required"
  [[ -n "${FORTI_USERNAME}" ]] || die "VPN username is required"
  [[ -n "${FORTI_PASSWORD}" ]] || die "VPN password is required"

  local effective_second_password="${CISCO_SECOND_PASSWORD:-${OPENCONNECT_SECOND_PASSWORD:-${VAULT_OPENCONNECT_SECOND_PASSWORD:-}}}"
  local effective_banner_response="${CISCO_BANNER_RESPONSE:-${OPENCONNECT_BANNER_RESPONSE:-${VAULT_OPENCONNECT_BANNER_RESPONSE:-}}}"
  local effective_extra_input="${OPENCONNECT_EXTRA_INPUT:-${VAULT_OPENCONNECT_EXTRA_INPUT:-}}"

  log "DEBUG: FORTI_REALM='${FORTI_REALM:-}'"
  log "DEBUG: FORTI_TRUSTED_CERT='${FORTI_TRUSTED_CERT:-}'"
  log "DEBUG: OPENCONNECT_SECOND_PASSWORD='${effective_second_password:+SET}'"
  log "DEBUG: OPENCONNECT_BANNER_RESPONSE='${effective_banner_response:-}'"
  log "DEBUG: OPENCONNECT_EXTRA_INPUT='${effective_extra_input:+SET}'"

  setup_nat

  local -a cmd=(openconnect --protocol=anyconnect --no-proxy --user "${FORTI_USERNAME}" --passwd-on-stdin)

  # DNS orchestrator handles DNS dynamically - no need for VPN_SET_DNS logic

  if [[ -n "${FORTI_REALM}" ]]; then
    cmd+=(--authgroup "${FORTI_REALM}")
    log "DEBUG: Added --authgroup '${FORTI_REALM}'"
  fi

  if [[ -n "${CISCO_USERGROUP}" ]]; then
    cmd+=(--usergroup "${CISCO_USERGROUP}")
    log "DEBUG: Added --usergroup '${CISCO_USERGROUP}'"
  fi

  if [[ -n "${FORTI_TRUSTED_CERT}" ]]; then
    if [[ -f "${FORTI_TRUSTED_CERT}" ]]; then
      cmd+=(--cafile "${FORTI_TRUSTED_CERT}")
      log "DEBUG: Added --cafile '${FORTI_TRUSTED_CERT}'"
    else
      local fingerprint
      fingerprint=$(normalize_server_cert "${FORTI_TRUSTED_CERT}")
      cmd+=(--servercert "${fingerprint}")
      log "DEBUG: Added --servercert '${fingerprint}'"
    fi
  else
    log "DEBUG: No FORTI_TRUSTED_CERT set - connection may fail cert validation"
  fi

  if [[ -n "${VAULT_CLIENT_CERT:-}" && -n "${VAULT_CLIENT_KEY:-}" ]]; then
    cmd+=(--certificate "${VAULT_CLIENT_CERT}" --sslkey "${VAULT_CLIENT_KEY}")
    log "DEBUG: Added client certificate/key from Vault"
  elif [[ -n "${VAULT_CLIENT_CERT:-}" || -n "${VAULT_CLIENT_KEY:-}" ]]; then
    log "DEBUG: Client certificate/key incomplete; skipping mutual TLS"
  fi

  if [[ -n "${VAULT_CA_CERT:-}" && "${VAULT_CA_CERT}" != "${FORTI_TRUSTED_CERT:-}" ]]; then
    if validate_ca_cert "${VAULT_CA_CERT}"; then
      cmd+=(--cafile "${VAULT_CA_CERT}")
      log "DEBUG: Added --cafile '${VAULT_CA_CERT}' from Vault"
    else
      log "DEBUG: Skipping invalid CA certificate path '${VAULT_CA_CERT}'"
    fi
  fi

  if [[ -n "${EXTRA_ARGS}" ]]; then
    # shellcheck disable=SC2206
    read -r -a extra_args <<< "${EXTRA_ARGS}"
    cmd+=("${extra_args[@]}")
  fi

  local target="${FORTI_HOST}"
  [[ -n "${FORTI_PORT}" ]] && target="${FORTI_HOST}:${FORTI_PORT}"
  cmd+=("${target}")

  log "DEBUG: Full command array: ${cmd[*]}"
  log "running: openconnect --protocol=anyconnect --user ${FORTI_USERNAME} ${target}"
  # For banner acceptance, use --non-inter flag (banner is shown AFTER auth, not during)
  if [[ -n "${effective_banner_response}" && "${effective_banner_response}" =~ ^(yes|y|accept)$ ]]; then
    cmd+=(--non-inter)
    log "DEBUG: Added --non-inter for automatic banner acceptance"
  fi

  local stdin_payload="${FORTI_PASSWORD}"
  local stdin_debug="password(${#FORTI_PASSWORD} chars)"
  if [[ -n "${effective_second_password}" ]]; then
    stdin_payload+=$'\n'"${effective_second_password}"
    stdin_debug+=", second_password(${#effective_second_password} chars)"
  fi
  if [[ -n "${effective_extra_input}" ]]; then
    stdin_payload+=$'\n'"${effective_extra_input}"
    stdin_debug+=", extra_input(set)"
  fi
  log "DEBUG: Stdin payload: ${stdin_debug}"
  print_runtime_command "${cmd[@]}"
  printf '%s\n' "${stdin_payload}" | exec "${cmd[@]}"
}

run_wireguard() {
  [[ -f "${WG_CONFIG}" ]] || die "WireGuard config not found: ${WG_CONFIG}"

  setup_nat

  log "starting WireGuard with config: ${WG_CONFIG}"
  print_runtime_command wg-quick up "${WG_CONFIG}"
  wg-quick up "${WG_CONFIG}"

  # Keep container running
  log "WireGuard tunnel established, monitoring..."
  while true; do
    sleep 30
    wg show || die "WireGuard tunnel down"
  done
}

# --------- Main VPN Router ----------
case "${VPN_TYPE}" in
  forti-saml)
    log "Starting FortiNet VPN with SAML authentication"
    run_forti_saml
    ;;

  forti-password)
    log "Starting FortiNet VPN with password authentication"
    run_forti_password
    ;;

  openvpn)
    log "Starting OpenVPN"
    run_openvpn
    ;;

  cisco-anyconnect)
    case "${VPN_CLIENT}" in
      openconnect)
        log "Starting Cisco AnyConnect with OpenConnect"
        run_cisco_anyconnect
        ;;
      cisco-secure-client)
        die "VPN_CLIENT=cisco-secure-client is host-runtime only in this release; use vpn-control-api host mode"
        ;;
      *)
        die "Unsupported VPN_CLIENT '${VPN_CLIENT}' for VPN_TYPE=cisco-anyconnect"
        ;;
    esac
    ;;

  wireguard)
    log "Starting WireGuard"
    run_wireguard
    ;;

  *)
    die "Unknown VPN_TYPE: ${VPN_TYPE}. Supported: forti-saml, forti-password, cisco-anyconnect, openvpn, wireguard"
    ;;
esac
