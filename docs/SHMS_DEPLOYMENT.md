# SHMS Nautobot Deployment

This overlay keeps the upstream `nautobot-docker-compose` layout but adapts it to the SHMS target environment:

- Nautobot `3.1.0`
- single-active app node on `nb-ha-01` first
- external Patroni/PostgreSQL and Redis via VIPs on `172.20.11.215`
- HTTP-only initially
- MinIO deferred, so media stays local on node 1 for now
- proxy-aware Docker build/runtime
- `/etc/hosts` workaround mirrored inside containers via `extra_hosts`
- VPN worker support preserved as a dedicated queue
- runtime diffsync and onboarding patches loaded explicitly from `patches_runtime/`

Files added for SHMS:

- `environments/docker-compose.shms-app.yml`
- `environments/docker-compose.shms-vpn.service.yml`
- `environments/docker-compose.shms-vpn.queue.yml`
- `environments/local.shms.example.env`
- `environments/creds.shms.example.env`
- `patches/` and `patches_runtime/`
- `deploy_shms_upstream_node1.sh`

Operational notes:

- Containers do not inherit the host `/etc/hosts`, so `extra_hosts` is required for `*.shms.local`.
- The app tier is intentionally single-active until MinIO is reachable, to avoid local media divergence.
- The runtime patch loader is best-effort; missing patch modules do not abort startup.
- Vault must be unsealed after a full reboot and should be expected to require an
  unseal check after a failover event, including failover toward `nb-ha-02`.
- This is an operational dependency for SHMS VPN startup, Git-backed Nautobot job
  repository access, and Vault-backed secrets resolution.
- The Vault unseal keys require proper key escrow. Treat unseal as a documented
  recovery procedure, not an implicit boot-time side effect.
