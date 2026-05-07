# SHMS VPN HA Design

## Current `wyze` design

The `wyze` Nautobot stack uses a dedicated VPN execution path rather than routing the main Celery worker through the VPN:

- `vpn` container
  - privileged
  - owns the tunnel device and customer routes
- `celery_worker_vpn_v3`
  - listens on queue `vpn`
  - uses `network_mode: "container:${VPN_CONTAINER_NAME}"`
  - therefore shares the VPN container network namespace
- `vpn_control_api`
  - FastAPI service
  - mounted with Docker socket access
  - starts/stops the `vpn` container and the dedicated VPN worker
- `Control VPN` Nautobot job
  - runs on the default queue
  - talks to `vpn_control_api`
  - ensures the command-mapper Git repo is synced before use

This is the correct execution model. The older pattern that restarts or routes the main `celery_worker` through the VPN should not be used on SHMS.

## What SHMS already has

The SHMS tree already contains:

- queue registration for `vpn`
- `environments/docker-compose.shms-vpn.service.yml`
- `environments/docker-compose.shms-vpn.queue.yml`
- VPN scripts under `vpn/vpn/`
- the `Control VPN` job in the jobs repo

The SHMS tree does not currently contain:

- the `vpn_control_api` source tree
- a compose service definition for `vpn_control_api`
- operational wiring for the control API key and service URL

So SHMS currently has the worker and tunnel scaffolding, but not the orchestration component that makes the flow usable.

## Constraints in SHMS

Current SHMS state:

- Nautobot app is intentionally single-active on `nb-ha-01`
- `nb-ha-02` is not yet carrying live application traffic
- MinIO/shared storage is still blocked

Therefore the VPN design should be implemented in two stages:

1. node-local production implementation on `nb-ha-01`
2. symmetric standby deployment on `nb-ha-02`, activated only when the app layer is ready to fail over cleanly

## Recommended SHMS architecture

### Stage 1: active node only

Deploy on `nb-ha-01`:

- `vpn_control_api`
- `vpn`
- `celery_worker_vpn`

Behavior:

- `Control VPN` runs on the normal/default worker
- it calls the local `vpn_control_api`
- the API starts or stops only the local node's `vpn` and `celery_worker_vpn`
- all VPN-routed jobs execute only on queue `vpn`
- only `celery_worker_vpn` consumes from queue `vpn`

This keeps VPN state and worker state local to the active node and avoids any cluster ambiguity.

### Stage 2: HA-ready shape

Once the second Nautobot app node is brought online after MinIO/shared storage is available:

- deploy the exact same `vpn_control_api`, `vpn`, and `celery_worker_vpn` stack on `nb-ha-02`
- keep only the active Nautobot node's VPN stack running
- during failover:
  - stop the old node's `celery_worker_vpn`
  - stop the old node's `vpn` container
  - start the new node's `vpn_control_api`-managed stack

This is active/passive VPN control, not active/active.

## Why not active/active

A shared active/active VPN design is the wrong fit here:

- the tunnel is stateful and node-local
- the worker shares the VPN container network namespace
- customer/session state may include OTP, MFA, or headend-specific routing state
- two workers consuming queue `vpn` at the same time would create undefined routing behavior

The correct model is a single logical queue with a single active consumer.

## Networking model

The control API should remain node-local and internal only.

Do not front `vpn_control_api` with:

- Traefik
- HAProxy
- a VIP

The API has Docker socket access and is an orchestration primitive, not a user-facing service.

Recommended exposure:

- only on the internal Docker network used by the Nautobot app containers
- protected with `VPN_CONTROL_API_KEY`

The `Control VPN` job should call:

- `http://vpn_control_api:5001` when the service runs in the same compose project/network

or the equivalent SHMS service name.

## Compose direction for SHMS

SHMS should use the dedicated worker model only:

- keep `docker-compose.shms-vpn.service.yml`
- keep `docker-compose.shms-vpn.queue.yml`
- add a new compose file for `vpn_control_api`

Recommended new file:

- `environments/docker-compose.shms-vpn.control.yml`

That file should define:

- `vpn_control_api`
  - use `SHMS_VPN_CONTROL_API_IMAGE`
  - mount project root read-only
  - mount the host project path read-only
  - mount `/var/run/docker.sock`
  - set:
    - `VPN_PROJECT_ROOT=/workspace`
    - `VPN_PROJECT_ROOT_HOST=/opt/nautobot`
    - `VPN_CONTROL_API_KEY=${VPN_CONTROL_API_KEY}`
    - `VPN_WORKER_SVC=celery_worker_vpn`

## Registry image model

The production HA nodes should not build VPN images locally. Build and push
images through GitLab CI, then deploy by setting:

- `SHMS_VPN_IMAGE=glcr.eztp.space.gr/.../shms-vpn@sha256:<digest>`
- `SHMS_VPN_CONTROL_API_IMAGE=glcr.eztp.space.gr/.../shms-vpn-control-api@sha256:<digest>`

The `shms-vpn` image is multi-arch and must be built for:

- `linux/amd64` for the SHMS HA nodes
- `linux/arm64` when the same appliance image is used on Raspberry Pi class
  workers

The Cisco Secure Client binaries are licensed build inputs and must not be
committed. Store the amd64 and arm64 predeploy tarballs as protected GitLab file
variables or protected package artifacts, then copy them into
`vpn/vpn/cisco-secure-client/` inside the CI job before `docker buildx build`.

## Source carryover required from `wyze`

Bring over:

- `vpn/VPN_Control_API/app.py`
- `vpn/VPN_Control_API/Dockerfile`
- `vpn/VPN_Control_API/README.md`

Optional but useful:

- `vpn/VPN_Control_API/systemd/`
- `vpn/docs/`

The systemd unit is not needed for the containerized SHMS implementation.

## Operational rules

1. Only jobs that truly require VPN access should target queue `vpn`.
2. `Control VPN` itself stays on the default queue.
3. `vpn_control_api` must not be exposed outside the Docker-internal network.
4. The command-mapper repo sync behavior in `Control VPN` should be preserved.
5. `celery_worker_vpn` should not start automatically unless the VPN service is intended to be usable on that node.

## Implementation order

1. Carry over `vpn_control_api` source from `wyze` into SHMS.
2. Add `docker-compose.shms-vpn.control.yml`.
3. Wire `VPN_CONTROL_API_URL` and `VPN_CONTROL_API_KEY` in SHMS env/config.
4. Build and push `SHMS_VPN_IMAGE` and `SHMS_VPN_CONTROL_API_IMAGE` through CI.
5. Pre-stage both HA nodes with:
   - `deploy_shms_vpn_control_api.sh nb-ha-01 --sync --pull`
   - `deploy_shms_vpn_control_api.sh nb-ha-02 --sync --pull`
6. Activate only the current app-active node:
   - `deploy_shms_vpn_control_api.sh nb-ha-01 --activate`
7. Verify:
   - `Control VPN` status/start/stop
   - local worker creation and teardown
   - queue `vpn` consumption
   - command-mapper repo sync path
8. During failover, stop tenant VPN slots on the old node before activating the
   new node's control API and starting tenant VPN slots there.

## Immediate recommendation

Implement the VPN stack now on `nb-ha-01` only.

Do not wait for MinIO to implement the node-local VPN path.
Do wait for MinIO before attempting dual-node application failover or any active/passive automation across both Nautobot nodes.
