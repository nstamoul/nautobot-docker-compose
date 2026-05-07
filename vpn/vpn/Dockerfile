FROM debian:bookworm-slim

ARG TARGETARCH
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
RUN set -eux; \
    TARGETARCH="${TARGETARCH:-amd64}"; \
    case "${TARGETARCH}" in \
      amd64) VAULT_ARCH="amd64"; DEB_ARCH="amd64" ;; \
      arm64) VAULT_ARCH="arm64"; DEB_ARCH="arm64" ;; \
      *) echo "Unsupported TARGETARCH '${TARGETARCH}'" >&2; exit 1 ;; \
    esac; \
    cd /tmp \
 && wget -q "https://releases.hashicorp.com/vault/${VAULT_VERSION}/vault_${VAULT_VERSION}_linux_${VAULT_ARCH}.zip" \
 && unzip "vault_${VAULT_VERSION}_linux_${VAULT_ARCH}.zip" \
 && mv vault /usr/local/bin/vault \
 && chmod +x /usr/local/bin/vault \
 && rm -f "vault_${VAULT_VERSION}_linux_${VAULT_ARCH}.zip" \
 && vault --version

# Cisco Secure Client installer bundle.
# The licensed Linux VPN installer artifacts are tracked under
# cisco-secure-client/ so the VPN image can be rebuilt deterministically.
COPY cisco-secure-client/ /tmp/cisco-secure-client/
RUN set -eux; \
    TARGETARCH="${TARGETARCH:-amd64}"; \
    case "${TARGETARCH}" in \
      amd64) VAULT_ARCH="amd64"; DEB_ARCH="amd64"; ARCHIVE_GLOB="*linux64*.tgz" ;; \
      arm64) VAULT_ARCH="arm64"; DEB_ARCH="arm64"; ARCHIVE_GLOB="*arm64*.tgz" ;; \
      *) echo "Unsupported TARGETARCH '${TARGETARCH}'" >&2; exit 1 ;; \
    esac; \
    artifact_dir="/tmp/cisco-secure-client"; \
    deb_file="$(find "$artifact_dir" -maxdepth 2 -type f -name "cisco-secure-client-vpn-cli_*_${DEB_ARCH}.deb" | head -n 1 || true)"; \
    if [ -z "$deb_file" ]; then deb_file="$(find "$artifact_dir" -maxdepth 2 -type f -name '*.deb' | head -n 1 || true)"; fi; \
    archive_file="$(find "$artifact_dir" -maxdepth 2 -type f -name "${ARCHIVE_GLOB}" | head -n 1 || true)"; \
    if [ -z "$archive_file" ]; then archive_file="$(find "$artifact_dir" -maxdepth 2 -type f \( -name '*.tar.gz' -o -name '*.tgz' \) | head -n 1 || true)"; fi; \
    if [ -n "$deb_file" ]; then \
      apt-get update; \
      apt-get install -y --no-install-recommends "$deb_file"; \
      rm -rf /var/lib/apt/lists/*; \
    elif [ -n "$archive_file" ]; then \
      mkdir -p /tmp/cisco-secure-client-extract; \
      tar -xzf "$archive_file" -C /tmp/cisco-secure-client-extract; \
      cli_deb="$(find /tmp/cisco-secure-client-extract -type f -name "cisco-secure-client-vpn-cli_*_${DEB_ARCH}.deb" | head -n 1 || true)"; \
      if [ -n "$cli_deb" ]; then \
        apt-get update; \
        apt-get install -y --no-install-recommends "$cli_deb"; \
        rm -rf /var/lib/apt/lists/*; \
      else \
        installer="$(find /tmp/cisco-secure-client-extract -type f -name 'vpn_install.sh' | head -n 1 || true)"; \
        if [ -z "$installer" ]; then echo "Cisco Secure Client archive did not contain VPN .deb packages or vpn_install.sh" >&2; exit 1; fi; \
        chmod +x "$installer"; \
        yes y | "$installer"; \
      fi; \
      rm -rf /tmp/cisco-secure-client-extract; \
    else \
      installer="$(find "$artifact_dir" -type f -name 'vpn_install.sh' | head -n 1 || true)"; \
      if [ -n "$installer" ]; then \
        chmod +x "$installer"; \
        yes y | "$installer"; \
      else \
        echo "No Cisco Secure Client installer bundled; VPN_CLIENT=cisco-secure-client will fail unless installed by a derived image."; \
      fi; \
    fi; \
    rm -rf "$artifact_dir"

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
