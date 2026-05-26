# SHMS Build, Image, and Promotion Governance

This document is the operational source of truth for SHMS/Nautobot source
repositories, CI-built images, production image pins, and promotion procedures.

State last verified: 2026-05-26.

---

## Executive Summary

SHMS production images are built by GitHub Actions on the `otepiconfig`
self-hosted runner and published to GHCR. Production promotion is explicit and
operator-driven from this compose repository; CI does not currently SSH into
production or change production image pins.

The old `nautobot_apps_repo` repository is no longer a production source. It is
archived on GitHub and moved locally to:

```text
/opt/_tools/_automation/__nautobot_master_directory__/repos/legacy/nautobot_apps_repo
```

The active production image authorities are:

| Runtime component | Source repository | GHCR package | Production promotion |
| --- | --- | --- | --- |
| Nautobot web, central celery, beat | `nstamoul/shms-nautobot` | `ghcr.io/nstamoul/shms-nautobot` | `make promote COMPONENTS=nautobot` |
| Per-tenant VPN appliance | `nstamoul/shms-vpn` | `ghcr.io/nstamoul/shms-vpn` | `make promote COMPONENTS=vpn` |
| VPN control API | `nstamoul/shms-vpn-control-api` | `ghcr.io/nstamoul/shms-vpn-control-api` | `make promote COMPONENTS=vpn-control` |
| Remote worker runtime | `nstamoul/nautobot_worker` | `ghcr.io/nstamoul/nautobot_worker` | piconfig/Vault worker image contract, not this compose repo |
| piconfig backend | `nstamoul/piconfigurator_v2` | `ghcr.io/nstamoul/piconfigurator_v2/backend` | piconfig HA `.env` and compose rollout |

---

## Repository Map

### Production Image Repositories

| Repository | Branch | Builds | CI workflow | Runner | Platforms | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `shms-nautobot` | `main` | Nautobot web, central celery worker, celery beat | `.github/workflows/ci.yml` | `self-hosted`, `otepiconfig` | Default `linux/amd64` | Canonical core+apps Nautobot image |
| `shms-vpn` | `main` | VPN appliance container | `.github/workflows/publish-image.yml` | `self-hosted`, `otepiconfig` | `linux/amd64` only | Used by tenant VPN compose stacks |
| `shms-vpn-control-api` | `main` | VPN control API container | `.github/workflows/publish-image.yml` | `self-hosted`, `otepiconfig` | `linux/amd64` only | Manages tenant VPN stacks |
| `nautobot_worker` | `main` | Remote worker image and worker base image | `.github/workflows/publish-image.yml` | `self-hosted`, `otepiconfig` | Default `linux/arm64`, configurable | Only image intended for RPi/ARM use |
| `piconfigurator_v2` | `main` | piconfig backend image | `.github/workflows/build-backend.yml` | self-hosted runner labels from workflow | `linux/amd64` | Deployed through piconfig HA compose |

### Code/Content Repositories That Do Not Build Production Images

| Repository | Purpose | Delivery mechanism |
| --- | --- | --- |
| `nautobot_jobs_repo` | Operational Nautobot jobs and workflows | Nautobot GitRepository sync and remote-worker fallback bake |
| `nautobot_command_mappers_repo` | Onboarding command mapper content | Nautobot jobs/worker runtime content |
| `rpiconfig` | RPi lifecycle scripts, system templates, defaults, bootstrap logic | RPi bootstrap pulls configured refs |
| Project repos such as `POC`, `4ype-ftd` | Per-project RPi config and Docker module manifests | RPi bootstrap/piconfig project mapping |
| `nautobot-docker-compose-upstream` | Production compose, promotion tasks, runbooks | Operator-run deployment tooling |

### Legacy/Archived Repositories

| Repository | GitHub state | Local folder | Status |
| --- | --- | --- | --- |
| `nautobot_apps_repo` | Archived | `repos/legacy/nautobot_apps_repo` | Migration reference only. Do not build or promote from it. |

---

## What Lives in `shms-nautobot`

`shms-nautobot` is intentionally the core+apps image repository. It contains the
Nautobot image build plus SHMS application code that must be installed in the
runtime image, not loaded through Nautobot Git sync.

It currently carries:

| Path | Purpose |
| --- | --- |
| `config/nautobot_config.py` | Nautobot settings, plugin registration, runtime integration |
| `plugins/nautobot-app-nbcot` | Cisco order tracking / NBCOT app |
| `plugins/nautobot-app-vpn-manager` | VPN manager and remote worker steering UI |
| `plugins/nautobot-app-nautobot-connectivity-matrix` | Connectivity matrix / stack planning app |
| `plugins/nautobot-app-nautobot_software_lifecycle` | DLM/software lifecycle app integration |
| `plugins/shms-secret-resolver` | Centralized SHMS secret resolver helper |
| `plugins/nautobot_ui_plugin` | SHMS UI customizations |
| `patches_runtime/` | Runtime monkey patches required by current production |
| `jobs/` | Small image-bundled support jobs, not the main operational jobs repo |

The practical rule is:

- App/plugin/runtime patch code belongs in `shms-nautobot`.
- Operational job content that Nautobot users edit/sync belongs in
  `nautobot_jobs_repo`.
- Remote collection runtime belongs in `nautobot_worker`.
- VPN appliance/control code does not belong in `shms-nautobot`.

---

## CI Behavior

### Common Behavior

All production image repositories use GitHub Actions. CI is the only supported
build path for production images.

Typical behavior:

- `push`: run tests/validation.
- `pull_request`: run tests/validation.
- `workflow_dispatch`: run tests and publish an image tag to GHCR.
- tag push: publish where the workflow supports tag builds.

CI publishes tags. Production uses digests. The promotion script resolves a
tag to a digest and writes the digest into production env files.

### What CI Does Not Do Today

CI does not currently:

- edit `/opt/nautobot/environments/.env` on production nodes,
- SSH to `nb-ha-01` or `nb-ha-02`,
- restart production containers,
- promote piconfig or remote worker images into live use.

Promotion remains a deliberate operator action.

---

## Current Production Pins

As of the last verification, both HA nodes pin these images in both
`/opt/nautobot/environments/.env` and
`/opt/nautobot/environments/local.shms.env`:

```text
SHMS_NAUTOBOT_IMAGE=ghcr.io/nstamoul/shms-nautobot@sha256:5d347f3a06810ca4f7060479390eeed6a3e47333d7690fd978bd9ba327ecdcd9
SHMS_VPN_CONTROL_API_IMAGE=ghcr.io/nstamoul/shms-vpn-control-api@sha256:6bf80859ba3e60c441dc3fc90214b71ba9e40a80da92fd131319a02bc2202beb
SHMS_VPN_IMAGE=ghcr.io/nstamoul/shms-vpn@sha256:e2889e0e1d211a1e2651fdc9ba4fab8089f263df9e21b42c960e2cb814060327
```

Running containers verified at that point:

| Node | Running app containers |
| --- | --- |
| `nb-ha-01` | `nautobot`, `celery_worker`, `celery_beat`, `vpn-control-api` |
| `nb-ha-02` | `nautobot`, `celery_worker`, `vpn-control-api` |

`celery_beat` intentionally runs only on `nb-ha-01`.

---

## Build Procedures

### Build and Publish `shms-nautobot`

From any machine with `gh` access:

```bash
gh workflow run ci.yml \
  --repo nstamoul/shms-nautobot \
  -f image_tag=main-<short-sha> \
  -f platforms=linux/amd64 \
  -f build_nautobot=true
```

The workflow publishes:

```text
ghcr.io/nstamoul/shms-nautobot:main-<short-sha>
```

### Build and Publish `shms-vpn`

```bash
gh workflow run publish-image.yml \
  --repo nstamoul/shms-vpn \
  -f image_tag=main-<short-sha>
```

The workflow publishes:

```text
ghcr.io/nstamoul/shms-vpn:main-<short-sha>
```

This image is `linux/amd64` only.

### Build and Publish `shms-vpn-control-api`

```bash
gh workflow run publish-image.yml \
  --repo nstamoul/shms-vpn-control-api \
  -f image_tag=main-<short-sha>
```

The workflow publishes:

```text
ghcr.io/nstamoul/shms-vpn-control-api:main-<short-sha>
```

This image is `linux/amd64` only.

### Build and Publish `nautobot_worker`

```bash
gh workflow run publish-image.yml \
  --repo nstamoul/nautobot_worker \
  -f image_tag=main-<short-sha> \
  -f platforms=linux/arm64 \
  -f jobs_ref=main \
  -f command_mappers_ref=main
```

Use a comma-separated `platforms` value only when a multi-platform worker image
is needed, for example:

```bash
-f platforms=linux/arm64,linux/amd64
```

The worker workflow also builds/reuses a dependency base image:

```text
ghcr.io/nstamoul/nautobot_worker-base:deps-<dependency-manifest-sha>
```

The runtime worker image is:

```text
ghcr.io/nstamoul/nautobot_worker:main-<short-sha>
```

Remote worker image selection is not promoted by this compose repository. It is
controlled by piconfig/Vault worker bootstrap configuration, for example the
`WorkerBootstrapImage`/worker image contract used by RPi, macOS, and Windows
worker bootstrap scripts.

### Build and Publish `piconfigurator_v2` Backend

The piconfig backend image workflow is:

```bash
gh workflow run build-backend.yml \
  --repo nstamoul/piconfigurator_v2
```

The image package is:

```text
ghcr.io/nstamoul/piconfigurator_v2/backend
```

piconfig rollout is controlled by the piconfig HA compose environment, not by
the Nautobot compose promotion task. The safe operational pattern is to update
`piconfig02` first, verify, then update `piconfig01`.

---

## Promotion Procedures

All Nautobot HA-side promotion is run from this repository:

```text
/opt/_tools/_automation/__nautobot_master_directory__/repos/active/nautobot-docker-compose-upstream
```

The relevant files are:

| File | Purpose |
| --- | --- |
| `Makefile` | Operator-friendly wrapper commands |
| `tasks.py` | Promotion, image digest resolution, compose control |
| `invoke.yml` | Local operator config; includes production node list |

The promotion flow:

1. Resolve a GHCR tag to an immutable digest using local `gh api`.
2. SSH to each configured HA node.
3. Update both `.env` and `local.shms.env`.
4. Pull the pinned image on each node.
5. Restart the affected containers.
6. Wait for health where applicable.

The HA nodes do not need GitHub CLI credentials for the normal promotion path.
They only need registry pull access and SSH access from the operator machine.

### Promote Nautobot App/Celery/Beat

```bash
cd /opt/_tools/_automation/__nautobot_master_directory__/repos/active/nautobot-docker-compose-upstream
PYENV_VERSION=3.12.11 make promote TAG=main-<short-sha> COMPONENTS=nautobot
```

Effect:

- updates `SHMS_NAUTOBOT_IMAGE`,
- pulls the image on both HA nodes,
- restarts currently-running app services,
- keeps `celery_beat` on `nb-ha-01` only,
- health-checks `nautobot`.

### Promote VPN Control API

```bash
cd /opt/_tools/_automation/__nautobot_master_directory__/repos/active/nautobot-docker-compose-upstream
PYENV_VERSION=3.12.11 make promote TAG=main-<short-sha> COMPONENTS=vpn-control
```

Effect:

- updates `SHMS_VPN_CONTROL_API_IMAGE`,
- pulls the image on both HA nodes,
- restarts `vpn-control-api`,
- health-checks `vpn-control-api`.

### Promote VPN Appliance Image

```bash
cd /opt/_tools/_automation/__nautobot_master_directory__/repos/active/nautobot-docker-compose-upstream
PYENV_VERSION=3.12.11 make promote TAG=main-<short-sha> COMPONENTS=vpn
```

Effect:

- updates `SHMS_VPN_IMAGE`,
- does not restart existing tenant VPN containers.

This is intentional. Existing VPN containers are customer-impacting and should
be restarted explicitly through the VPN manager/control plane when required.
Newly created or recreated VPN tenant stacks will use the new pinned image.

### Promote Multiple Components

`COMPONENTS=all` only works cleanly when the same image tag exists in all three
HA-side packages. If component repositories were built at different SHAs, run
three separate promotions with their own tags:

```bash
PYENV_VERSION=3.12.11 make promote TAG=main-<nautobot-sha> COMPONENTS=nautobot
PYENV_VERSION=3.12.11 make promote TAG=main-<vpn-api-sha> COMPONENTS=vpn-control
PYENV_VERSION=3.12.11 make promote TAG=main-<vpn-sha> COMPONENTS=vpn
```

### Check Pinned and Running Images

```bash
cd /opt/_tools/_automation/__nautobot_master_directory__/repos/active/nautobot-docker-compose-upstream
PYENV_VERSION=3.12.11 make images
```

To compare against a candidate GHCR tag:

```bash
PYENV_VERSION=3.12.11 make images TAG=main-<short-sha>
```

### Single-Node Fallback

```bash
PYENV_VERSION=3.12.11 make promote-local TAG=main-<short-sha> COMPONENTS=nautobot
```

This runs on the current node and requires `gh` authentication there. It is a
fallback, not the preferred production path.

---

## Rollback Procedures

Because production env files pin digests, rollback is simply another promotion
to a previous known-good tag or manual re-pin to a previous digest.

Preferred rollback:

```bash
PYENV_VERSION=3.12.11 make promote TAG=<previous-known-good-tag> COMPONENTS=nautobot
```

If the previous tag is gone but the digest is known, edit both production env
files on both HA nodes:

```text
/opt/nautobot/environments/.env
/opt/nautobot/environments/local.shms.env
```

Then recreate the affected compose services.

Database migrations are not rolled back by image rollback. For any release that
introduces migrations, take a database backup before promotion and confirm the
migration rollback path separately.

---

## Operational Guardrails

- Do not build production images locally except as an emergency diagnostic.
- Do not promote images from `nautobot_apps_repo`; it is archived legacy.
- Do not put app/plugin code back into `nautobot_jobs_repo`.
- Do not build VPN appliance or VPN control API for ARM; those are HA-node
  amd64 components.
- Do not assume CI has deployed production; verify production env pins and
  running container digests.
- Do not use mutable tags in production env files; production uses digests.
- Do not restart tenant VPN containers as a side effect of image pin changes.

---

## Quick Verification Commands

Check GitHub Actions:

```bash
gh run list --repo nstamoul/shms-nautobot --limit 5
gh run list --repo nstamoul/shms-vpn --limit 5
gh run list --repo nstamoul/shms-vpn-control-api --limit 5
gh run list --repo nstamoul/nautobot_worker --limit 5
```

Check GHCR digest for a tag:

```bash
docker buildx imagetools inspect ghcr.io/nstamoul/shms-nautobot:main-<short-sha>
```

Check production pins and running images:

```bash
for node in nb-ha-01 nb-ha-02; do
  echo "===== ${node} ====="
  ssh "${node}" '
    grep -hE "^(SHMS_NAUTOBOT_IMAGE|SHMS_VPN_IMAGE|SHMS_VPN_CONTROL_API_IMAGE)=" \
      /opt/nautobot/environments/.env \
      /opt/nautobot/environments/local.shms.env | sort -u
    docker ps --format "{{.Names}} {{.Image}} {{.Status}}" |
      egrep "^(nautobot|celery_worker|celery_beat|vpn-control-api|shms-vpn-)" || true
  '
done
```

Check public and internal Nautobot login paths:

```bash
curl -k -sS -o /dev/null -w "%{http_code}\n" https://sot.space.gr/login/
curl -k -sS -o /dev/null -w "%{http_code}\n" https://sot3.shms.local/login/
```
