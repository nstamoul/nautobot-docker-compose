#!/usr/bin/env bash
# Network Monitor - Detect VPN reconnection and restart dependent containers
#
# Monitors routing table changes to detect VPN interface recreation.
# Works with any VPN type (tun0, ppp0, wg0, etc.)

set -euo pipefail

# Configuration
CHECK_INTERVAL="${VPN_MONITOR_INTERVAL:-5}"
STATE_FILE="/tmp/vpn_route_state"
COOLDOWN_FILE="/tmp/vpn_last_restart"
COOLDOWN_SECONDS="${VPN_MONITOR_COOLDOWN:-60}"
LOG_PREFIX="[vpn-monitor]"

# Logging function
log() {
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') ${LOG_PREFIX} $*" >&2
}

# Get hash of current routing table (excluding default route and docker networks)
# This detects when VPN routes are added/removed/changed
get_route_hash() {
    ip route show | \
        grep -v '^default' | \
        grep -v '^172\.\(1[6-9]\|2[0-9]\|3[0-1]\)\.' | \
        grep -v '^192\.168\.' | \
        sort | \
        md5sum | \
        awk '{print $1}'
}

# Check if we're in cooldown period
in_cooldown() {
    if [[ ! -f "$COOLDOWN_FILE" ]]; then
        return 1  # Not in cooldown
    fi

    local last_restart
    last_restart=$(cat "$COOLDOWN_FILE")
    local now
    now=$(date +%s)
    local elapsed=$((now - last_restart))

    if [[ $elapsed -lt $COOLDOWN_SECONDS ]]; then
        return 0  # Still in cooldown
    fi

    return 1  # Cooldown expired
}

# Record restart time for cooldown
record_restart() {
    date +%s > "$COOLDOWN_FILE"
}

# Get list of VPN interfaces (tun, ppp, wg, etc.)
get_vpn_interfaces() {
    ip link show | \
        grep -E '(tun|ppp|wg)[0-9]+:' | \
        awk -F': ' '{print $2}' | \
        awk '{print $1}'
}

# Check if any VPN interface exists
has_vpn_interface() {
    local interfaces
    interfaces=$(get_vpn_interfaces)
    [[ -n "$interfaces" ]]
}

# Main monitoring function
monitor_network_changes() {
    log "Network monitor starting..."
    log "Check interval: ${CHECK_INTERVAL}s, Cooldown: ${COOLDOWN_SECONDS}s"

    # Wait for VPN to establish initially
    log "Waiting for VPN interface to come up..."
    local wait_count=0
    while ! has_vpn_interface; do
        sleep 2
        wait_count=$((wait_count + 1))
        if [[ $wait_count -gt 30 ]]; then
            log "WARNING: No VPN interface detected after 60s, continuing anyway"
            break
        fi
    done

    if has_vpn_interface; then
        local interfaces
        interfaces=$(get_vpn_interfaces | tr '\n' ' ')
        log "VPN interface(s) detected: $interfaces"
    fi

    # Get initial state
    local current_hash
    current_hash=$(get_route_hash)
    echo "$current_hash" > "$STATE_FILE"
    log "Initial route hash: $current_hash"
    log "Monitoring for VPN reconnection events..."

    # Main monitoring loop
    while true; do
        sleep "$CHECK_INTERVAL"

        current_hash=$(get_route_hash)
        local last_hash
        last_hash=$(cat "$STATE_FILE" 2>/dev/null || echo "")

        # Detect significant routing change
        if [[ -n "$current_hash" && -n "$last_hash" && "$current_hash" != "$last_hash" ]]; then
            log "Routing table changed detected"
            log "  Previous hash: $last_hash"
            log "  Current hash:  $current_hash"

            # Check cooldown
            if in_cooldown; then
                local elapsed=$(($(date +%s) - $(cat "$COOLDOWN_FILE")))
                log "Skipping restart (cooldown: ${elapsed}s / ${COOLDOWN_SECONDS}s)"
                echo "$current_hash" > "$STATE_FILE"
                continue
            fi

            # Verify VPN interface still exists (not just route churn)
            if has_vpn_interface; then
                local interfaces
                interfaces=$(get_vpn_interfaces | tr '\n' ' ')
                log "VPN reconnection confirmed (interfaces: $interfaces)"

                # Trigger container restart
                log "Initiating restart of dependent containers..."
                if /usr/local/bin/container_restarter.sh; then
                    log "✓ Container restart completed successfully"
                    record_restart
                else
                    log "✗ Container restart failed (see errors above)"
                fi
            else
                log "Route change detected but no VPN interface present, skipping restart"
            fi

            # Update state
            echo "$current_hash" > "$STATE_FILE"
        fi
    done
}

# Cleanup handler
cleanup() {
    log "Network monitor shutting down..."
    rm -f "$STATE_FILE" "$COOLDOWN_FILE"
    exit 0
}

trap cleanup SIGTERM SIGINT

# Check if docker socket is available
if [[ ! -S /var/run/docker.sock ]]; then
    log "ERROR: Docker socket not available at /var/run/docker.sock"
    log "       Mount it with: -v /var/run/docker.sock:/var/run/docker.sock:ro"
    log "       Auto-restart disabled"
    exit 1
fi

# Check if docker CLI is available
if ! command -v docker &>/dev/null; then
    log "ERROR: Docker CLI not found in container"
    log "       Install docker-cli package in Dockerfile"
    log "       Auto-restart disabled"
    exit 1
fi

# Start monitoring
monitor_network_changes
