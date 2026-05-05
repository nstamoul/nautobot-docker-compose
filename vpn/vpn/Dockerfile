FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Base VPN clients + troubleshooting + Vault CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    # VPN clients
    openfortivpn \
    openvpn \
    wireguard-tools \
    openconnect \
    vpnc-scripts \
    # DNS orchestration
    dnsmasq \
    # Network tools
    iproute2 iputils-ping \
    curl wget ca-certificates openssl \
    dnsutils bind9-dnsutils \
    netcat-openbsd socat \
    traceroute mtr-tiny \
    tcpdump \
    iptables nftables \
    # Container management (for auto-restart)
    docker.io \
    # Utilities
    jq procps less nano bash dumb-init \
    python3 \
    unzip \
 && update-ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Ensure a canonical path for vpnc-script used by openconnect
RUN mkdir -p /etc/vpnc \
 && if [ ! -e /etc/vpnc/vpnc-script ] && [ -f /usr/share/vpnc-scripts/vpnc-script ]; then \
      ln -s /usr/share/vpnc-scripts/vpnc-script /etc/vpnc/vpnc-script; \
    fi

# Install HashiCorp Vault CLI
ARG VAULT_VERSION=1.15.4
RUN cd /tmp \
 && wget -q "https://releases.hashicorp.com/vault/${VAULT_VERSION}/vault_${VAULT_VERSION}_linux_amd64.zip" \
 && unzip "vault_${VAULT_VERSION}_linux_amd64.zip" \
 && mv vault /usr/local/bin/vault \
 && chmod +x /usr/local/bin/vault \
 && rm -f "vault_${VAULT_VERSION}_linux_amd64.zip" \
 && vault --version

# Optional connectivity probe
RUN echo '#!/usr/bin/env bash\nset -e\nhost="${1:-1.1.1.1}"\nping -c1 -W2 "$host" >/dev/null 2>&1 || exit 1\nexit 0' \
    > /usr/local/bin/netcheck \
 && chmod +x /usr/local/bin/netcheck

# Create directories for certificates and configs
RUN mkdir -p /vpn/certs /vpn/configs /vpn/secrets

# --- runtime ---
# --- DNS orchestration & Network monitoring ---

COPY vault_fetch.sh /usr/local/bin/vault_fetch.sh
COPY dns_orchestrator.sh /usr/local/bin/dns_orchestrator.sh
COPY network_monitor.sh /usr/local/bin/network_monitor.sh
COPY container_restarter.sh /usr/local/bin/container_restarter.sh
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /usr/local/bin/vault_fetch.sh /usr/local/bin/dns_orchestrator.sh \
    /usr/local/bin/network_monitor.sh /usr/local/bin/container_restarter.sh /entrypoint.sh

ENTRYPOINT ["/usr/bin/dumb-init","--"]
CMD ["/entrypoint.sh"]

# Disable dnsmasq system startup (we control it manually)
RUN echo "manual" > /etc/init/dnsmasq.override 2>/dev/null || true
