# Nautobot Connectivity Matrix Workbench Design

## Context

The current connectivity matrix app still carries the shape of the failed first attempt: it supports XLSX template download, offline editing, reimport, and then online validation/execution. The new direction is to make the Nautobot app itself the planning surface. Excel export remains useful as an output/report, but Excel must no longer be the main workflow.

The app targets Nautobot 3.1 and will run in the existing SHMS HA Nautobot stack. The app should feel like a real Nautobot app while preserving the speed of an Excel-like keyboard workflow.

## Product Shape

The app has two independent work areas under a shared planning batch:

1. **Device / Stack Builder**
   - Supporting pane for creating planned devices, stacks, uplink modules, and generated interfaces.
   - Online replacement for the stack-plan Excel sheet.
   - Uses batch defaults for tenant, location, status, role, and platform.
   - Allows device type/profile and uplink module selection where known.
   - Creates planned app objects first; Nautobot objects are only created during explicit materialization.

2. **Connectivity Matrix**
   - Primary pane and main engineering focus.
   - Excel-like grid for online cabling plans.
   - Supports keyboard-first entry, mouse-friendly selection/actions, header filtering, sorting, drag/drop row ordering, per-row color, bulk color, per-row swap, bulk selected-row swap, validation, cable creation, and XLSX export.

## Data Model

Keep `ConnectionPlanBatch` as the workspace object, but expand the app beyond text-only connection rows.

Add `PlannedDevice`:

- `batch`
- `name`
- batch-derived defaults: tenant, location, status, role, platform
- device type/profile where known
- optional `materialized_device` FK to `dcim.Device`
- state such as `planned`, `materialized`, `error`
- source such as `builder`, `matrix`, or `import`

Add `PlannedInterface`:

- `planned_device`
- `name`
- type and speed/profile metadata where known
- optional `materialized_interface` FK to `dcim.Interface`
- generated interfaces from known profiles/device types, plus free-text planned interfaces when unknown

Extend `ConnectionPlan`:

- continue supporting real Nautobot device/interface FKs
- add planned endpoint references for unresolved devices/interfaces
- keep text fallbacks for fast entry and imports
- add `row_color` for pure visual cabling progress
- preserve row order, notes, medium, speed, SFP A, and SFP B

Rows must be able to reference either real Nautobot endpoints or planned endpoints cleanly. Existing Nautobot objects remain authoritative; planned objects are first-class app data until materialized.

## Matrix Behavior

Device cells:

- Autocomplete existing Nautobot devices.
- Allow unknown typed device names.
- Unknown devices remain planned unresolved references until the user runs **Materialize / Create Missing Devices**.
- Unknown devices must not be silently created on blur or save.

Interface cells:

- Existing device: dropdown shows only interfaces on that device that are not already cabled in Nautobot and not already reserved by another open matrix row.
- Planned unresolved device with known device type/profile: show generated interface suggestions.
- Planned unresolved device without profile: allow free-text interface names and validate later.
- The current row’s selected interface remains selectable while editing that same row.

SFP, medium, and speed:

- Dependent choices should be offered where the app has enough source data.
- Speed should depend on selected interface and/or SFP when known.
- When compatibility data is missing, allow entry but raise warnings instead of blocking planning.

Row actions:

- Per-row swap A/B swaps device, interface, SFP, and endpoint-specific display/lookup state.
- Bulk swap applies the same endpoint swap to selected rows.
- Swap preserves row color, medium, speed, notes, row order, and workflow status.
- Drag/drop row reordering persists to the server.
- Header sorting and filtering work per column.

Row color:

- Purely visual progress marker for cabling work.
- No named semantic meaning and no effect on validation or execution.
- Supports per-row color and bulk color for selected rows.
- Included in XLSX export.

## Materialization

Materialization is explicit. The user runs **Materialize / Create Missing Devices** when ready.

Behavior:

- Use batch tenant, location, status, role, and platform defaults.
- Use selected/planned device type or profile when present.
- Use a configured generic/default device type when a planned device lacks a specific type.
- Create planned devices and planned/generated interfaces where enough information exists.
- Link app planned objects to the created Nautobot objects.
- Do not create Nautobot objects for incomplete or invalid planned devices.
- Return a reviewable exception list for anything not created.

Materialization should be idempotent and safe to rerun.

## Validation

Validation has hard blockers and warnings.

Hard blockers:

- Same interface used twice across open, non-closed matrix rows.
- Interface already has a Nautobot cable.
- Same endpoint on both sides of a row.
- Missing device/interface when attempting cable creation.
- Unresolved planned device/interface when attempting cable creation.

Warnings:

- Unknown device type/profile.
- Free-text interface on unresolved device.
- Unknown SFP compatibility.
- Speed/medium not provably compatible with selected interface/SFP.
- Incomplete stack/module profile.

Backlog rule areas:

- Precise Cisco 9200 module compatibility if source data is missing.
- SFP compatibility by port type/vendor if source data is missing.
- Speed derivation from transceiver/module/device type when source data is incomplete.

Users can keep editing with warnings. Cable execution should block only when Nautobot integrity would be harmed.

## UI Structure

The default batch view should open into the Connectivity Matrix, not import/export controls.

Primary screens:

- **Connectivity Matrix**: grid-first editor with action toolbar.
- **Device / Stack Builder**: planned stack/device/module/interface creation pane.
- **Review / Exceptions**: unresolved devices, validation warnings, duplicate use, cabled interface conflicts, materialization errors.
- **Export**: XLSX export of the online matrix and optional draw.io export/reporting outputs.

The old XLSX import/export may remain temporarily for migration and backup, but it must be visually secondary to the online workflow.

## Implementation Approach

Use a matrix-first workbench approach:

1. Build the real online matrix behavior first.
2. Add planned unresolved device/interface models and serializers.
3. Add explicit materialization.
4. Add row color and swap operations.
5. Add the supporting Device / Stack Builder pane.
6. Keep XLSX export as output/reporting, not workflow entry.

This focuses engineering effort where the value is highest while allowing the final two-pane app structure to appear early.

## Testing Strategy

Model/service tests:

- planned device materialization uses batch defaults and generic fallback correctly
- unresolved devices do not create Nautobot objects on cell save
- available-interface logic excludes cabled interfaces and open-row reservations
- hybrid planned interface suggestions work for known profiles and free text works for unknown profiles
- row swap preserves non-endpoint fields
- row color does not affect validation/execution

API tests:

- grid update for real endpoints
- grid update for planned unresolved endpoints
- materialization endpoint returns created counts and exceptions
- bulk swap and bulk color endpoints
- XLSX export includes row color and current online matrix data

Browser/UI verification:

- keyboard editing, autocomplete, sorting/filtering, drag/drop reorder
- row color and bulk color
- per-row and bulk swap
- materialization review flow
- validation and cable execution guardrails
