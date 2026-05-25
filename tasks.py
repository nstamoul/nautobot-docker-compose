"""SHMS Nautobot Stack - Invoke Tasks."""

import os
import subprocess
from pathlib import Path

from invoke import Collection, task as invoke_task

PROJECT_ROOT = Path(__file__).parent
COMPOSE_DIR = PROJECT_ROOT / "environments"

GHCR_ORG = "ghcr.io/nstamoul/nautobot_apps_repo"
IMAGE_NAUTOBOT = f"{GHCR_ORG}/shms-nautobot"
IMAGE_VPN = f"{GHCR_ORG}/shms-vpn"
IMAGE_VPN_CONTROL_API = f"{GHCR_ORG}/shms-vpn-control-api"
IMAGE_COMPONENTS = {
    "nautobot": ("SHMS_NAUTOBOT_IMAGE", IMAGE_NAUTOBOT, "shms-nautobot"),
    "vpn": ("SHMS_VPN_IMAGE", IMAGE_VPN, "shms-vpn"),
    "vpn-control": ("SHMS_VPN_CONTROL_API_IMAGE", IMAGE_VPN_CONTROL_API, "shms-vpn-control-api"),
}
COMPONENT_ALIASES = {
    "all": "all",
    "app": "nautobot",
    "apps": "nautobot",
    "nautobot": "nautobot",
    "vpn": "vpn",
    "vpn-api": "vpn-control",
    "vpn-control": "vpn-control",
    "vpn-control-api": "vpn-control",
}

ENV_FILE = COMPOSE_DIR / ".env"
REMOTE_ENV_FILES = (".env", "local.shms.env")

namespace = Collection("nautobot_docker_compose")
namespace.configure(
    {
        "nautobot_docker_compose": {
            "project_name": "environments",
            "node_name": "nb-ha-01",
            "compose_dir": str(COMPOSE_DIR),
            "compose_files": ["docker-compose.shms-app.yml"],
        }
    }
)


def task(function=None, *args, **kwargs):  # pylint: disable=keyword-arg-before-vararg
    """Task decorator that also registers the task in the namespace."""

    def task_wrapper(function=None):
        if args or kwargs:
            task_func = invoke_task(*args, **kwargs)(function)
        else:
            task_func = invoke_task(function)
        namespace.add_task(task_func)
        return task_func

    if function:
        return task_wrapper(function)
    return task_wrapper


def _base_compose_cmd(context):
    cfg = context.nautobot_docker_compose
    cmd = (
        f"docker compose"
        f" --project-name {cfg.project_name}"
        f' --project-directory "{cfg.compose_dir}"'
    )
    for f in cfg.compose_files:
        cmd += f' -f "{cfg.compose_dir}/{f}"'
    return cmd


def docker_compose(context, command, **kwargs):
    """Run a docker compose command against the app stack."""
    full_cmd = f"{_base_compose_cmd(context)} {command}"
    print(f'Running: docker compose {command}')
    return context.run(full_cmd, **kwargs)


def vpn_control_compose(context, command, **kwargs):
    """Run a docker compose command against the vpn-control-api stack."""
    cfg = context.nautobot_docker_compose
    node_name = cfg.node_name
    full_cmd = (
        f"docker compose"
        f" --project-name {cfg.project_name}"
        f' --project-directory "{cfg.compose_dir}"'
        f' -f "{cfg.compose_dir}/docker-compose.shms-vpn.control.yml"'
        f" {command}"
    )
    print(f'Running: docker compose (vpn-control) {command}')
    env = {**os.environ, "VPN_NODE_NAME": node_name}
    return context.run(full_cmd, env=env, **kwargs)


def run_command(context, command, **kwargs):
    """Run a management command inside the nautobot container."""
    results = docker_compose(context, "ps --services --filter status=running", hide="out")
    if "nautobot" in results.stdout:
        docker_compose(context, f"exec nautobot {command}", pty=True)
    else:
        docker_compose(context, f"run --rm nautobot {command}", pty=True)


def _read_env_file():
    """Parse the .env file into a dict."""
    env = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def _write_env_file(env: dict):
    """Write a dict back to the .env file preserving key order."""
    _write_env_path(ENV_FILE, env)


def _write_env_path(env_path: Path, env: dict):
    """Write a dict back to an env file preserving existing key order."""
    lines = []
    existing = env_path.read_text().splitlines() if env_path.exists() else []
    written = set()
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            lines.append(line)
            continue
        k = stripped.split("=", 1)[0].strip()
        if k in env:
            lines.append(f"{k}={env[k]}")
            written.add(k)
        else:
            lines.append(line)
    for k, v in env.items():
        if k not in written:
            lines.append(f"{k}={v}")
    env_path.write_text("\n".join(lines) + "\n")


def _write_local_image_updates(updates: dict):
    """Update selected image pins in all local production env files."""
    for env_name in REMOTE_ENV_FILES:
        env_path = COMPOSE_DIR / env_name
        if not env_path.exists():
            print(f"{env_path} missing; skipped")
            continue
        env = {}
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, value = stripped.split("=", 1)
                env[key.strip()] = value.strip()
        env.update(updates)
        _write_env_path(env_path, env)
        print(f"Updated {env_path}")


def _gh_digest(package: str, tag: str) -> str:
    """Resolve a GHCR digest for the given package and tag via gh api."""
    pkg_encoded = package.replace("/", "%2F")
    result = subprocess.run(
        ["gh", "api", f"/users/nstamoul/packages/container/{pkg_encoded}/versions",
         "--jq", f'.[] | select(.metadata.container.tags[] == "{tag}") | .name'],
        capture_output=True, text=True, check=True,
    )
    digest = result.stdout.strip()
    if not digest:
        raise ValueError(f"No digest found for {package}:{tag}")
    return digest


def _pkg_name(full_image: str) -> str:
    """Extract the package path after the registry owner for gh api calls."""
    # ghcr.io/nstamoul/nautobot_apps_repo/shms-nautobot -> nautobot_apps_repo%2Fshms-nautobot
    parts = full_image.split("/")
    return "/".join(parts[2:])  # drop ghcr.io/nstamoul


def _selected_components(components: str) -> list[str]:
    """Parse a comma-separated component selector."""
    requested = [item.strip().lower() for item in components.split(",") if item.strip()]
    if not requested or "all" in requested:
        return list(IMAGE_COMPONENTS)

    selected = []
    for requested_component in requested:
        try:
            component = COMPONENT_ALIASES[requested_component]
        except KeyError as exc:
            valid = ", ".join(sorted(COMPONENT_ALIASES))
            raise ValueError(f"Unknown component {requested_component!r}. Valid values: {valid}") from exc
        if component != "all" and component not in selected:
            selected.append(component)
    return selected


def _resolve_image_updates(tag: str, components: str) -> tuple[dict, list[str]]:
    """Resolve GHCR digests for selected components and return env updates."""
    selected = _selected_components(components)
    updates = {}
    print(f"Resolving digests for tag: {tag}")
    print(f"Components: {', '.join(selected)}")
    for component in selected:
        env_key, image, label = IMAGE_COMPONENTS[component]
        digest = _gh_digest(_pkg_name(image), tag)
        updates[env_key] = f"{image}@{digest}"
        print(f"  {label}: {digest}")
    return updates, selected


def _ssh(node: str, cmd: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command on a remote node via SSH."""
    return subprocess.run(["ssh", node, cmd], check=check, text=True, capture_output=capture)


def _remote_update_env(node: str, updates: dict, compose_dir: str = "/opt/nautobot/environments"):
    """Update image keys in both production env files on a remote node.

    Production nodes can load image pins from both .env and local.shms.env.
    Keeping the two files aligned prevents a later compose/deploy operation from
    resurrecting an older image after a successful promotion.
    """
    script = f"""
from pathlib import Path

compose_dir = Path({compose_dir!r})
updates = {updates!r}
env_files = {REMOTE_ENV_FILES!r}

for env_name in env_files:
    env_path = compose_dir / env_name
    if not env_path.exists():
        print(f"  [{{env_name}}] missing, skipped")
        continue

    lines = env_path.read_text().splitlines()
    written = set()
    output = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            output.append(f"{{key}}={{updates[key]}}")
            written.add(key)
        else:
            output.append(line)

    for key, value in updates.items():
        if key not in written:
            output.append(f"{{key}}={{value}}")

    env_path.write_text("\\n".join(output) + "\\n")
    print(f"  [{{env_name}}] updated")
"""
    _ssh(node, f"python3 - <<'PY'\n{script}PY")
    print(f"  [{node}] image pins updated")


def _remote_pull_app(node: str, compose_dir: str = "/opt/nautobot/environments"):
    """Pull app stack images on a remote node before restarting."""
    print(f"  [{node}] Pulling app stack images...")
    _ssh(
        node,
        f"cd {compose_dir} && set -a && source .env && set +a && "
        f"docker compose -f docker-compose.shms-app.yml pull nautobot celery_worker celery_beat",
    )


def _remote_pull_vpn_control(node: str, compose_dir: str = "/opt/nautobot/environments"):
    """Pull vpn-control-api image on a remote node before restarting."""
    print(f"  [{node}] Pulling vpn-control-api image...")
    _ssh(
        node,
        f"cd {compose_dir} && set -a && source .env && set +a && "
        f"VPN_NODE_NAME={node} docker compose -f docker-compose.shms-vpn.control.yml pull vpn-control-api",
    )


def _remote_restart_app(node: str, compose_dir: str = "/opt/nautobot/environments"):
    """Restart only the currently-running app services on a remote node.

    Detects running services first so celery_beat is never started on nodes
    that intentionally don't run it (e.g. nb-ha-02).
    """
    result = _ssh(
        node,
        f"cd {compose_dir} && docker compose -f docker-compose.shms-app.yml ps --services --filter status=running 2>/dev/null",
        check=False, capture=True,
    )
    running = result.stdout.strip().split() if result.returncode == 0 and result.stdout.strip() else []
    services_arg = " ".join(running)
    label = ", ".join(running) if running else "all"
    print(f"  [{node}] Restarting app stack ({label})...")
    _ssh(
        node,
        f"cd {compose_dir} && set -a && source .env && set +a && "
        f"docker compose -f docker-compose.shms-app.yml up -d {services_arg}",
    )


def _remote_restart_vpn_control(node: str, compose_dir: str = "/opt/nautobot/environments"):
    """Restart vpn-control-api on a remote node."""
    print(f"  [{node}] Restarting vpn-control-api...")
    _ssh(
        node,
        f"cd {compose_dir} && set -a && source .env && set +a && "
        f"VPN_NODE_NAME={node} docker compose -f docker-compose.shms-vpn.control.yml up -d vpn-control-api",
    )


def _remote_wait_healthy(node: str, container_name: str, timeout_seconds: int = 180):
    """Wait for a remote container to report healthy, or just running if no healthcheck exists."""
    print(f"  [{node}] Waiting for {container_name} to become healthy...")
    _ssh(
        node,
        f"""timeout {timeout_seconds} bash -lc '
while true; do
  status="$(docker inspect -f '{{{{.State.Status}}}}' {container_name} 2>/dev/null || true)"
  health="$(docker inspect -f '{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{end}}}}' {container_name} 2>/dev/null || true)"
  if [ "$health" = "healthy" ] || {{ [ -z "$health" ] && [ "$status" = "running" ]; }}; then
    exit 0
  fi
  if [ "$status" = "exited" ] || [ "$status" = "dead" ]; then
    docker logs --tail 80 {container_name} || true
    exit 1
  fi
  sleep 5
done
'""",
    )


# ------------------------------------------------------------------------------
# PROMOTE
# ------------------------------------------------------------------------------
@task(
    help={
        "tag": "Image tag to promote (e.g. main-a5efb51). Required.",
        "components": "Comma-separated components to promote: all, nautobot/app, vpn, vpn-control.",
        "yes": "Skip confirmation prompt.",
    }
)
def promote(context, tag, components="all", yes=False):
    """Promote a CI-built image tag to production by updating .env and restarting the stack.

    Fetches selected digests from GHCR via `gh api`, updates environments/.env,
    then restarts the affected local stacks.

    Example:
        invoke promote --tag main-a5efb51
        invoke promote --tag main-a5efb51 --components nautobot
    """
    updates, selected = _resolve_image_updates(tag, components)

    if not yes:
        confirm = input("\nPromote these images? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            return

    _write_local_image_updates(updates)

    if "nautobot" in selected:
        print("\nRestarting app stack...")
        docker_compose(context, "up -d")

    if "vpn-control" in selected:
        print("\nRestarting vpn-control-api...")
        vpn_control_compose(context, "up -d vpn-control-api")

    if selected == ["vpn"]:
        print("\nUpdated VPN image pin. Existing tenant VPN containers are not restarted automatically.")

    print(f"\nPromotion to {tag} complete for: {', '.join(selected)}.")


@task(
    help={
        "tag": "Image tag to promote (e.g. main-a5efb51). Required.",
        "components": "Comma-separated components to promote: all, nautobot/app, vpn, vpn-control.",
        "yes": "Skip confirmation prompt.",
    }
)
def promote_nodes(context, tag, components="all", yes=False):
    """Promote a CI-built image tag to all production nodes from this machine.

    Resolves digests via local `gh api`, then SSHes to each node listed under
    nautobot_docker_compose.nodes in invoke.yml to update the remote image pins,
    pull the pinned images, and restart both the app stack and vpn-control-api.
    The servers do not need GitHub CLI credentials for this task.

    Running services are detected per-node so a service that is intentionally
    not running (e.g. celery_beat on nb-ha-02) is never accidentally started.

    Example:
        invoke promote-nodes --tag main-a5efb51
        invoke promote-nodes --tag main-a5efb51 --components nautobot
    """
    cfg = context.nautobot_docker_compose
    try:
        nodes = list(cfg.nodes)
    except AttributeError:
        print("No nodes configured. Add 'nodes: [nb-ha-01, nb-ha-02]' to invoke.yml.")
        return
    if not nodes:
        print("nodes list in invoke.yml is empty.")
        return

    updates, selected = _resolve_image_updates(tag, components)
    print(f"\nTarget nodes: {', '.join(nodes)}")

    if not yes:
        confirm = input("\nPromote to all nodes? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            return

    for node in nodes:
        print(f"\n--- {node} ---")
        _remote_update_env(node, updates)
        if "nautobot" in selected:
            _remote_pull_app(node)
            _remote_restart_app(node)
            _remote_wait_healthy(node, "nautobot")
        if "vpn-control" in selected:
            _remote_pull_vpn_control(node)
            _remote_restart_vpn_control(node)
            _remote_wait_healthy(node, "vpn-control-api")
        if selected == ["vpn"]:
            print(f"  [{node}] Updated VPN image pin. Existing tenant VPN containers were not restarted.")

    print(f"\nPromotion of {tag} complete on {', '.join(nodes)} for: {', '.join(selected)}")


@task(
    help={"tag": "Optional tag to check. Defaults to latest two versions."}
)
def images(context, tag=None):
    """List current image versions: what is pinned in .env vs what is running."""
    env = _read_env_file()
    print("\n--- Pinned in .env ---")
    for k in ("SHMS_NAUTOBOT_IMAGE", "SHMS_VPN_IMAGE", "SHMS_VPN_CONTROL_API_IMAGE"):
        print(f"  {k}={env.get(k, '(not set)')}")

    print("\n--- Running containers ---")
    context.run(
        "docker inspect nautobot celery_worker celery_beat vpn-control-api "
        "--format '{{.Name}}  {{slice .Config.Image 0 90}}  ({{.State.Status}})' 2>/dev/null || true"
    )

    if tag:
        print(f"\n--- Latest digests for tag {tag} on GHCR ---")
        for pkg, label in [
            (_pkg_name(IMAGE_NAUTOBOT), "shms-nautobot"),
            (_pkg_name(IMAGE_VPN), "shms-vpn"),
            (_pkg_name(IMAGE_VPN_CONTROL_API), "shms-vpn-control-api"),
        ]:
            try:
                digest = _gh_digest(pkg, tag)
                print(f"  {label}: {digest}")
            except Exception as exc:  # pylint: disable=broad-except
                print(f"  {label}: ERROR - {exc}")


# ------------------------------------------------------------------------------
# START / STOP / RESTART
# ------------------------------------------------------------------------------
@task
def start(context):
    """Start the Nautobot app stack (nautobot, celery_worker, celery_beat)."""
    print("Starting SHMS Nautobot stack...")
    docker_compose(context, "up -d")


@task
def stop(context):
    """Stop the Nautobot app stack."""
    print("Stopping SHMS Nautobot stack...")
    docker_compose(context, "down")


@task
def restart(context):
    """Gracefully restart the Nautobot app stack."""
    print("Restarting SHMS Nautobot stack...")
    docker_compose(context, "restart")


@task
def recreate(context):
    """Force-recreate all app stack containers (picks up .env changes without promote)."""
    print("Recreating SHMS Nautobot stack...")
    docker_compose(context, "up -d --force-recreate")


@task
def ps(context):
    """Show container status for all managed stacks."""
    print("--- App stack ---")
    docker_compose(context, "ps")
    print("\n--- VPN control API ---")
    vpn_control_compose(context, "ps")


@task
def logs(context, follow=False, service="nautobot celery_worker"):
    """Tail logs for the app stack (default: nautobot and celery_worker)."""
    cmd = f"logs {'--follow ' if follow else ''}{service}"
    docker_compose(context, cmd, pty=follow)


# ------------------------------------------------------------------------------
# VPN CONTROL API
# ------------------------------------------------------------------------------
@task
def vpn_control_start(context):
    """Start the vpn-control-api container."""
    print("Starting vpn-control-api...")
    vpn_control_compose(context, "up -d vpn-control-api")


@task
def vpn_control_stop(context):
    """Stop the vpn-control-api container."""
    print("Stopping vpn-control-api...")
    vpn_control_compose(context, "down")


@task
def vpn_control_restart(context):
    """Restart the vpn-control-api container."""
    print("Restarting vpn-control-api...")
    vpn_control_compose(context, "restart vpn-control-api")


@task
def vpn_control_logs(context, follow=False):
    """Tail vpn-control-api logs."""
    vpn_control_compose(context, f"logs {'--follow ' if follow else ''}vpn-control-api", pty=follow)


# ------------------------------------------------------------------------------
# NAUTOBOT MANAGEMENT COMMANDS
# ------------------------------------------------------------------------------
@task
def post_upgrade(context):
    """Run nautobot-server post_upgrade (migrate, collectstatic, etc.)."""
    run_command(context, "nautobot-server post_upgrade")


@task
def migrate(context):
    """Run nautobot-server migrate."""
    run_command(context, "nautobot-server migrate")


@task
def nbshell(context):
    """Open an interactive nautobot-server shell_plus session."""
    run_command(context, "nautobot-server shell_plus", pty=True)


@task
def cli(context):
    """Open a bash shell inside the running nautobot container."""
    run_command(context, "bash", pty=True)


@task(help={"user": "Superuser username (default: admin)"})
def createsuperuser(context, user="admin"):
    """Create a Nautobot superuser account."""
    run_command(context, f"nautobot-server createsuperuser --username {user}", pty=True)
