# VPN client selection and Cisco Secure Client support plan

Date: 2026-05-05

## Scope

Add an explicit VPN client implementation selector for Cisco AnyConnect-family
VPNs while preserving the existing container-owned tunnel model for current
OpenConnect, Forti, OpenVPN, and WireGuard profiles.

This plan is based on read-only investigation of:

- Vault VPN metadata and secret key shape for all current customer profiles.
- `vpn/vpn.sh`, `vpn/vpn/entrypoint.sh`, `vpn/vpn/vault_fetch.sh`.
- DNS/reconnect helpers under `vpn/vpn/`.
- `vpn/VPN_Control_API/app.py` and its current tests.
- `plugins/nautobot-app-vpn-manager`.
- VPN compose files under `environments/`.
- Existing SHMS VPN architecture docs.
- Local OpenConnect and Cisco Secure Client CLI tests against e-Trikala.

No Vault secret values were printed, no Vault writes were performed, no deploys
were performed, and no production containers were restarted.

## Findings

OpenConnect supports the Cisco AnyConnect protocol in general, but the tested
e-Trikala Meraki headend is not compatible with the current OpenConnect path.
The failure is after successful authentication/cookie issuance, when OpenConnect
uses the cookie for the tunnel `CONNECT` request and receives `HTTP/1.1 401
Unauthorized`.

The official Cisco Secure Client CLI succeeds for e-Trikala on the local host:

```bash
/opt/cisco/secureclient/bin/vpn connect "e-Trikala VPN Profile Admins"
```

The local profile needed by the official client is:

```text
HostName: e-Trikala VPN Profile Admins
HostAddress: stadium-wifi-wired-tnknwjndbr.dynamic-m.com
UserGroup: RAVPN_Admins
```

Quoting the profile name is required because it contains spaces. The successful
CLI test did not require MFA, SAML, or a banner response. Cisco documentation
does allow an optional banner during CLI login, with a default negative response
if the user does not accept it.

The current SHMS runtime assumes the VPN tunnel is owned by a Docker `vpn`
appliance container:

- `environments/docker-compose.shms-vpn.service.yml` starts a privileged `vpn`
  service with TUN/PPP devices.
- `environments/docker-compose.shms-vpn.queue.yml` runs
  `celery_worker_vpn` with `network_mode: "service:vpn"`.
- `vpn/VPN_Control_API/app.py` detects tunnel state by inspecting `ppp0`,
  `tun0`, or `wg0` inside the VPN container.
- DNS orchestration and route-change monitoring run inside the VPN container.

A host-level official Cisco Secure Client connection creates host routes and a
host tunnel interface. A worker using `network_mode: "service:vpn"` will not see
that tunnel. Therefore, official Cisco Secure Client support is not just another
argument to the existing `vpn` appliance container unless the official client is
installed and run inside that same container namespace. Containerizing Cisco
Secure Client is high risk because it requires Cisco packaging, `vpnagentd`,
system integration, licensing/distribution review, and reliable headless agent
startup.

## Naming convention

Keep `vpn_type` as the protocol/product family and add `vpn_client` as the
implementation.

Use:

```text
vpn_type=cisco-anyconnect
vpn_client=openconnect
```

or:

```text
vpn_type=cisco-anyconnect
vpn_client=cisco-secure-client
```

Do not introduce `vpn_type=cisco-secure-client-official`; that mixes the
protocol family with the client implementation and will make routing, UI, and
future migration logic ambiguous.

Backward compatibility rule:

```text
if vpn_type == cisco-anyconnect and vpn_client is missing:
    vpn_client = openconnect
```

## Vault metadata model

Add these metadata fields. They are metadata, not secret data:

```text
vpn_client=openconnect|cisco-secure-client
profile_name=<official Cisco Secure Client alias/profile name>
usergroup=<AnyConnect/Meraki group, if required>
client_runtime=container|host
worker_network_mode=service-vpn|host|remote-worker
```

Recommended e-Trikala metadata:

```text
vpn_type=cisco-anyconnect
vpn_client=cisco-secure-client
host=stadium-wifi-wired-tnknwjndbr.dynamic-m.com
port=443
auth_method=password
requires_cert=false
trusted_cert=pin-sha256:1Hvrf2ddlobhLR8zD/0BBLs29gR8LY7BfRIjxU9IEw8=
profile_name=e-Trikala VPN Profile Admins
usergroup=RAVPN_Admins
client_runtime=host
worker_network_mode=host
```

`trusted_cert` should remain available for OpenConnect and for audit/comparison,
but the official Cisco client validates server trust through its own profile,
local trust store, and CLI behavior. If Linux CLI cannot display an untrusted
certificate prompt, Cisco documents that the connection can fail rather than
prompting.

## Implementation plan

### 1. Add VPN client metadata retrieval

Update `vpn/vpn/vault_fetch.sh`:

- Read `vpn_client`, `profile_name`, `usergroup`, `client_runtime`, and
  `worker_network_mode` from KV metadata.
- Export them as:
  - `VAULT_VPN_CLIENT`
  - `VAULT_CISCO_PROFILE_NAME`
  - `VAULT_CISCO_USERGROUP`
  - `VAULT_CLIENT_RUNTIME`
  - `VAULT_WORKER_NETWORK_MODE`
- Keep secret values out of logs.
- Log only presence or safe metadata values:

```bash
VPN_CLIENT_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.vpn_client // .custom_metadata.vpn_client // empty')
CISCO_PROFILE_NAME_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.profile_name // .custom_metadata.profile_name // empty')
CISCO_USERGROUP_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.usergroup // .custom_metadata.usergroup // empty')
CLIENT_RUNTIME_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.client_runtime // .custom_metadata.client_runtime // empty')
WORKER_NETWORK_MODE_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.worker_network_mode // .custom_metadata.worker_network_mode // empty')
```

### 2. Normalize Cisco naming in the VPN entrypoint

Update `vpn/vpn/entrypoint.sh`:

- Introduce:
  - `VPN_CLIENT="${VPN_CLIENT:-}"`
  - `CISCO_HOST`, `CISCO_PORT`, `CISCO_USERNAME`, `CISCO_PASSWORD`
  - `CISCO_AUTHGROUP`
  - `CISCO_USERGROUP`
  - `CISCO_PROFILE_NAME`
  - `CISCO_SECURE_CLIENT_BIN="${CISCO_SECURE_CLIENT_BIN:-/opt/cisco/secureclient/bin/vpn}"`
- Continue mapping existing `FORTI_*` variables for compatibility in this
  release.
- After Vault fetch:

```bash
[[ -z "${VPN_CLIENT}" && -n "${VAULT_VPN_CLIENT:-}" ]] && VPN_CLIENT="$VAULT_VPN_CLIENT"
if [[ "${VPN_TYPE}" == "cisco-anyconnect" && -z "${VPN_CLIENT}" ]]; then
  VPN_CLIENT="openconnect"
fi
[[ -n "${VAULT_CISCO_PROFILE_NAME:-}" ]] && CISCO_PROFILE_NAME="$VAULT_CISCO_PROFILE_NAME"
[[ -n "${VAULT_CISCO_USERGROUP:-}" ]] && CISCO_USERGROUP="$VAULT_CISCO_USERGROUP"
```

- In the `cisco-anyconnect` case, dispatch by `VPN_CLIENT`:

```bash
case "${VPN_CLIENT}" in
  openconnect) run_cisco_anyconnect_openconnect ;;
  cisco-secure-client) run_cisco_anyconnect_secure_client ;;
  *) die "Unsupported VPN_CLIENT '${VPN_CLIENT}' for VPN_TYPE '${VPN_TYPE}'" ;;
esac
```

### 3. Improve the OpenConnect Cisco backend without changing defaults

Rename the current `run_cisco_anyconnect` to
`run_cisco_anyconnect_openconnect`.

Add explicit support for `CISCO_USERGROUP`:

- Use `--usergroup "$CISCO_USERGROUP"` for AnyConnect URL/group selection.
- Keep `--authgroup "$CISCO_AUTHGROUP"` or existing `FORTI_REALM` behavior for
  forms that expose auth-group selection.
- Do not overload `--authgroup` for Meraki `UserGroup` unless a specific profile
  proves that is the right field.

Keep `--non-inter` behavior for accepted banners, but document that OpenConnect
may still fail if the gateway rejects the cookie during the tunnel `CONNECT`.

### 4. Add a host official-client backend, gated by runtime mode

Do not try to run the local macOS/Linux official client from inside the current
VPN container. Add an explicit host runtime path in `vpn/vpn.sh` and the Control
API.

Add a helper script, for example:

```text
vpn/cisco_secure_client_host.sh
```

Responsibilities:

- Run on the host where `/opt/cisco/secureclient/bin/vpn` and `vpnagentd` exist.
- Fetch Vault credentials read-only, same as the container path.
- Resolve `profile_name` from metadata, falling back to `host` only if no
  profile is configured.
- Start:

```bash
printf '%s\n%s\n%s\n' "$CISCO_USERNAME" "$CISCO_PASSWORD" "${CISCO_BANNER_RESPONSE:-y}" \
  | /opt/cisco/secureclient/bin/vpn -s connect "$CISCO_PROFILE_NAME"
```

- Treat success as seeing `state: Connected` or `notice: Connected`.
- Stop:

```bash
/opt/cisco/secureclient/bin/vpn disconnect
```

- Status:

```bash
/opt/cisco/secureclient/bin/vpn state
/opt/cisco/secureclient/bin/vpn stats
```

- Never echo passwords. Redact stdin payload summaries.

Banner handling:

- If `banner_response` is present, append it after username/password.
- Default to `y` only for `cisco-secure-client` profiles where metadata says
  `banner_default_accept=true`, or where the operator passes a runtime override.
- For e-Trikala, current test evidence says the banner input is not consumed.

### 5. Add worker networking for host-managed VPNs

Add a separate compose file for host-routed workers:

```text
environments/docker-compose.shms-vpn.host-worker.yml
```

Use:

```yaml
services:
  celery_worker_vpn:
    network_mode: "host"
```

Preserve the current `docker-compose.shms-vpn.queue.yml` for container-owned
tunnels.

In `vpn/VPN_Control_API/app.py`:

- Add `client_runtime` and `worker_network_mode` resolution from Vault metadata
  before start.
- If `vpn_client=cisco-secure-client` and `client_runtime=host`, start the host
  official-client helper instead of `docker compose up vpn`.
- Use the host-worker compose file when `worker_network_mode=host`.
- Status for host official-client slots must not depend on a `vpn` appliance
  container. It should query the helper and report:
  - `vpn_running=true` when official CLI state is connected.
  - `tunnel_interface` from helper output if known, or `cisco-secure-client`.
  - `source_of_truth=vault`.
  - `vpn_client=cisco-secure-client`.
- Stop should disconnect the official client and then stop host-mode workers.

Important single-active constraint:

- A host official Cisco client is host-global, not per-container. Enforce one
  active host-managed Cisco slot per node unless testing proves separate
  namespaces and clients can coexist.

### 6. Extend API and manager UI models

In `vpn/VPN_Control_API/app.py`:

- Add optional fields to `StartRequest`:
  - `vpn_client`
  - `profile_name`
  - `usergroup`
  - `client_runtime`
  - `worker_network_mode`
- Add fields to `SlotStatus`:
  - `vpn_type`
  - `vpn_client`
  - `client_runtime`
  - `worker_network_mode`
- Keep all fields optional so old clients continue to work.
- Runtime request fields override Vault metadata for one run only.

In `plugins/nautobot-app-vpn-manager`:

- Add optional runtime overrides for `vpn_client`, `profile_name`, `usergroup`,
  and `worker_network_mode`.
- Display `vpn_client` and `client_runtime` on the active slot card.
- Mark official-client host slots clearly so operators understand that a host
  VPN is active.

### 7. Update docs and operator runbook

Update:

- `vpn/VPN_Control_API/README.md`
- `docs/SHMS_VPN_HA_DESIGN.md`
- `docs/SHMS_VPN_MULTI_TENANT_CONTROL_PLANE.md`

Document:

- `vpn_type` versus `vpn_client`.
- OpenConnect remains the default for `cisco-anyconnect`.
- Official Cisco Secure Client is selected per profile.
- Host official-client mode requires host installation of Cisco Secure Client
  and `vpnagentd`.
- Host official-client mode uses host-routed workers or a registered remote
  worker, not `network_mode: service:vpn`.
- Only one host official-client slot can be active on a node.

## Safe one-liner tests

These tests are read-only except for local VPN connect/disconnect on the test
machine. They must not be run on production nodes without an approved window.

OpenConnect compatibility reproduction:

```bash
printf '%s\n' "$VPN_PASSWORD" | openconnect --protocol=anyconnect --no-proxy --user "$VPN_USERNAME" --passwd-on-stdin --servercert 'pin-sha256:1Hvrf2ddlobhLR8zD/0BBLs29gR8LY7BfRIjxU9IEw8=' stadium-wifi-wired-tnknwjndbr.dynamic-m.com:443 --dump-http-traffic --authenticate
```

OpenConnect group-specific test:

```bash
printf '%s\n' "$VPN_PASSWORD" | openconnect --protocol=anyconnect --no-proxy --user "$VPN_USERNAME" --passwd-on-stdin --servercert 'pin-sha256:1Hvrf2ddlobhLR8zD/0BBLs29gR8LY7BfRIjxU9IEw8=' --usergroup RAVPN_Admins stadium-wifi-wired-tnknwjndbr.dynamic-m.com:443 --dump-http-traffic
```

Official Cisco Secure Client profile list:

```bash
/opt/cisco/secureclient/bin/vpn hosts
```

Official Cisco Secure Client state:

```bash
/opt/cisco/secureclient/bin/vpn state
```

Official Cisco Secure Client noninteractive connect:

```bash
printf '%s\n%s\n' "$VPN_USERNAME" "$VPN_PASSWORD" | /opt/cisco/secureclient/bin/vpn -s connect "e-Trikala VPN Profile Admins"
```

Official Cisco Secure Client disconnect:

```bash
/opt/cisco/secureclient/bin/vpn disconnect
```

Official client route visibility for a host-mode worker:

```bash
ip route get <customer-internal-ip>
```

Container namespace mismatch check:

```bash
docker compose --project-name shms-vpn-e-trikala --project-directory environments -f environments/docker-compose.shms-vpn.queue.yml run --rm celery_worker_vpn ip route get <customer-internal-ip>
```

Expected result before host-worker support: the host can route over the official
VPN, but the existing service-vpn worker cannot.

## Test plan

Add unit tests for `vpn/VPN_Control_API/app.py`:

- Missing `vpn_client` for `vpn_type=cisco-anyconnect` resolves to
  `openconnect`.
- `vpn_client=cisco-secure-client` selects host runtime only when metadata or
  request says `client_runtime=host`.
- Start command construction passes `profile_name`, `usergroup`, and
  `worker_network_mode` without logging passwords.
- Host official-client status does not require a Docker `vpn` container.
- Stop for host official-client calls disconnect before worker teardown.

Add shell tests or a lightweight pytest shell harness for:

- `vault_fetch.sh` metadata parsing.
- OpenConnect command assembly with `--usergroup` and `--authgroup`.
- Official-client helper command assembly and redaction.
- Refusal to run `cisco-secure-client` inside the existing VPN appliance
  container unless an explicit container runtime is implemented later.

Manual verification on a non-production host:

1. Verify OpenConnect-backed existing profile still starts a container-owned
   tunnel and worker.
2. Verify e-Trikala official-client host mode connects, reports connected
   status, starts a host-network worker, and routes a harmless customer IP.
3. Verify stop disconnects official Cisco Secure Client and stops only the
   matching tenant worker.
4. Verify the Nautobot VPN Manager dashboard shows client/runtime status.

## Rollout plan

1. Merge code and docs with no Vault metadata changes.
2. Deploy to a staging/non-production control node.
3. Add `vpn_client=openconnect` metadata to one existing Cisco profile only if
   needed for clarity; missing metadata should still default correctly.
4. Add e-Trikala metadata with `vpn_client=cisco-secure-client` and
   `client_runtime=host` in a scheduled maintenance/test window.
5. Start e-Trikala with one worker and run a harmless read-only reachability job.
6. Stop e-Trikala and verify official client disconnect state.
7. Roll out additional official-client profiles only when OpenConnect has been
   proven incompatible for that profile.

## Decision

Use both clients:

- Keep OpenConnect as the default implementation for `vpn_type=cisco-anyconnect`
  because it fits the current container-owned VPN architecture.
- Add official Cisco Secure Client as an explicit per-profile implementation for
  Meraki/AnyConnect headends like e-Trikala that reject OpenConnect after
  authentication.

Do not switch all Cisco AnyConnect profiles to the official client by default.
That would replace a container-isolated, tenant-scoped tunnel model with a
host-global VPN client and would require worker networking changes even for
profiles that already work.

## Primary references

- OpenConnect documents AnyConnect as a supported protocol and describes the
  cookie-then-HTTP-CONNECT tunnel flow:
  https://www.infradead.org/openconnect/anyconnect.html
- OpenConnect manual documents the relevant AnyConnect options including
  `--usergroup`, `--authgroup`, `--non-inter`, `--useragent`, `--version-string`,
  and `--os`:
  https://www.infradead.org/openconnect/manual.html
- Cisco documents the Secure Client CLI path, `connect`, `disconnect`, `stats`,
  and optional banner behavior:
  https://www.cisco.com/c/en/us/td/docs/security/vpn_client/anyconnect/Cisco-Secure-Client-5/admin/guide/b-cisco-secure-client-admin-guide-5-0/customize-localize-anyconnect.html
