# SHMS AD / RBAC Specification

## Goal

Provide a scalable access-control model for SHMS Nautobot across three axes:

1. Access level:
   - user
   - admin
   - superadmin
2. Tenant:
   - one or more customer tenants
3. Capability domain:
   - operational
   - non-operational

Example:
- sales teams should be able to see non-operational data such as devices, inventory, serial numbers, lifecycle/EOX/coverage data
- sales teams should not be able to access IPAM, VPN, or operational automation surfaces

## Architectural Constraints

### Nautobot permissions are additive

Nautobot merges permissions from all groups a user belongs to.

This means the following design is unsafe:
- one group grants tenant scope
- another group grants operational or non-operational capability

That would union privileges and leak access across tenants or domains.

Because of this, SHMS must use **composite entitlement groups** that encode:
- tenant
- capability domain
- access level

Example:
- `NB-AXEPA-OPS-USERS`
- `NB-AXEPA-OPS-ADMINS`
- `NB-AXEPA-NONOPS-USERS`
- `NB-AXEPA-NONOPS-ADMINS`

### Nautobot is model/object-RBAC, not field-RBAC

Nautobot can restrict:
- models
- objects
- actions
- API/UI visibility through object permissions

Nautobot cannot cleanly enforce true field-level access on a single object page.

Implication:
- we can segregate operational vs non-operational **models and workflows**
- we cannot safely hide operational attributes while showing non-operational attributes on the same object without further data-model or UI refactoring

If true field-level separation becomes mandatory later, one of these will be required:
- move non-operational data into separate models/apps
- expose a custom non-operational UI surface
- implement custom view logic that filters fields/templates explicitly

## AD Design

### Recommended OU layout

Create a dedicated Nautobot group OU:

- `OU=Nautobot,OU=Groups,DC=shms,DC=local`
- platform gate groups under:
  - `OU=Platform,OU=Nautobot,OU=Groups,DC=shms,DC=local`
- tenant entitlement groups under:
  - `OU=<TENANT>,OU=TenantAccess,OU=Nautobot,OU=Groups,DC=shms,DC=local`

This keeps Nautobot access groups isolated from the rest of AD.

### AD group classes

There are two different classes of groups.

#### 1. LDAP flag groups

These control whether a user can log in and whether Nautobot marks the user as staff or superuser.

- `NB-LOGIN`
- `NB-STAFF`
- `NB-SUPERUSERS`

Recommended DNs:

- `CN=NB-LOGIN,OU=Platform,OU=Nautobot,OU=Groups,DC=shms,DC=local`
- `CN=NB-STAFF,OU=Platform,OU=Nautobot,OU=Groups,DC=shms,DC=local`
- `CN=NB-SUPERUSERS,OU=Platform,OU=Nautobot,OU=Groups,DC=shms,DC=local`

Behavior:
- `NB-LOGIN`
  - required to authenticate into Nautobot
  - maps to `is_active=True`
- `NB-STAFF`
  - maps to `is_staff=True`
  - allows staff/admin UI access
- `NB-SUPERUSERS`
  - maps to `is_superuser=True`
  - full unrestricted platform access

#### 2. Composite entitlement groups

These groups represent the actual business access model.

Naming convention:

- `NB-<TENANTKEY>-OPS-USERS`
- `NB-<TENANTKEY>-OPS-ADMINS`
- `NB-<TENANTKEY>-NONOPS-USERS`
- `NB-<TENANTKEY>-NONOPS-ADMINS`

Where:
- `<TENANTKEY>` is a deterministic uppercase tenant token derived from the tenant name
- non-alphanumeric characters are replaced with `-`

Examples:
- `NB-AXEPA-OPS-USERS`
- `NB-AXEPA-NONOPS-USERS`
- `NB-IONIO-PANEPISTIMIO-OPS-ADMINS`
- `NB-E-TRIKALA-NONOPS-ADMINS`

### Group membership rules

Recommended policy:

- all Nautobot users must be in `NB-LOGIN`
- administrators who need the staff UI must also be in `NB-STAFF`
- only platform owners should be in `NB-SUPERUSERS`
- tenant/capability access is granted only through the composite entitlement groups

Examples:

- Sales user for AXEPA:
  - `NB-LOGIN`
  - `NB-AXEPA-NONOPS-USERS`

- Operational tenant admin for Zenith:
  - `NB-LOGIN`
  - `NB-STAFF`
  - `NB-ZENITH-OPS-ADMINS`

- Platform owner:
  - `NB-LOGIN`
  - `NB-STAFF`
  - `NB-SUPERUSERS`

## Nautobot Model

### LDAP behavior

Nautobot should:
- authenticate against AD
- mirror AD groups
- require membership in `NB-LOGIN`
- map `NB-LOGIN`, `NB-STAFF`, and `NB-SUPERUSERS` to Django user flags

### Permission model

Nautobot object permissions should be created per composite entitlement group.

The bootstrap should create:
- mirrored Group objects matching the AD names
- ObjectPermissions with tenant-scoped constraints

### Tenant scoping

In this SHMS Nautobot build, tenant scoping must use `tenant__name`, not `tenant__slug`.

Reason:
- the current `Tenant` model does not expose a `slug` field

### Capability domains

#### Non-operational

Intended for:
- sales
- lifecycle/commercial viewers
- non-operational tenant stakeholders

Should include read-only access to tenant-scoped objects such as:
- devices
- inventory items
- lifecycle / EOX / coverage style records
- software license records where relevant

Should exclude:
- IPAM
- VPN workflows
- operational automation
- write access by default

#### Operational

Intended for:
- engineers
- operators
- tenant admins for operational workflows

Should include:
- device/inventory visibility
- IPAM
- circuits
- virtualization where tenant-scoped
- operational write access for admin variants

Should still avoid unrestricted delete by default.

## Default action policy

### Users

Default actions:
- `view`

### Admins

Default actions:
- `view`
- `add`
- `change`

### Superadmins

Do not model these with object permissions.

Use:
- AD -> `NB-SUPERUSERS`
- Nautobot -> `is_superuser=True`

## Reference data caveat

Some objects are global reference data rather than tenant-owned data, for example:
- manufacturers
- device types
- some platforms
- some locations depending on modeling choices

These do not always map cleanly to tenant constraints.

Current SHMS recommendation:
- tenant-scoped permissions should focus on tenant-owned data
- global reference data should be exposed only where required
- if strict tenant isolation is needed for reference data, the data model must evolve

## Onboarding workflow for a new tenant

1. Create the tenant in Nautobot.
2. Ensure tenant-owned objects are actually linked to that tenant.
3. Create the AD groups:
   - `NB-<TENANTKEY>-OPS-USERS`
   - `NB-<TENANTKEY>-OPS-ADMINS`
   - `NB-<TENANTKEY>-NONOPS-USERS`
   - `NB-<TENANTKEY>-NONOPS-ADMINS`
4. Assign users in AD.
5. Run the SHMS RBAC bootstrap job/script.
6. Validate:
   - mirrored Nautobot groups exist
   - object permissions exist
   - test user can only see intended tenant/domain objects

## Security boundary for jobs and secrets

Tenant RBAC in Nautobot UI is not sufficient by itself.

Two further controls are required:

1. Job code must enforce tenant scope during execution.
2. Vault policies must enforce tenant-scoped secret access.

Without those, a broadly privileged job or service token can bypass UI-level scoping.

## Implementation status in SHMS

This specification is implemented by:
- LDAP flag-group environment configuration
- mirrored AD groups in Nautobot
- an idempotent RBAC bootstrap script that creates:
  - the flag groups
  - the composite entitlement groups
  - tenant/capability-scoped object permissions
