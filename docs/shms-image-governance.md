# SHMS Image Governance

How container images are built, stored, promoted to production, and what each piece does.

---

## Image repositories

The SHMS stack is now built from component-specific GitHub repositories. All
GitHub Actions builds run on the `otepiconfig` self-hosted runner label set.

| Repo                               | Status      | CI runner               | GHCR path                               |
| ---------------------------------- | ----------- | ----------------------- | --------------------------------------- |
| `nstamoul/shms-nautobot`           | **Active**  | otepiconfig self-hosted | `ghcr.io/nstamoul/shms-nautobot`        |
| `nstamoul/shms-vpn`                | **Active**  | otepiconfig self-hosted | `ghcr.io/nstamoul/shms-vpn`             |
| `nstamoul/shms-vpn-control-api`    | **Active**  | otepiconfig self-hosted | `ghcr.io/nstamoul/shms-vpn-control-api` |
| `nstamoul/nautobot_worker`         | **Active**  | otepiconfig self-hosted | `ghcr.io/nstamoul/nautobot_worker`      |
| `nstamoul/nautobot_apps_repo`      | Legacy      | none for production     | Do not promote from this package        |

`shms-nautobot` is the canonical Nautobot runtime image source. The old
`nautobot_apps_repo` tree is retained only as migration reference.

Neither repo is a "base image" for the other. Both Dockerfiles start from the upstream Nautobot image:

```
FROM ghcr.io/nautobot/nautobot:${NAUTOBOT_VERSION}-py${PYTHON_VER}
```

The VPN appliance and VPN control API are separate deployables and do not build
from the Nautobot image repository.

---

## Runtime images

Production consumes three HA-side images:

| Image                    | Purpose                                 |
| ------------------------ | --------------------------------------- |
| `shms-nautobot`        | Nautobot app + celery workers           |
| `shms-vpn`             | Per-tenant VPN appliance sidecar        |
| `shms-vpn-control-api` | REST API that manages tenant VPN stacks |

The remote worker image is separate and is the only image that is expected to
support ARM devices:

| Image              | Purpose                                             |
| ------------------ | --------------------------------------------------- |
| `nautobot_worker`  | Remote worker runtime for RPi, macOS, Windows, etc. |

VPN appliance and VPN control API images are amd64-only. Do not build those for
RPi or macOS remote workers.

---

## Tags vs digests

**Tag** (e.g. `main-a5efb51`): a human-readable label that CI applies at build time. Tags are mutable — a tag can be re-pushed to point to a new image without any warning.

**Digest** (e.g. `sha256:e901ec7e121cc...`): a cryptographic hash of the image content. Immutable. If you pin a digest, you always get that exact image, regardless of what the tag points to later.

**Production nodes always pin digests in `.env`**, not tags. Tags are used only at promote time to look up the current digest, then the digest is what gets written to `.env`.

```
# .env on production node:
SHMS_NAUTOBOT_IMAGE=ghcr.io/nstamoul/shms-nautobot@sha256:e901ec7e...
```

This means `docker compose up` on a production node will always pull the exact same image, even if someone pushes a new image under the same tag.

---

## CI build pipeline

Defined in each component repository under `.github/workflows/`.

**Triggers:**

- Every `push` and `pull_request` -> runs tests only
- `workflow_dispatch` with `image_tag` input -> runs tests then builds and
  pushes that repository's image
- Git tag push -> builds and pushes that repository's image where the workflow
  supports tag builds

**Tag format:** CI names images `<image-repo>:<tag>` where `<tag>` is the value you supply at dispatch (e.g. `main-a5efb51`). Convention is `<branch>-<short-sha>`.

---

## Promoting an image to production

"Promote" means: resolve the current digest for a given tag on GHCR, update the
image pins on the production nodes, pull the pinned images, and restart the
affected containers.

### Recommended: promote from the workstation

```bash
make promote TAG=main-a5efb51
```

This:

1. Calls local `gh api` to resolve selected GHCR image digests.
2. Shows the resolved digests and asks for confirmation.
3. SSHes to each node listed in `invoke.yml`.
4. Writes the selected image pins to both `environments/.env` and
   `environments/local.shms.env`.
5. Pulls the selected images on the nodes.
6. Restarts and health-checks only the affected stacks.

The servers do not need `gh` credentials for this path. They only need normal
SSH access from the operator machine and Docker registry pull access.

Examples:

```bash
make promote TAG=main-a5efb51
make promote TAG=main-a5efb51 COMPONENTS=nautobot
make promote TAG=main-a5efb51 COMPONENTS=vpn-control
make promote TAG=main-a5efb51 COMPONENTS=vpn
```

### Local single-node fallback

```bash
make promote-local TAG=main-a5efb51
```

This runs `invoke promote` on the current node. It requires `gh` auth on that
node and should not be the normal production path.

### Prerequisites

- `gh` CLI must be authenticated on the operator workstation (`gh auth status`)
- `invoke` must be installed (`sudo apt-get install -y python3-invoke`)
- `invoke.yml` must exist in the compose repo checkout with the HA node list

---

## invoke.yml configuration

`invoke.yml` is gitignored because it contains node/operator-specific values.
For workstation-driven promotion it must include the production node list:

```yaml
---
nautobot_docker_compose:
  project_name: "environments"
  node_name: "nb-ha-01"
  compose_dir: "environments"
  compose_files:
    - "docker-compose.shms-app.yml"
  nodes:
    - nb-ha-01
    - nb-ha-02
```

`node_name` is used by the local single-node fallback to inject
`VPN_NODE_NAME` when starting the VPN control stack.

---

## Could CI auto-deploy?

Yes, it is feasible. The pattern would be:

1. CI builds images on `workflow_dispatch` (as today)
2. An additional CI job resolves the built image digests
3. The job SSHes to nb-ha-01 and nb-ha-02 and writes those digest pins

This requires:

- A deploy SSH key stored as a GitHub Actions secret
- Docker registry pull access on the nodes
- Passing digests from CI to the node update step; do not require `gh` on the
  servers

**Trade-offs:**

| Approach                    | Pro                                                       | Con                                                                        |
| --------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------- |
| Manual promote (current)    | Explicit control, easy rollback, zero infra change needed | Requires human action after CI passes                                      |
| Auto-deploy on dispatch tag | Fully automated after the build                           | Needs deploy key secret in GitHub; a bad image goes live before you review |
| Auto-deploy on git tag      | Explicit promotion signal via `git tag`                 | Slightly more ceremony; tags are harder to clean up                        |

The current recommendation is manual workstation promotion with `make promote`.
CI auto-deploy should be added only if you want GitHub Actions to become the
deployment authority as well as the build authority.

---

## Available invoke tasks

Run `invoke --list` from the compose repo checkout.

| Task                                             | Description                                                         |
| ------------------------------------------------ | ------------------------------------------------------------------- |
| `promote --tag <tag> [--components ...]`       | Promote a CI-built tag on the current node                          |
| `promote-nodes --tag <tag> [--components ...]` | Promote a CI-built tag to all configured nodes from the workstation |
| `images [--tag <tag>]`                         | Show pinned vs running vs available digests                         |
| `start`                                        | Start nautobot + celery stack                                       |
| `stop`                                         | Stop nautobot + celery stack                                        |
| `restart`                                      | Restart nautobot + celery stack                                     |
| `recreate`                                     | Force-recreate (picks up `.env` changes without promote)          |
| `ps`                                           | Container status for all stacks                                     |
| `logs [--follow]`                              | Tail nautobot + celery_worker logs                                  |
| `vpn-control-start`                            | Start vpn-control-api                                               |
| `vpn-control-stop`                             | Stop vpn-control-api                                                |
| `vpn-control-restart`                          | Restart vpn-control-api                                             |
| `vpn-control-logs [--follow]`                  | Tail vpn-control-api logs                                           |
| `post-upgrade`                                 | Run `nautobot-server post_upgrade`                                |
| `migrate`                                      | Run `nautobot-server migrate`                                     |
| `nbshell`                                      | Open `nautobot-server shell_plus`                                 |
| `cli`                                          | Open bash in the nautobot container                                 |
| `createsuperuser`                              | Create admin superuser                                              |

All tasks also have `make` equivalents (e.g. `make promote TAG=main-a5efb51`).
