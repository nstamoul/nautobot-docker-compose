#!/usr/bin/env bash
# Container Restarter - Restart containers that depend on VPN network namespace
#
# Discovers containers using label-based filtering:
#   vpn.dependent=true  - Container should be restarted on VPN reconnection
#   vpn.parent=<name>   - Optional: Only restart if specific VPN container

set -euo pipefail

LOG_PREFIX="[vpn-restarter]"

# Logging function
log() {
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') ${LOG_PREFIX} $*" >&2
}

# Get our own container ID
get_self_container_id() {
    # Try multiple methods to get container ID

    # Method 1: Read from cgroup (works in most cases)
    if [[ -f /proc/self/cgroup ]]; then
        local cgroup_id
        cgroup_id=$(grep -oP '(?<=docker/|docker-)[a-f0-9]{64}' /proc/self/cgroup | head -1)
        if [[ -n "$cgroup_id" ]]; then
            echo "$cgroup_id"
            return 0
        fi
    fi

    # Method 2: Use hostname (if --hostname not overridden)
    if [[ -n "${HOSTNAME:-}" ]]; then
        local container_id
        container_id=$(docker ps -q --filter "name=${HOSTNAME}" 2>/dev/null | head -1)
        if [[ -n "$container_id" ]]; then
            echo "$container_id"
            return 0
        fi
    fi

    # Method 3: Environment variable (can be set in docker-compose)
    if [[ -n "${VPN_CONTAINER_NAME:-}" ]]; then
        local container_id
        container_id=$(docker ps -q --filter "name=${VPN_CONTAINER_NAME}" 2>/dev/null | head -1)
        if [[ -n "$container_id" ]]; then
            echo "$container_id"
            return 0
        fi
    fi

    log "WARNING: Could not determine self container ID"
    return 1
}

# Get our container name
get_self_container_name() {
    # Method 1: Use VPN_CONTAINER_NAME if set (most reliable)
    if [[ -n "${VPN_CONTAINER_NAME:-}" ]]; then
        echo "${VPN_CONTAINER_NAME}"
        return 0
    fi

    # Method 2: Try to get from container ID
    local self_id
    if ! self_id=$(get_self_container_id); then
        echo ""
        return 1
    fi

    docker inspect "$self_id" --format '{{.Name}}' 2>/dev/null | sed 's/^\///'
}

# Find containers that depend on this VPN
find_dependent_containers() {
    local self_name
    self_name=$(get_self_container_name)

    if [[ -z "$self_name" ]]; then
        log "Cannot find dependent containers without knowing self name"
        return 1
    fi

    log "Searching for containers with labels:"
    log "  vpn.dependent=true"
    log "  vpn.parent=$self_name (optional)"

    # Find containers with vpn.dependent=true label
    local all_dependents
    all_dependents=$(docker ps --filter "label=vpn.dependent=true" --format "{{.Names}}" 2>/dev/null || echo "")

    if [[ -z "$all_dependents" ]]; then
        log "No dependent containers found with label vpn.dependent=true"
        return 0
    fi

    # Filter by parent if vpn.parent label exists
    local filtered_dependents=""
    while IFS= read -r container; do
        [[ -z "$container" ]] && continue

        # Check if container has vpn.parent label
        local parent_label
        parent_label=$(docker inspect "$container" --format '{{index .Config.Labels "vpn.parent"}}' 2>/dev/null || echo "")

        # Include if no parent label (applies to all VPN) or parent matches us
        if [[ -z "$parent_label" ]] || [[ "$parent_label" == "$self_name" ]]; then
            filtered_dependents="${filtered_dependents}${container}"$'\n'
        else
            log "Skipping $container (parent: $parent_label, expected: $self_name)"
        fi
    done <<< "$all_dependents"

    echo "$filtered_dependents"
}

# Restart a single container
restart_container() {
    local container="$1"

    # Verify container exists and is running
    if ! docker ps --filter "name=^${container}$" --format "{{.Names}}" | grep -q "^${container}$"; then
        log "✗ Container '$container' not found or not running"
        return 1
    fi

    log "Restarting container: $container"

    # Restart with timeout
    if timeout 30 docker restart "$container" >/dev/null 2>&1; then
        log "✓ Successfully restarted: $container"
        return 0
    else
        log "✗ Failed to restart: $container (timeout or error)"
        return 1
    fi
}

# Main restart logic
restart_dependent_containers() {
    log "Starting container restart process..."

    # Find dependent containers
    local dependents
    if ! dependents=$(find_dependent_containers); then
        log "ERROR: Failed to find dependent containers"
        return 1
    fi

    if [[ -z "$dependents" ]]; then
        log "No dependent containers to restart"
        return 0
    fi

    # Count containers
    local count
    count=$(echo "$dependents" | grep -c '^' || echo 0)
    log "Found $count dependent container(s) to restart"

    # Restart each container
    local success=0
    local failed=0

    while IFS= read -r container; do
        [[ -z "$container" ]] && continue

        if restart_container "$container"; then
            success=$((success + 1))
        else
            failed=$((failed + 1))
        fi

        # Small delay between restarts
        sleep 1
    done <<< "$dependents"

    # Summary
    log "Restart summary: $success succeeded, $failed failed"

    if [[ $failed -gt 0 ]]; then
        return 1
    fi

    return 0
}

# Check prerequisites
check_prerequisites() {
    # Check docker socket
    if [[ ! -S /var/run/docker.sock ]]; then
        log "ERROR: Docker socket not available at /var/run/docker.sock"
        return 1
    fi

    # Check docker CLI
    if ! command -v docker &>/dev/null; then
        log "ERROR: Docker CLI not found"
        return 1
    fi

    # Test docker access
    if ! docker ps >/dev/null 2>&1; then
        log "ERROR: Cannot access Docker API (permission denied?)"
        return 1
    fi

    return 0
}

# Main execution
main() {
    if ! check_prerequisites; then
        log "Prerequisites check failed, cannot restart containers"
        exit 1
    fi

    if restart_dependent_containers; then
        log "Container restart process completed successfully"
        exit 0
    else
        log "Container restart process completed with errors"
        exit 1
    fi
}

# Run main function
main "$@"
