# SHMS VPN Multi-Tenant Control Plane

## Purpose

This document defines the production target for SHMS VPN execution beyond the
current single-tunnel `vpn` queue model.

The goal is to support:

- one outbound SHMS-managed VPN appliance per tenant when needed
- one outbound VPN worker per active tenant VPN tunnel
- stable tenant-derived Celery queues
- remote VPN-capable workers that can be reassigned between tenant queues
- Nautobot-side visibility and control over queues, workers, and assignments

This design is intended to be concrete enough for either an engineer or an LLM
to implement without re-deriving the architecture.

## Core principles

1. Queue identity is tenant-derived and stable.
2. Worker identity is machine-derived and dynamic.
3. Outbound SHMS VPN workers are one-to-one with tenant queues.
4. Outbound workers should start only after the tenant VPN appliance connects.
5. Remote workers should not invent queues; they should be assigned to existing
   tenant queues.
6. Nautobot controls queue metadata and job-routing policy.
7. Worker runtime controls actual queue consumption.

## Operational dependency: Vault availability

The tenant VPN appliance path depends on Vault for tunnel credentials. In SHMS
that means the control plane must assume:

- Vault may need manual unseal after a full reboot.
- Vault should be checked after HA failover events, including failover toward
  `nb-ha-02`.
- If Vault is sealed, tenant VPN appliances will fail before tunnel bring-up and
  dedicated tenant workers will not start correctly.

This requires key escrow for the unseal shares. The unseal procedure is an
explicit operational recovery step and should be documented alongside failover
runbooks.

## Queue model

### Naming

Tenant queues must use deterministic, human-readable queue names:

- `vpn-<tenant_name_slug>`

Examples:

- `vpn-acme`
- `vpn-space-gr`
- `vpn-customer-a`

The slugification rules should be:

- lowercase
- replace any non-alphanumeric characters with `-`
- collapse repeated `-`
- trim leading/trailing `-`
- do not use Nautobot's uniqueness suffix behavior

If the normalized tenant name becomes empty, the reconciler should fall back to
`tenant-<uuid-prefix>` and log the reason explicitly.

### Special queues

Optional:

- `vpn-generic`

This queue is useful for generic VPN-enabled workflows not yet tied to a tenant.

### Ownership

Each tenant queue should be represented in Nautobot as a `JobQueue` row with:

- `name = vpn-<tenant_name_slug>`
- `queue_type = celery`
- `tenant = <tenant>`

`vpn-generic` should have:

- `name = vpn-generic`
- `queue_type = celery`
- `tenant = NULL`

## Execution model

### Outbound SHMS-managed VPN workers

These are the workers that SHMS itself creates by controlling a tenant-specific
VPN appliance container.

Model:

- one tenant VPN appliance container
- one tenant VPN worker container
- one fixed tenant queue

Relationship:

- `Tenant -> queue -> outbound worker` is one-to-one while the tunnel is active

Example:

- tenant: `Acme`
- queue: `vpn-acme`
- worker: `vpn-worker-nb-ha-01-acme`
- appliance: `vpn-appliance-nb-ha-01-acme`

Important rule:

- the queue exists before the worker
- the worker is spawned only after the VPN appliance successfully connects
- the worker consumes only its tenant queue

This is intentionally different from the current coarse `vpn` queue design.

### Remote VPN-capable workers

These are external executors such as:

- a technician laptop running Docker
- a Raspberry Pi at a site
- a small host on customer premises

Model:

- worker identity comes from the machine hostname
- queue identity remains tenant-derived
- queue assignment changes over time

Example:

- worker hostname: `tech-laptop-01`
- today assigned to: `vpn-acme`
- tomorrow assigned to: `vpn-contoso`

The worker identity stays constant. The queue assignment changes.

## Responsibility split

### Nautobot server-side responsibility

Nautobot is responsible for:

- creating and storing `JobQueue` records
- associating tenant queues with tenants
- storing `JobQueueAssignment` rows for VPN-capable jobs
- deciding which queue a job run is allowed to target
- presenting control-plane state in the UI

### Worker-side responsibility

The worker runtime is responsible for:

- deciding which queues are actually consumed
- subscribing to the configured queues via Celery `-Q ...`
- exposing health and identity to the control plane

This means:

- Redis/DB/Nautobot reachability is necessary
- but it is not enough to steer a worker correctly
- the worker must still be started or reconfigured with the right queue list

## Control-plane components

### 1. Queue reconciliation job

Purpose:

- create/update tenant queues in Nautobot
- ensure VPN-capable jobs are assigned to tenant queues
- optionally ensure `vpn-generic`
- optionally disable or delete obsolete tenant VPN queues

This job can run:

- on demand
- periodically

This is the first implementation step because it is low-risk and gives SHMS
stable queue metadata before the dynamic worker/orchestration layer exists.

### 2. VPN manager app

The long-term control plane should be a Nautobot app, not just a collection of
jobs.

Suggested models:

- `VPNTenantQueue`
  - tenant
  - queue_name
  - enabled
  - desired_state
- `VPNWorker`
  - hostname
  - worker_type (`outbound`, `remote`)
  - node_name
  - status
  - last_heartbeat
  - current_queues
- `VPNAppliance`
  - tenant
  - node_name
  - status
  - last_connected
  - metadata
- `VPNAssignment`
  - worker
  - tenant_queue
  - assigned_by
  - assigned_at
  - desired_state

### 3. Controller API

The controller service should own:

- tenant appliance lifecycle
- outbound worker lifecycle
- queue subscription reconciliation for remote workers
- health/status reporting

Suggested responsibilities:

- start tenant VPN appliance
- stop tenant VPN appliance
- spawn outbound worker after successful connection
- stop outbound worker on disconnect
- assign remote worker to tenant queue(s)
- restart/reconfigure remote worker with the new `-Q ...` list

## Job-routing model

### Current state

Today, several VPN-capable jobs still declare:

- `task_queues = ["default", "vpn"]`

and some job forms expose:

- `vpn_task_queue`

This is not sufficient for multi-tenant routing.

### Target state

VPN-bound jobs should route by tenant queue.

Recommended behavior:

1. user selects tenant
2. job derives queue `vpn-<tenant_name_slug>`
3. job validates that:
   - the queue exists
   - the queue is assigned to the job
   - at least one healthy worker is consuming it when execution requires it
4. job enqueues the VPN-bound stages to that tenant queue

Optional advanced override:

- allow explicit queue selection only for expert/operational jobs
- keep `vpn-generic` as an explicit fallback

### `Control VPN` special case

`Control VPN` itself should stay on the default queue.

Why:

- it is the orchestration entrypoint
- it should not depend on the tenant VPN worker already existing

Its role becomes:

- resolve tenant
- call the controller
- wait for appliance connect
- verify worker start on tenant queue

## Remote worker registration and assignment

### Registration

Each remote worker should periodically register:

- hostname
- software version
- reachable queues
- current queue subscriptions
- health/heartbeat

### Assignment

The control plane should assign:

- one or more tenant queues to a worker

The worker itself should not create queues or self-assign tenant identity.

### Reconfiguration

When assignment changes, the controller should:

- update desired assignment
- restart or reconfigure the worker with the correct `-Q ...`

Examples:

- `celery -A nautobot.celery worker -Q vpn-acme`
- `celery -A nautobot.celery worker -Q vpn-contoso`
- `celery -A nautobot.celery worker -Q vpn-acme,vpn-generic`

## SHMS HA model

### Near-term

Because Nautobot app traffic is still single-active on `nb-ha-01`, the initial
multi-tenant VPN control plane should be active on `nb-ha-01` only.

### Future

After MinIO/shared storage and app failover are ready:

- mirror the controller stack on `nb-ha-02`
- keep the control plane active/passive
- do not run the same tenant VPN appliance active on both nodes simultaneously

This is not an active/active VPN design.

## Implementation phases

### Phase 1: queue control plane

Deliverables:

- tenant queue naming function
- local Nautobot reconciliation job
- `JobQueue` and `JobQueueAssignment` population
- design doc for the rest of the system

Issues:

- `NBSHMS-31`

### Phase 2: outbound multi-tenant controller

Deliverables:

- extend control API to manage multiple tenant appliances/workers
- spawn worker only after appliance connect
- one tenant queue per outbound worker

Issues:

- `NBSHMS-32`

### Phase 3: remote worker registration and assignment

Deliverables:

- worker heartbeat/registration API
- machine-identified worker records
- dynamic queue assignment and restart flow

Issues:

- `NBSHMS-33`

### Phase 4: VPN-bound job routing update

Deliverables:

- update VPN-bound jobs to derive tenant queues
- keep `Control VPN` on `default`
- standardize queue-selection behavior

Issues:

- `NBSHMS-34`

### Phase 5: HA promotion/failover preparation

Deliverables:

- active/passive promotion procedure for control plane
- standby node readiness on `nb-ha-02`

Issues:

- `NBSHMS-35`

## Immediate implementation recommendation

Implement Phase 1 now:

- add the design doc
- add a SHMS local job to reconcile tenant VPN queues and assignments
- use the real Nautobot `JobQueue` / `JobQueueAssignment` models
- do not change the live job execution path yet

This is the lowest-risk way to turn the architecture into concrete SHMS code
without breaking the existing single-queue VPN behavior.
