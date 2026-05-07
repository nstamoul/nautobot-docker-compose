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

Official Cisco Secure Client must run inside the same `vpn` appliance container
namespace as OpenConnect, Forti, OpenVPN, and WireGuard. That preserves the
existing worker model where `celery_worker_vpn` uses
`network_mode: "service:vpn"`. The main risk is image packaging: Cisco installer
binaries must not be committed, and `vpnagentd` must run reliably inside the
privileged VPN container.

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
```

`trusted_cert` should remain available for OpenConnect and for audit/comparison,
but the official Cisco client validates server trust through its own profile,
local trust store, and CLI behavior. If Linux CLI cannot display an untrusted
certificate prompt, Cisco documents that the connection can fail rather than
prompting.

## Implementation plan

### 1. Add VPN client metadata retrieval

Update `vpn/vpn/vault_fetch.sh`:

- Read `vpn_client`, `profile_name`, and `usergroup` from KV metadata.
- Export them as:
  - `VAULT_VPN_CLIENT`
  - `VAULT_CISCO_PROFILE_NAME`
  - `VAULT_CISCO_USERGROUP`
- Keep secret values out of logs.
- Log only presence or safe metadata values:

```bash
VPN_CLIENT_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.vpn_client // .custom_metadata.vpn_client // empty')
CISCO_PROFILE_NAME_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.profile_name // .custom_metadata.profile_name // empty')
CISCO_USERGROUP_META=$(echo "$METADATA_JSON" | jq -r '.data.custom_metadata.usergroup // .custom_metadata.usergroup // empty')
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

### 4. Add a container-bundled official-client backend

Update the `vpn` image build so an approved Cisco Secure Client Linux installer
can be placed in `vpn/vpn/cisco-secure-client/` before building. The directory
must be gitignored so proprietary Cisco artifacts are not committed.

Runtime responsibilities:

- Run `/opt/cisco/secureclient/bin/vpnagentd` inside the privileged `vpn`
  container.
- Use the same Vault-loaded username/password as the OpenConnect path.
- Resolve `profile_name` from metadata, falling back to `host` only if no
  profile is configured.
- Connect inside the VPN container:

```bash
printf '%s\n%s\n%s\n' "$CISCO_USERNAME" "$CISCO_PASSWORD" "${CISCO_BANNER_RESPONSE:-y}" \
  | /opt/cisco/secureclient/bin/vpn -s connect "$CISCO_PROFILE_NAME"
```

- Treat success as seeing `state: Connected` or `notice: Connected`.
- Never echo passwords. Redact stdin payload summaries.
- Keep the container alive by polling `vpn state`.
- Let existing `vpn.sh stop` and compose teardown stop the client by removing
  the container.

Banner handling:

- If `banner_response` is present, append it after username/password.
- Default to `y` only for `cisco-secure-client` profiles where metadata says
  `banner_default_accept=true`, or where the operator passes a runtime override.
- For e-Trikala, current test evidence says the banner input is not consumed.

### 5. Preserve worker networking

In `vpn/VPN_Control_API/app.py`:

- Resolve `vpn_client`, `profile_name`, and `usergroup` from Vault metadata
  before start.
- Pass those values to `vpn.sh start` and the `vpn` compose service.
- Keep `environments/docker-compose.shms-vpn.queue.yml` unchanged:
  `celery_worker_vpn` continues to use `network_mode: "service:vpn"`.
- Status remains based on the `vpn` appliance container and its tunnel
  interfaces.

### 6. Extend API and manager UI models

In `vpn/VPN_Control_API/app.py`:

- Add optional fields to `StartRequest`:
  - `vpn_client`
  - `profile_name`
  - `usergroup`
- Add fields to `SlotStatus`:
  - `vpn_type`
  - `vpn_client`
- Keep all fields optional so old clients continue to work.
- Runtime request fields override Vault metadata for one run only.

In `plugins/nautobot-app-vpn-manager`:

- Add optional runtime overrides for `vpn_client`, `profile_name`, and
  `usergroup`.
- Display `vpn_client` on the active slot card.

### 7. Update docs and operator runbook

Update:

- `vpn/VPN_Control_API/README.md`
- `docs/SHMS_VPN_HA_DESIGN.md`
- `docs/SHMS_VPN_MULTI_TENANT_CONTROL_PLANE.md`

Document:

- `vpn_type` versus `vpn_client`.
- OpenConnect remains the default for `cisco-anyconnect`.
- Official Cisco Secure Client is selected per profile.
- Official Cisco Secure Client must be bundled into the `vpn` image and run in
  the `vpn` container namespace.
- Cisco installer artifacts are build inputs only and must not be committed.

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

Official client route visibility inside the VPN container:

```bash
docker exec <vpn-container> ip route get <customer-internal-ip>
```

Expected result: routes are visible inside the `vpn` container, and therefore
also visible to `celery_worker_vpn` through `network_mode: "service:vpn"`.

## Test plan

Add unit tests for `vpn/VPN_Control_API/app.py`:

- Missing `vpn_client` for `vpn_type=cisco-anyconnect` resolves to
  `openconnect`.
- Start command construction passes `profile_name`, `usergroup`, and
  `vpn_client` without logging passwords.
- `vpn_client=cisco-secure-client` still starts the normal `vpn` appliance
  compose service.

Add shell tests or a lightweight pytest shell harness for:

- `vault_fetch.sh` metadata parsing.
- OpenConnect command assembly with `--usergroup` and `--authgroup`.
- Official-client entrypoint command assembly and redaction.
- Clear runtime failure when `vpn_client=cisco-secure-client` is selected but
  the official client was not bundled into the image.

Manual verification on a non-production host:

1. Verify OpenConnect-backed existing profile still starts a container-owned
   tunnel and worker.
2. Build a non-production VPN image with the approved Cisco Secure Client Linux
   installer artifact staged under `vpn/vpn/cisco-secure-client/`.
3. Verify e-Trikala official-client container mode connects, reports connected
   status, starts the normal service-vpn worker, and routes a harmless customer
   IP from inside the worker namespace.
4. Verify stop tears down the matching tenant VPN container and worker.
5. Verify the Nautobot VPN Manager dashboard shows `vpn_client`.

## Rollout plan

1. Merge code and docs with no Vault metadata changes.
2. Deploy to a staging/non-production control node.
3. Add `vpn_client=openconnect` metadata to one existing Cisco profile only if
   needed for clarity; missing metadata should still default correctly.
4. Add e-Trikala metadata with `vpn_client=cisco-secure-client` in a scheduled
   maintenance/test window.
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
That would expand the blast radius and require every Cisco profile to depend on
the larger official-client image and its agent behavior even when OpenConnect
already works.

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
