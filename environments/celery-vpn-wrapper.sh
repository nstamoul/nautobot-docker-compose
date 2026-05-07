#!/bin/bash
set -e

echo "[vpn-routing] Setting up VPN routing for celery_worker..."

# Get current default gateway and network
DEFAULT_ROUTE=$(ip route show default | head -n1)
DEFAULT_IFACE=$(echo "$DEFAULT_ROUTE" | awk '{for (i=1;i<=NF;i++){if($i=="dev"){print $(i+1); exit}}}')
DEFAULT_GW=$(echo "$DEFAULT_ROUTE" | awk '{for (i=1;i<=NF;i++){if($i=="via"){print $(i+1); exit}}}')
NAUTOBOT_ROUTE=$(ip -o route | awk -v def_iface="$DEFAULT_IFACE" '$1 != "default" {
    iface="";
    for (i=1; i<=NF; i++) {
        if ($i == "dev") {
            iface = $(i+1);
            break;
        }
    }
    if (iface != "" && iface != def_iface) {
        print;
        exit;
    }
}')
if [ -z "$NAUTOBOT_ROUTE" ]; then
  NAUTOBOT_ROUTE=$(ip -o route | awk '$1 != "default" {print; exit}')
fi
NAUTOBOT_NET=$(echo "$NAUTOBOT_ROUTE" | awk '{print $1}')
NAUTOBOT_IFACE=$(echo "$NAUTOBOT_ROUTE" | awk '{for (i=1;i<=NF;i++){if($i=="dev"){print $(i+1); exit}}}')
NAUTOBOT_GW=$(echo "$NAUTOBOT_ROUTE" | awk '{for (i=1;i<=NF;i++){if($i=="via"){print $(i+1); exit}}}')

# Wait for VPN container to be resolvable
VPN_SERVICE_NAME=${VPN_SERVICE_NAME:-vpn}
echo "[vpn-routing] Waiting for VPN container ($VPN_SERVICE_NAME) to be available..."
for i in {1..30}; do
  if VPN_GW=$(getent hosts "$VPN_SERVICE_NAME" | awk '{print $1}'); then
    echo "[vpn-routing] VPN container found at: $VPN_GW"
    break
  fi
  echo "[vpn-routing] Waiting for $VPN_SERVICE_NAME... ($i/30)"
  sleep 2
done

if [ -z "$VPN_GW" ]; then
  echo "[vpn-routing] ERROR: Could not resolve $VPN_SERVICE_NAME container"
  echo "[vpn-routing] Continuing without VPN routing..."
  exec "$@"
fi

echo "[vpn-routing] Current routing table:"
ip route

echo "[vpn-routing] Configuring routes..."
echo "[vpn-routing]   Nautobot network: $NAUTOBOT_NET dev $NAUTOBOT_IFACE${NAUTOBOT_GW:+ via $NAUTOBOT_GW}"
echo "[vpn-routing]   Default route: via VPN ($VPN_GW)"

# Delete current default route
ip route del default || true

# Add specific route for Nautobot network if needed
if [ -n "$NAUTOBOT_NET" ] && [ -n "$NAUTOBOT_IFACE" ]; then
  if [ -n "$NAUTOBOT_GW" ]; then
    ip route add "$NAUTOBOT_NET" via "$NAUTOBOT_GW" dev "$NAUTOBOT_IFACE" 2>/dev/null || true
  else
    ip route add "$NAUTOBOT_NET" dev "$NAUTOBOT_IFACE" 2>/dev/null || true
  fi
else
  echo "[vpn-routing] ⚠ Warning: Could not determine Nautobot network route"
fi

add_passthrough_route() {
  local target="$1"

  if [ -z "$target" ]; then
    return
  fi

  local gateway="$DEFAULT_GW"
  if [ -z "$gateway" ]; then
    gateway="$NAUTOBOT_GW"
  fi

  if [ -n "$gateway" ]; then
    ip route add "$target" via "$gateway" 2>/dev/null || true
  else
    ip route add "$target" 2>/dev/null || true
  fi
}

trim_whitespace() {
  local value="$1"
  value="${value#${value%%[![:space:]]*}}"  # leading
  value="${value%${value##*[![:space:]]}}"  # trailing
  echo "$value"
}

PASSTHROUGH_RAW="${VPN_PASSTHROUGH_DOMAINS:-}"
if [ -n "$PASSTHROUGH_RAW" ]; then
  IFS=',' read -ra PASSTHROUGH_DOMAINS <<< "$PASSTHROUGH_RAW"
  echo "[vpn-routing] Adding passthrough routes for configured domains/IPs..."
  for entry in "${PASSTHROUGH_DOMAINS[@]}"; do
    entry="$(trim_whitespace "$entry")"
    [ -n "$entry" ] || continue

    # Support literal CIDRs/IPs alongside domain names
    if [[ "$entry" == */* ]]; then
      echo "[vpn-routing]   Adding CIDR route: $entry"
      add_passthrough_route "$entry"
      continue
    fi

    if [[ "$entry" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "[vpn-routing]   Adding host route: $entry"
      add_passthrough_route "$entry/32"
      continue
    fi

    resolved_ips=$(getent hosts "$entry" | awk '{print $1}' | sort -u)
    if [ -z "$resolved_ips" ]; then
      echo "[vpn-routing]   ⚠ Warning: Could not resolve $entry"
      continue
    fi

    for ip in $resolved_ips; do
      if [[ "$ip" == *:* ]]; then
        echo "[vpn-routing]   ⚠ Skipping IPv6 address for $entry ($ip)"
        continue
      fi
      echo "[vpn-routing]   Adding host route for $entry → $ip"
      add_passthrough_route "$ip/32"
    done
  done
fi

# Add default route via VPN container
ip route add default via $VPN_GW

echo "[vpn-routing] New routing table:"
ip route

echo "[vpn-routing] Testing VPN connectivity..."
if ping -c 1 -W 2 $VPN_GW > /dev/null 2>&1; then
  echo "[vpn-routing] ✓ VPN container is reachable"
else
  echo "[vpn-routing] ⚠ Warning: Cannot ping VPN container"
fi

echo "[vpn-routing] Starting application..."
exec "$@"
