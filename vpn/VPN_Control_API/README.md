# VPN Control API

Small FastAPI service that exposes a minimal HTTP interface for the existing `vpn/vpn.sh`
script. Nautobot jobs (or other automation) can call this service to make sure a VPN
customer profile is connected before dispatching work to the `vpn` queue.

## Endpoints

- `GET /healthz` – basic liveness check (requires the API key header if configured)
- `GET /status` – structured status of the VPN container and dedicated worker
- `POST /start` – ensure the VPN is connected for the requested customer.
  - Body:
    ```json
    {
      "customer": "Ippokratio",
      "otp": "123456",
      "authgroup": "SomeRealm",
      "banner_response": "yes",
      "extra_args": "--pppd-use-peerdns=0",
      "passthrough": "1.1.1.1,example.com"
    }
    ```
  - If the VPN is already connected to that customer, the script is left untouched and
    only the dedicated worker is started (if needed).
- `POST /stop` – stop the VPN tunnel and remove the dedicated worker.

All responses are JSON; client side failures include the captured stdout/stderr from
`vpn.sh` for quick troubleshooting.

## Authentication

If `VPN_CONTROL_API_KEY` is set in the environment before starting the service, every
request must include `X-VPN-Control: <key>` to be accepted. Leave the variable unset to
disable authentication (not recommended beyond local testing).

## Running locally

```bash
cd /mnt/c/_tools/_automation_git/nautobot-docker-compose
python3 -m venv .venv
. .venv/bin/activate
pip install -r vpn/VPN_Control_API/requirements.txt

# Optional: export VPN_CONTROL_API_KEY=supersecret
uvicorn vpn.VPN_Control_API.app:app --host 127.0.0.1 --port 5001
```

The process must run as the same user that normally executes `vpn/vpn.sh`, so it can
access Vault credentials, `vpn/.env`, and Docker.

For persistent use, wrap the command in a systemd unit or supervisor to ensure it
restarts on boot.

### Running as part of docker-compose

Ship the API alongside the rest of the Nautobot stack:

```bash
# Build the image once (use the same compose files you pass to `inv start`)
docker compose \
  --project-name nautobot-docker-compose \
  --project-directory environments \
  -f environments/docker-compose.postgres.yml \
  -f environments/docker-compose.base.yml \
  -f environments/docker-compose.local.yml \
  build vpn_control_api

# Start it (still optional until you need it)
docker compose \
  --project-name nautobot-docker-compose \
  --project-directory environments \
  -f environments/docker-compose.postgres.yml \
  -f environments/docker-compose.base.yml \
  -f environments/docker-compose.local.yml \
  up -d vpn_control_api
```

The service mounts the project directory at `/workspace` and the Docker socket, so
commands issued by the API act exactly like the host version. Set `VPN_CONTROL_API_KEY`
in `environments/local.env` (exported to the container) to enforce auth.

### systemd service (WSL/systemd-enabled hosts)

1. Ensure systemd is enabled in your WSL distro (WSL 2 supports this via `/etc/wsl.conf`).
2. Create a dedicated virtualenv as above; the service definition expects it at
   `vpn/VPN_Control_API/.venv`. Adjust the unit if you place it elsewhere.
3. Copy the provided template to `/etc/systemd/system` and enable it:

   ```bash
   sudo cp vpn/VPN_Control_API/systemd/vpn-control@.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now vpn-control@nstam.service
   ```

   Replace `nstam` with the Unix user that should own the process, and edit the unit
   to set `VPN_CONTROL_API_KEY` or tweak the `PATH` if needed.

4. Check status with:

   ```bash
   systemctl status vpn-control@nstam.service
   journalctl -u vpn-control@nstam.service -f
   ```

## Nautobot Job integration

Inside a Nautobot job (running on the default queue) you can now do:

```python
import requests

resp = requests.post(
    "http://vpn-control-api:5001/start",
    json={"customer": "Ippokratio"},
    headers={"X-VPN-Control": "supersecret"},
    timeout=60,
)
resp.raise_for_status()
status = resp.json()
```

Once the call succeeds, schedule the actual device-access job on the `vpn` queue so it
executes on `celery_worker_vpn`.
