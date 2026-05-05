# SHMS App Versioning

SHMS Nautobot apps are version controlled in this deployment repository and
released as part of the Nautobot container image. Jobs may still use Nautobot's
Git repository sync, but apps must not be Git-synced directly into a running
container.

## Policy

- Keep app source under `plugins/`.
- Reference local apps from the root `pyproject.toml` with Poetry path
  dependencies.
- Build and deploy a new Nautobot image for every app change.
- Roll back by redeploying the previous image or previous deployment commit.
- Do not commit local app credentials, SQLite test databases, caches, or build
  output.

## Current Local Apps

| App | Source path | Installed package |
| --- | --- | --- |
| Cisco order tracking | `plugins/nautobot-app-nbcot` | `nbcot` |
| Connectivity matrix | `plugins/nautobot-app-nautobot-connectivity-matrix` | `nautobot-connectivity-matrix` |
| Software lifecycle fork | `plugins/nautobot-app-nautobot_software_lifecycle` | `nautobot-software-lifecycle` |
| VPN manager | `plugins/nautobot-app-vpn-manager` | `nautobot-vpn-manager` |
| UI plugin overrides | `plugins/nautobot_ui_plugin` | copied over `nautobot-ui-plugin` during image build |

## Change Workflow

1. Edit the app source under `plugins/`.
2. Add any migrations and focused tests with the app change.
3. Update the app's `pyproject.toml` version when the change is a release-worthy
   app change.
4. Run app tests where the local Nautobot/Django environment supports them.
5. Build the SHMS Nautobot image from this repository.
6. Run `nautobot-server post_upgrade` as part of deployment.
7. Start or restart the approved Nautobot services.

The image build copies the `plugins/` tree into `/source/plugins` and installs
the root Poetry environment. That makes the Git commit and resulting image the
version boundary for apps.
