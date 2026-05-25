# SHMS Image Governance

How container images are built, stored, promoted to production, and what each piece does.

---

## Image repositories

There are two GitHub repos that contain Dockerfiles for the SHMS stack:

| Repo | Status | CI runner | GHCR path |
|------|--------|-----------|-----------|
| `nstamoul/shms-nautobot` | Legacy | otepiconfig self-hosted | `ghcr.io/nstamoul/shms-<name>` |
| `nstamoul/nautobot_apps_repo` | **Active** | `ubuntu-latest` | `ghcr.io/nstamoul/nautobot_apps_repo/shms-<name>` |

The `shms-nautobot` repo was the original. All SHMS Nautobot apps, plugins, VPN code, and the Dockerfiles were later consolidated into `nautobot_apps_repo`, which is the active build source.

Neither repo is a "base image" for the other. Both Dockerfiles start from the upstream Nautobot image:

```
FROM ghcr.io/nautobot/nautobot:${NAUTOBOT_VERSION}-py${PYTHON_VER}
```

The `nautobot_apps_repo` Dockerfile differs from the old `shms-nautobot` one by only two lines (a path rename from `plugins/` to `patches/` for the UI plugin overlay).

---

## The three images

Every CI run builds all three images together (monorepo approach):

| Image | Purpose |
|-------|---------|
| `shms-nautobot` | Nautobot app + celery workers |
| `shms-vpn` | Per-tenant WireGuard/OpenVPN sidecar |
| `shms-vpn-control-api` | REST API that manages tenant VPN stacks |

They are always tagged and promoted together so all three are always in sync.

---

## Tags vs digests

**Tag** (e.g. `main-a5efb51`): a human-readable label that CI applies at build time. Tags are mutable — a tag can be re-pushed to point to a new image without any warning.

**Digest** (e.g. `sha256:e901ec7e121cc...`): a cryptographic hash of the image content. Immutable. If you pin a digest, you always get that exact image, regardless of what the tag points to later.

**Production nodes always pin digests in `.env`**, not tags. Tags are used only at promote time to look up the current digest, then the digest is what gets written to `.env`.

```
# .env on production node:
SHMS_NAUTOBOT_IMAGE=ghcr.io/nstamoul/nautobot_apps_repo/shms-nautobot@sha256:e901ec7e...
```

This means `docker compose up` on a production node will always pull the exact same image, even if someone pushes a new image under the same tag.

---

## CI build pipeline

Defined in `nautobot_apps_repo/.github/workflows/ci.yml`.

**Triggers:**
- Every `push` and `pull_request` → runs tests only
- `workflow_dispatch` with `image_tag` input → runs tests then builds and pushes all three images
- Git tag push → same as dispatch

**Tag format:** CI names images `<image-repo>:<tag>` where `<tag>` is the value you supply at dispatch (e.g. `main-a5efb51`). Convention is `<branch>-<short-sha>`.

---

## Promoting an image to production

"Promote" means: resolve the current digest for a given tag on GHCR, update `.env` on the production node, and restart the affected containers.

### With invoke (from `/opt/nautobot` on either node)

```bash
invoke promote --tag main-a5efb51
```

This:
1. Calls `gh api` to resolve the digest for each of the three images at that tag
2. Shows you the resolved digests and asks for confirmation
3. Writes `SHMS_NAUTOBOT_IMAGE`, `SHMS_VPN_IMAGE`, and `SHMS_VPN_CONTROL_API_IMAGE` to `environments/.env`
4. Runs `docker compose up -d` for the app stack (nautobot + celery)
5. Runs `docker compose up -d vpn-control-api` for the VPN control stack

To skip the confirmation prompt (e.g. in automation):

```bash
invoke promote --tag main-a5efb51 --yes
```

### With make (same location)

```bash
make promote TAG=main-a5efb51
```

### Prerequisites

- `gh` CLI must be authenticated (`gh auth status`)
- `invoke` must be installed (`sudo apt-get install -y python3-invoke`)
- `invoke.yml` must exist in `/opt/nautobot/` (gitignored, node-specific — see below)

---

## invoke.yml — per-node configuration

`invoke.yml` is gitignored because it contains node-specific values. Each node needs its own copy at `/opt/nautobot/invoke.yml`.

**nb-ha-01** (`/opt/nautobot/invoke.yml`):
```yaml
---
nautobot_docker_compose:
  project_name: "environments"
  node_name: "nb-ha-01"
  compose_dir: "environments"
  compose_files:
    - "docker-compose.shms-app.yml"
```

**nb-ha-02** (`/opt/nautobot/invoke.yml`):
```yaml
---
nautobot_docker_compose:
  project_name: "environments"
  node_name: "nb-ha-02"
  compose_dir: "environments"
  compose_files:
    - "docker-compose.shms-app.yml"
```

`node_name` is used by `vpn_control_compose()` to inject `VPN_NODE_NAME` when starting the VPN control stack.

---

## Could CI auto-deploy?

Yes, it is feasible. The pattern would be:

1. CI builds images on `workflow_dispatch` (as today)
2. An additional CI job SSHes to nb-ha-01 and nb-ha-02 and runs `invoke promote --tag <tag> --yes`

This requires:
- A deploy SSH key stored as a GitHub Actions secret
- The `gh` CLI authenticated on the nodes (already is), or the digest passed directly from CI

**Trade-offs:**

| Approach | Pro | Con |
|----------|-----|-----|
| Manual promote (current) | Explicit control, easy rollback, zero infra change needed | Requires human action after CI passes |
| Auto-deploy on dispatch tag | Fully automated, same `promote` command | Needs deploy key secret in GitHub; a bad image goes live before you review |
| Auto-deploy on git tag | Explicit promotion signal via `git tag` | Slightly more ceremony; tags are harder to clean up |

The `promote --yes` flag already supports the scripted path. To add CI auto-deploy later, only a GitHub Actions step + SSH secret is needed — no code changes required.

---

## Available invoke tasks

Run `invoke --list` from `/opt/nautobot` on either node.

| Task | Description |
|------|-------------|
| `promote --tag <tag>` | Promote a CI-built tag to production |
| `images [--tag <tag>]` | Show pinned vs running vs available digests |
| `start` | Start nautobot + celery stack |
| `stop` | Stop nautobot + celery stack |
| `restart` | Restart nautobot + celery stack |
| `recreate` | Force-recreate (picks up `.env` changes without promote) |
| `ps` | Container status for all stacks |
| `logs [--follow]` | Tail nautobot + celery_worker logs |
| `vpn-control-start` | Start vpn-control-api |
| `vpn-control-stop` | Stop vpn-control-api |
| `vpn-control-restart` | Restart vpn-control-api |
| `vpn-control-logs [--follow]` | Tail vpn-control-api logs |
| `post-upgrade` | Run `nautobot-server post_upgrade` |
| `migrate` | Run `nautobot-server migrate` |
| `nbshell` | Open `nautobot-server shell_plus` |
| `cli` | Open bash in the nautobot container |
| `createsuperuser` | Create admin superuser |

All tasks also have `make` equivalents (e.g. `make promote TAG=main-a5efb51`).
