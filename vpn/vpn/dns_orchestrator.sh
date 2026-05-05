#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# DNS Orchestrator - Dynamic DNS Management for VPN Container
# ==============================================================================
# This script:
# 1. Starts dnsmasq with Docker embedded DNS as primary upstream
# 2. Monitors /etc/resolv.conf for VPN nameserver changes
# 3. Dynamically updates dnsmasq upstream servers when VPN changes
# 4. Ensures internal services (redis, db) remain resolvable
#
# Usage: dns_orchestrator.sh [--monitor] [--dry-run]
#   --monitor  : Keep running and watch for resolv.conf changes
#   --dry-run  : Don't actually modify dnsmasq, just show what would happen
# ==============================================================================

DNSMASQ_PID_FILE="/var/run/dnsmasq.pid"
DNSMASQ_CONFIG_DIR="/etc/dnsmasq.d"
DNS_MONITOR_CONFIG="${DNSMASQ_CONFIG_DIR}/upstream-servers.conf"
RESOLV_CONF="/etc/resolv.conf"
DOCKER_DNS="127.0.0.11"
LOCALHOST_DNS="127.0.0.1"
MONITOR_MODE="${1:---monitor}"
DRY_RUN="${2:-}"

log() { echo "[dns-orch] $*"; }
die() { echo "[dns-orch] ERROR: $*" >&2; exit 1; }

# ==============================================================================
# Helper: Extract nameservers from /etc/resolv.conf
# ==============================================================================
get_current_nameservers() {
  grep "^nameserver" "$RESOLV_CONF" | awk '{print $2}' | grep -v "^${DOCKER_DNS}$" | grep -v "^${LOCALHOST_DNS}$" || true
}

# ==============================================================================
# Helper: Get current search domain
# ==============================================================================
get_current_search_domain() {
  grep "^search" "$RESOLV_CONF" | awk '{print $2}' | head -1 || echo ""
}

# ==============================================================================
# Initialize dnsmasq configuration
# ==============================================================================
init_dnsmasq() {
  log "Initializing dnsmasq..."

  mkdir -p "$DNSMASQ_CONFIG_DIR"

  cat > /etc/dnsmasq.conf << 'DNSMASQ_MAIN'
# Main dnsmasq configuration
listen-address=127.0.0.1
port=53
cache-size=1000
neg-ttl=60
conf-dir=/etc/dnsmasq.d
no-resolv
dnssec-check-unsigned=no
DNSMASQ_MAIN

  log "Created /etc/dnsmasq.conf"
  update_dnsmasq_upstreams "$(get_current_nameservers)" "$(get_current_search_domain)"
}

# ==============================================================================
# Update dnsmasq upstream servers
# ==============================================================================
update_dnsmasq_upstreams() {
  local vpn_nameservers="$1"
  local search_domain="$2"

  log "Updating upstream DNS servers..."
  log "  Docker embedded DNS: ${DOCKER_DNS}"
  log "  VPN nameservers: ${vpn_nameservers}"
  log "  Search domain: ${search_domain:-[none]}"

  cat > "$DNS_MONITOR_CONFIG" << EOF
# Dynamically generated upstream server configuration
# Updated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')
#
# Strategy:
# - VPN domain queries (${search_domain:-none}) → VPN nameservers (internal resolution)
# - Docker services (redis, db, etc.) → Docker embedded DNS (127.0.0.11)
# - External domains → Docker DNS → forwarded to public DNS

EOF

  # Route VPN domain queries to VPN nameservers (if available)
  if [[ -n "$vpn_nameservers" && -n "$search_domain" ]]; then
    log "  Routing *.${search_domain} queries to VPN nameservers"
    while IFS= read -r ns; do
      if [[ -n "$ns" ]]; then
        echo "server=/${search_domain}/${ns}" >> "$DNS_MONITOR_CONFIG"
      fi
    done <<< "$vpn_nameservers"
    echo "" >> "$DNS_MONITOR_CONFIG"
  elif [[ -n "$vpn_nameservers" ]]; then
    log "  WARNING: VPN nameservers present but no search domain - using as fallback"
    while IFS= read -r ns; do
      [[ -n "$ns" ]] && echo "server=$ns" >> "$DNS_MONITOR_CONFIG"
    done <<< "$vpn_nameservers"
    echo "" >> "$DNS_MONITOR_CONFIG"
  fi

  # Docker embedded DNS as default for everything else (internal services + external via forwarding)
  cat >> "$DNS_MONITOR_CONFIG" << EOF
# Docker embedded DNS handles:
# - Internal Docker services (redis, db, etc.)
# - External domains (forwarded to 8.8.8.8 via docker-compose dns config)
server=${DOCKER_DNS}
EOF

  # Fallback to public DNS if no VPN nameservers and no Docker DNS available
  if [[ -z "$vpn_nameservers" ]]; then
    log "WARNING: No VPN nameservers found, adding public DNS fallback"
    cat >> "$DNS_MONITOR_CONFIG" << EOF

# Public DNS fallback (used only if Docker DNS unavailable)
server=8.8.8.8
server=8.8.4.4
EOF
  fi

  if [[ -n "$search_domain" ]]; then
    echo "" >> "$DNS_MONITOR_CONFIG"
    echo "# Search domain from VPN" >> "$DNS_MONITOR_CONFIG"
    echo "domain=$search_domain" >> "$DNS_MONITOR_CONFIG"
  fi

  if [[ "$DRY_RUN" != "--dry-run" ]]; then
    log "Reloading dnsmasq configuration..."
    if [[ -f "$DNSMASQ_PID_FILE" ]]; then
      kill -HUP $(cat "$DNSMASQ_PID_FILE") 2>/dev/null || log "DEBUG: dnsmasq PID file exists but process may not be running yet"
    fi
  else
    log "[DRY-RUN] Would have updated $DNS_MONITOR_CONFIG and reloaded dnsmasq"
  fi

  cat "$DNS_MONITOR_CONFIG"
}

# ==============================================================================
# Start dnsmasq daemon
# ==============================================================================
start_dnsmasq() {
  log "Starting dnsmasq daemon..."

  if [[ "$DRY_RUN" != "--dry-run" ]]; then
    dnsmasq --pid-file="$DNSMASQ_PID_FILE"
    log "dnsmasq started (PID: $(<"$DNSMASQ_PID_FILE"))"

    sleep 1
    if ! kill -0 $(cat "$DNSMASQ_PID_FILE") 2>/dev/null; then
      die "dnsmasq failed to start"
    fi
  else
    log "[DRY-RUN] Would start dnsmasq with config from $DNSMASQ_CONFIG_DIR"
  fi
}

# ==============================================================================
# Update system resolv.conf to use local dnsmasq
# ==============================================================================
setup_local_dns_resolution() {
  log "Configuring system to use local dnsmasq..."

  if [[ "$DRY_RUN" != "--dry-run" ]]; then
    if [[ ! -f "/etc/resolv.conf.vpn-backup" ]]; then
      cp "$RESOLV_CONF" "/etc/resolv.conf.vpn-backup"
    fi

    cat > "$RESOLV_CONF" << EOF
# Generated by DNS Orchestrator
nameserver 127.0.0.1
EOF

    log "System resolv.conf updated to use local dnsmasq (127.0.0.1)"
  else
    log "[DRY-RUN] Would update /etc/resolv.conf to use 127.0.0.1"
  fi
}

# ==============================================================================
# Monitor resolv.conf for VPN changes
# ==============================================================================
monitor_resolv_conf() {
  log "Starting resolv.conf monitor (updating on VPN nameserver changes)..."

  local last_vpn_nameservers=""
  local last_search_domain=""

  while true; do
    # Check if VPN client has modified resolv.conf (doesn't point to our dnsmasq)
    if ! grep -q "^nameserver ${LOCALHOST_DNS}$" "$RESOLV_CONF"; then
      # VPN client modified resolv.conf, extract the VPN nameservers BEFORE we overwrite
      local vpn_nameservers
      local search_domain
      vpn_nameservers=$(get_current_nameservers)
      search_domain=$(get_current_search_domain)

      # Check if VPN nameservers actually changed (avoid redundant updates)
      if [[ "$vpn_nameservers" != "$last_vpn_nameservers" || "$search_domain" != "$last_search_domain" ]]; then
        log "Detected VPN nameserver change"
        log "  New nameservers: ${vpn_nameservers:-[none]}"
        log "  New search domain: ${search_domain:-[none]}"
        # Update dnsmasq with captured VPN nameservers
        update_dnsmasq_upstreams "$vpn_nameservers" "$search_domain"
        # Save the VPN nameservers we captured for future comparison
        last_vpn_nameservers="$vpn_nameservers"
        last_search_domain="$search_domain"
      fi

      # Always restore resolv.conf to point to dnsmasq after VPN modifies it
      setup_local_dns_resolution
    fi

    sleep 5
  done
}

# ==============================================================================
# Health check DNS resolution
# ==============================================================================
health_check_dns() {
  log "Performing DNS health check..."

  if timeout 2 dig @127.0.0.1 redis +short 2>/dev/null | grep -q .; then
    log "✓ Internal DNS resolution working (redis resolved)"
  else
    log "⚠ WARNING: Internal Docker DNS not yet responding (redis unresolved)"
  fi

  if timeout 2 dig @127.0.0.1 google.com +short 2>/dev/null | grep -q .; then
    log "✓ External DNS resolution working"
  else
    log "⚠ WARNING: External DNS not responding yet"
  fi
}

# ==============================================================================
# Main
# ==============================================================================
main() {
  log "DNS Orchestrator starting..."
  log "Mode: ${MONITOR_MODE#--}"
  [[ "$DRY_RUN" == "--dry-run" ]] && log "DRY-RUN mode enabled"

  init_dnsmasq
  start_dnsmasq
  setup_local_dns_resolution

  sleep 1

  health_check_dns

  log "DNS Orchestrator initialized successfully"

  if [[ "$MONITOR_MODE" == "--monitor" ]]; then
    monitor_resolv_conf
  fi
}

main "$@"
