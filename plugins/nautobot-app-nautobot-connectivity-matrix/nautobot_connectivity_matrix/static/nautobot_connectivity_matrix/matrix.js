/* global Tabulator */

(function () {
  function normalize(value) {
    return (value || "").toString().trim().toLowerCase();
  }

  function containsNeedle(haystack, needle) {
    const n = normalize(needle);
    if (!n) return true;
    return normalize(haystack).includes(n);
  }

  function getCookie(name) {
    const cookies = document.cookie ? document.cookie.split(";") : [];
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === `${name}=`) {
        return decodeURIComponent(cookie.substring(name.length + 1));
      }
    }
    return "";
  }

  function getConfig() {
    const el = document.getElementById("connectivity-matrix-config");
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Failed to parse connectivity-matrix config:", err);
      return null;
    }
  }

  const cfg = getConfig();
  if (!cfg) return;

  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const batchId = cfg.batchId;
  const apiBaseUrl = cfg.apiBaseUrl;
  const csrfToken = getCookie("csrftoken");
  const tenantId = cfg.tenantId;
  const locationId = cfg.locationId;
  const mediumChoices = cfg.mediumChoices || [];
  const speedChoices = cfg.speedChoices || [];
  const deviceStatusChoices = cfg.deviceStatusChoices || [];
  const deviceRoleChoices = cfg.deviceRoleChoices || [];

  const mediumValues = mediumChoices.reduce((acc, c) => {
    acc[c.value] = c.label;
    return acc;
  }, {});

  const speedValues = speedChoices.reduce((acc, c) => {
    acc[c.value] = c.label;
    return acc;
  }, {});

  const interfaceCache = {};
  let deviceCache = null;
  let deviceCacheIndex = null;
  let deviceLabelIndex = null;
  const interfaceLabelIndex = {};

  const STORAGE_KEY = `nautobot_connectivity_matrix:${batchId}:deviceFilters`;

  function getFiltersFromStorage() {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return { statusIds: [], excludeRoleIds: [] };
      const parsed = JSON.parse(raw);
      return {
        statusIds: Array.isArray(parsed.statusIds) ? parsed.statusIds : [],
        excludeRoleIds: Array.isArray(parsed.excludeRoleIds) ? parsed.excludeRoleIds : [],
      };
    } catch (_e) {
      return { statusIds: [], excludeRoleIds: [] };
    }
  }

  function setFiltersToStorage(filters) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
  }

  function resetDeviceCaches() {
    deviceCache = null;
    deviceCacheIndex = null;
    deviceLabelIndex = null;
  }

  function resetInterfaceCaches() {
    Object.keys(interfaceCache).forEach((k) => delete interfaceCache[k]);
  }

  function buildDeviceIndex(devices) {
    const idx = {};
    (devices || []).forEach((d) => {
      if (d && d.value) idx[d.value] = d.label;
    });
    return idx;
  }

  function buildDeviceLabelIndex(devices) {
    const idx = {};
    (devices || []).forEach((d) => {
      if (d && d.label) idx[d.label] = d.value;
    });
    return idx;
  }

  function getSelectedOptions(selectEl) {
    if (!selectEl) return [];
    return Array.from(selectEl.selectedOptions || []).map((o) => o.value).filter(Boolean);
  }

  function populateSelect(selectEl, choices) {
    if (!selectEl) return;
    selectEl.innerHTML = "";
    (choices || []).forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.value;
      opt.textContent = c.label;
      selectEl.appendChild(opt);
    });
  }

  function applyStoredFiltersToUI() {
    const filters = getFiltersFromStorage();
    const statusSelect = document.getElementById("device-status-filter");
    const roleExcludeSelect = document.getElementById("device-role-exclude");
    if (statusSelect) {
      Array.from(statusSelect.options).forEach((o) => {
        // eslint-disable-next-line no-param-reassign
        o.selected = filters.statusIds.includes(o.value);
      });
    }
    if (roleExcludeSelect) {
      Array.from(roleExcludeSelect.options).forEach((o) => {
        // eslint-disable-next-line no-param-reassign
        o.selected = filters.excludeRoleIds.includes(o.value);
      });
    }
  }

  // Build filter UI options.
  populateSelect(document.getElementById("device-status-filter"), deviceStatusChoices);
  populateSelect(document.getElementById("device-role-exclude"), deviceRoleChoices);
  applyStoredFiltersToUI();

  function showLoading() {
    document.getElementById("loading-overlay")?.classList.add("active");
  }

  function hideLoading() {
    document.getElementById("loading-overlay")?.classList.remove("active");
  }

  function interfaceCacheKey(deviceId, planId) {
    return `${deviceId || ""}:${planId || ""}`;
  }

  async function fetchInterfaces(deviceId, planId) {
    if (!deviceId) return [];
    const key = interfaceCacheKey(deviceId, planId);
    if (interfaceCache[key]) return interfaceCache[key];

    try {
      const params = new URLSearchParams();
      params.append("device_id", deviceId);
      params.append("batch_id", batchId);
      if (planId) params.append("plan_id", planId);
      const response = await fetch(`${apiBaseUrl}/available-interfaces/?${params}`, {
        headers: { "X-CSRFToken": csrfToken },
        credentials: "same-origin",
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`available-interfaces failed (${response.status}): ${text.slice(0, 200)}`);
      }
      const data = await response.json();
      if (!Array.isArray(data)) throw new Error("available-interfaces returned non-list JSON");
      data.forEach((item) => {
        if (item && item.label) interfaceLabelIndex[item.label] = item.value;
      });
      interfaceCache[key] = data;
      return data;
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("Failed to fetch interfaces:", e);
      return [];
    }
  }

  async function fetchDevices() {
    if (deviceCache) return deviceCache;
    try {
      const params = new URLSearchParams();
      if (tenantId) params.append("tenant", tenantId);
      if (locationId) params.append("location", locationId);
      params.append("limit", "500");
      const filters = getFiltersFromStorage();
      filters.statusIds.forEach((id) => params.append("status_id", id));
      filters.excludeRoleIds.forEach((id) => params.append("exclude_role_id", id));

      const response = await fetch(`${apiBaseUrl}/available-devices/?${params}`, {
        headers: { "X-CSRFToken": csrfToken },
        credentials: "same-origin",
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`available-devices failed (${response.status}): ${text.slice(0, 200)}`);
      }
      const data = await response.json();
      if (!Array.isArray(data)) throw new Error("available-devices returned non-list JSON");
      deviceCache = data;
      deviceCacheIndex = buildDeviceIndex(data);
      deviceLabelIndex = buildDeviceLabelIndex(data);
      return data;
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("Failed to fetch devices:", e);
      return [];
    }
  }

  function lookupDeviceLabel(deviceId) {
    if (!deviceId) return "";
    if (deviceCacheIndex && deviceCacheIndex[deviceId]) return deviceCacheIndex[deviceId];
    if (deviceCache) {
      deviceCacheIndex = buildDeviceIndex(deviceCache);
      return deviceCacheIndex[deviceId] || "";
    }
    return "";
  }

  function lookupInterfaceLabel(deviceId, interfaceId) {
    if (!deviceId || !interfaceId) return "";
    const keyPrefix = `${deviceId}:`;
    const keys = Object.keys(interfaceCache).filter((k) => k.startsWith(keyPrefix));
    const list = keys.length ? interfaceCache[keys[0]] : [];
    const found = list.find((i) => i.value === interfaceId);
    return found ? found.label : "";
  }

  function resolveDeviceEdit(value) {
    const text = (value || "").toString().trim();
    if (!text) return { id: null, name: "", display: "" };
    if (uuidPattern.test(text)) {
      return { id: text, name: "", display: lookupDeviceLabel(text) || text };
    }
    const id = deviceLabelIndex && deviceLabelIndex[text];
    if (id) return { id, name: "", display: text };
    return { id: null, name: text, display: text };
  }

  function resolveInterfaceEdit(value, deviceId) {
    const text = (value || "").toString().trim();
    if (!text) return { id: null, name: "", display: "" };
    if (uuidPattern.test(text)) {
      return { id: text, name: "", display: lookupInterfaceLabel(deviceId, text) || text };
    }
    const id = interfaceLabelIndex[text];
    if (id) return { id, name: "", display: text };
    return { id: null, name: text, display: text };
  }

  async function patchRow(rowData) {
    if (!rowData || !rowData.id) return null;

    const payload = {
      device_a_id: rowData.device_a_id || null,
      device_a_name: rowData.device_a_name || "",
      interface_a_id: rowData.interface_a_id || null,
      interface_a_name: rowData.interface_a_name || "",
      sfp_a: rowData.sfp_a || "",
      medium: rowData.medium || "RJ45",
      speed: rowData.speed || "1G",
      device_b_id: rowData.device_b_id || null,
      device_b_name: rowData.device_b_name || "",
      interface_b_id: rowData.interface_b_id || null,
      interface_b_name: rowData.interface_b_name || "",
      sfp_b: rowData.sfp_b || "",
      notes: rowData.notes || "",
      row_color: rowData.row_color || "",
    };

    const response = await fetch(`${apiBaseUrl}/plans/${rowData.id}/grid/`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });

    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json() : await response.text();

    if (!response.ok) {
      let msg = `Save failed (${response.status}).`;
      if (typeof data === "string") {
        msg = `${msg} ${data.slice(0, 200)}`;
      } else if (data && typeof data === "object") {
        msg = `${msg} ${JSON.stringify(data)}`;
      }
      throw new Error(msg);
    }

    return data;
  }

  function statusFormatter(cell) {
    const val = cell.getValue();
    return `<span class="status-${val}">${val}</span>`;
  }

  function rowWarningFormatter(cell) {
    const data = cell.getRow().getData();
    const blockers = data.validation_errors || [];
    const warnings = data.validation_warnings || [];
    if (!blockers.length && !warnings.length) return "";
    const icon = blockers.length ? "mdi-alert-circle text-danger" : "mdi-alert text-warning";
    const title = [...blockers, ...warnings].join("\n").replace(/'/g, "&#39;");
    return `<i class="mdi ${icon}" title='${title}'></i>`;
  }

  function rowSwapFormatter() {
    return "<button class='btn btn-sm btn-outline-secondary' title='Swap A/B'><i class='mdi mdi-swap-horizontal'></i></button>";
  }

  async function requestJson(url, options) {
    const response = await fetch(url, {
      ...(options || {}),
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        ...((options && options.headers) || {}),
      },
      credentials: "same-origin",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || data.detail || "Request failed");
    return data;
  }

  function selectedIds() {
    return table.getSelectedData().map((row) => row.id).filter(Boolean);
  }

  async function swapRows(ids) {
    if (!ids.length) {
      alert("No rows selected");
      return;
    }
    showLoading();
    try {
      if (ids.length === 1) {
        await requestJson(`${apiBaseUrl}/plans/${ids[0]}/swap/`, { method: "POST", body: "{}" });
      } else {
        await requestJson(`${apiBaseUrl}/plans/bulk_swap/`, {
          method: "POST",
          body: JSON.stringify({ ids }),
        });
      }
      await table.setData(`${apiBaseUrl}/plans/grid/?batch=${batchId}`);
      resetInterfaceCaches();
    } catch (err) {
      alert(err.message);
    } finally {
      hideLoading();
    }
  }

  async function colorRows(ids, rowColor) {
    if (!ids.length) {
      alert("No rows selected");
      return;
    }
    showLoading();
    try {
      await requestJson(`${apiBaseUrl}/plans/bulk_color/`, {
        method: "POST",
        body: JSON.stringify({ ids, row_color: rowColor }),
      });
      await table.setData(`${apiBaseUrl}/plans/grid/?batch=${batchId}`);
    } catch (err) {
      alert(err.message);
    } finally {
      hideLoading();
    }
  }

  function computeAndPersistRowOrder() {
    const allData = table.getData("all") || [];
    const orderedIds = allData.map((row) => row.id).filter(Boolean);
    if (!orderedIds.length) return;

    // Keep client-side row_order in sync with the current order, so the UI doesn't "snap back".
    orderedIds.forEach((id, idx) => {
      const row = table.getRow(id);
      row?.update({ row_order: idx + 1 });
    });

    fetch(`${apiBaseUrl}/batches/${batchId}/reorder/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      credentials: "same-origin",
      body: JSON.stringify({ ordered_ids: orderedIds }),
    }).catch((err) => {
      // eslint-disable-next-line no-console
      console.error("Failed to persist row order:", err);
    });
  }

  const table = new Tabulator("#matrix-grid", {
    height: "600px",
    layout: "fitColumns",
    responsiveLayout: "collapse",
    placeholder: "No connections defined. Click 'Add Row' to start.",
    selectable: true,
    index: "id",
    filterMode: "local",
    sortMode: "local",
    headerFilterLiveFilter: true,
    headerFilterLiveFilterDelay: 250,
    movableRows: true,
    rowMoved: function () {
      computeAndPersistRowOrder();
    },
    rowFormatter: function (row) {
      const data = row.getData();
      row.getElement().style.backgroundColor = data.row_color || "";
    },
    initialSort: [{ column: "row_order", dir: "asc" }],

    ajaxURL: `${apiBaseUrl}/plans/grid/`,
    ajaxParams: { batch: batchId },
    ajaxConfig: {
      headers: { "X-CSRFToken": csrfToken },
      credentials: "same-origin",
    },

    columns: [
      {
        title: "",
        rowHandle: true,
        formatter: "handle",
        headerSort: false,
        width: 30,
        hozAlign: "center",
      },
      {
        title: "",
        formatter: "rowSelection",
        titleFormatter: "rowSelection",
        hozAlign: "center",
        headerSort: false,
        width: 40,
      },
      {
        title: "",
        formatter: rowSwapFormatter,
        headerSort: false,
        width: 52,
        hozAlign: "center",
        cellClick: function (_e, cell) {
          swapRows([cell.getRow().getData().id]);
        },
      },
      {
        title: "",
        field: "validation_errors",
        formatter: rowWarningFormatter,
        headerSort: false,
        width: 40,
        hozAlign: "center",
      },
      { title: "#", field: "row_order", sorter: "number", width: 70, hozAlign: "right", headerSort: true },
      {
        title: "Device A",
        field: "device_a_id",
        headerSort: true,
        headerFilter: "input",
        headerFilterFunc: function (headerValue, _rowValue, rowData) {
          return containsNeedle(rowData.device_a_display || rowData.device_a_name, headerValue);
        },
        sorter: function (_a, _b, aRow, bRow) {
          const aName = normalize(aRow.getData().device_a_display || aRow.getData().device_a_name);
          const bName = normalize(bRow.getData().device_a_display || bRow.getData().device_a_name);
          return aName.localeCompare(bName);
        },
        formatter: function (cell) {
          const row = cell.getRow().getData();
          if (row.device_a_display) return row.device_a_display;
          if (row.device_a_name) return row.device_a_name;
          return lookupDeviceLabel(cell.getValue()) || "";
        },
        editor: "list",
        editorParams: {
          valuesLookup: async function () {
            const devices = await fetchDevices();
            return devices.map((d) => ({ value: d.value, label: d.label }));
          },
          autocomplete: true,
          allowEmpty: true,
          freetext: true,
          listOnEmpty: true,
        },
        cellEdited: function (cell) {
          const row = cell.getRow();
          const resolved = resolveDeviceEdit(cell.getValue());
          row.update({
            device_a_id: resolved.id,
            device_a_name: resolved.name,
            device_a_display: resolved.display,
            interface_a_display: "",
            interface_a_id: null,
            interface_a_name: "",
          });
          resetInterfaceCaches();
        },
      },
      {
        title: "Interface A",
        field: "interface_a_id",
        headerSort: true,
        headerFilter: "input",
        headerFilterFunc: function (headerValue, _rowValue, rowData) {
          return containsNeedle(rowData.interface_a_display || rowData.interface_a_name, headerValue);
        },
        sorter: function (_a, _b, aRow, bRow) {
          const aName = normalize(aRow.getData().interface_a_display || aRow.getData().interface_a_name);
          const bName = normalize(bRow.getData().interface_a_display || bRow.getData().interface_a_name);
          return aName.localeCompare(bName);
        },
        formatter: function (cell) {
          const row = cell.getRow().getData();
          if (row.interface_a_display) return row.interface_a_display;
          if (row.interface_a_name) return row.interface_a_name;
          return lookupInterfaceLabel(row.device_a_id, cell.getValue()) || "";
        },
        editor: "list",
        editorParams: {
          valuesLookup: async function (cell) {
            const data = cell.getRow().getData();
            const deviceId = data.device_a_id;
            if (!deviceId) return [];
            const interfaces = await fetchInterfaces(deviceId, data.id);
            const used = new Set();
            (table.getData("all") || []).forEach((r) => {
              if (r.interface_a_id) used.add(r.interface_a_id);
              if (r.interface_b_id) used.add(r.interface_b_id);
            });
            const current = data.interface_a_id;
            return interfaces
              .filter((i) => !used.has(i.value) || i.value === current)
              .map((i) => ({ value: i.value, label: i.label }));
          },
          autocomplete: true,
          allowEmpty: true,
          freetext: true,
          listOnEmpty: true,
        },
        cellEdited: function (cell) {
          const rowData = cell.getRow().getData();
          const resolved = resolveInterfaceEdit(cell.getValue(), rowData.device_a_id);
          cell.getRow().update({
            interface_a_id: resolved.id,
            interface_a_name: resolved.name,
            interface_a_display: resolved.display,
          });
          resetInterfaceCaches();
        },
      },
      { title: "SFP A", field: "sfp_a", editor: "input", width: 100, headerSort: true, headerFilter: "input" },
      {
        title: "Medium",
        field: "medium",
        headerSort: true,
        headerFilter: "list",
        headerFilterParams: { values: mediumValues, clearable: true },
        editor: "list",
        editorParams: { values: mediumValues, allowEmpty: false },
        width: 100,
      },
      {
        title: "Speed",
        field: "speed",
        headerSort: true,
        headerFilter: "list",
        headerFilterParams: { values: speedValues, clearable: true },
        editor: "list",
        editorParams: { values: speedValues, allowEmpty: false },
        width: 80,
      },
      {
        title: "Device B",
        field: "device_b_id",
        headerSort: true,
        headerFilter: "input",
        headerFilterFunc: function (headerValue, _rowValue, rowData) {
          return containsNeedle(rowData.device_b_display || rowData.device_b_name, headerValue);
        },
        sorter: function (_a, _b, aRow, bRow) {
          const aName = normalize(aRow.getData().device_b_display || aRow.getData().device_b_name);
          const bName = normalize(bRow.getData().device_b_display || bRow.getData().device_b_name);
          return aName.localeCompare(bName);
        },
        formatter: function (cell) {
          const row = cell.getRow().getData();
          if (row.device_b_display) return row.device_b_display;
          if (row.device_b_name) return row.device_b_name;
          return lookupDeviceLabel(cell.getValue()) || "";
        },
        editor: "list",
        editorParams: {
          valuesLookup: async function () {
            const devices = await fetchDevices();
            return devices.map((d) => ({ value: d.value, label: d.label }));
          },
          autocomplete: true,
          allowEmpty: true,
          freetext: true,
          listOnEmpty: true,
        },
        cellEdited: function (cell) {
          const row = cell.getRow();
          const resolved = resolveDeviceEdit(cell.getValue());
          row.update({
            device_b_id: resolved.id,
            device_b_name: resolved.name,
            device_b_display: resolved.display,
            interface_b_display: "",
            interface_b_id: null,
            interface_b_name: "",
          });
          resetInterfaceCaches();
        },
      },
      {
        title: "Interface B",
        field: "interface_b_id",
        headerSort: true,
        headerFilter: "input",
        headerFilterFunc: function (headerValue, _rowValue, rowData) {
          return containsNeedle(rowData.interface_b_display || rowData.interface_b_name, headerValue);
        },
        sorter: function (_a, _b, aRow, bRow) {
          const aName = normalize(aRow.getData().interface_b_display || aRow.getData().interface_b_name);
          const bName = normalize(bRow.getData().interface_b_display || bRow.getData().interface_b_name);
          return aName.localeCompare(bName);
        },
        formatter: function (cell) {
          const row = cell.getRow().getData();
          if (row.interface_b_display) return row.interface_b_display;
          if (row.interface_b_name) return row.interface_b_name;
          return lookupInterfaceLabel(row.device_b_id, cell.getValue()) || "";
        },
        editor: "list",
        editorParams: {
          valuesLookup: async function (cell) {
            const data = cell.getRow().getData();
            const deviceId = data.device_b_id;
            if (!deviceId) return [];
            const interfaces = await fetchInterfaces(deviceId, data.id);
            const used = new Set();
            (table.getData("all") || []).forEach((r) => {
              if (r.interface_a_id) used.add(r.interface_a_id);
              if (r.interface_b_id) used.add(r.interface_b_id);
            });
            const current = data.interface_b_id;
            return interfaces
              .filter((i) => !used.has(i.value) || i.value === current)
              .map((i) => ({ value: i.value, label: i.label }));
          },
          autocomplete: true,
          allowEmpty: true,
          freetext: true,
          listOnEmpty: true,
        },
        cellEdited: function (cell) {
          const rowData = cell.getRow().getData();
          const resolved = resolveInterfaceEdit(cell.getValue(), rowData.device_b_id);
          cell.getRow().update({
            interface_b_id: resolved.id,
            interface_b_name: resolved.name,
            interface_b_display: resolved.display,
          });
          resetInterfaceCaches();
        },
      },
      { title: "SFP B", field: "sfp_b", editor: "input", width: 100, headerSort: true, headerFilter: "input" },
      {
        title: "Status",
        field: "status",
        formatter: statusFormatter,
        width: 100,
        editor: false,
        headerSort: true,
        headerFilter: "list",
        headerFilterParams: {
          values: {
            draft: "draft",
            validated: "validated",
            approved: "approved",
            executed: "executed",
            conflict: "conflict",
            failed: "failed",
          },
          clearable: true,
        },
      },
      { title: "Notes", field: "notes", editor: "input", minWidth: 180, headerSort: true, headerFilter: "input" },
    ],

    cellEdited: function (cell) {
      const rowData = cell.getRow().getData();
      if (!rowData.id) return;

      showLoading();
      patchRow(rowData)
        .then((data) => {
          cell.getRow().update(data);
          hideLoading();
        })
        .catch((err) => {
          // eslint-disable-next-line no-console
          console.error("Save failed:", err);
          hideLoading();
          alert(err.message || "Failed to save changes");
          table.setData(`${apiBaseUrl}/plans/grid/?batch=${batchId}`);
        });
    },
  });

  document.getElementById("btn-apply-device-filters")?.addEventListener("click", function () {
    const statusIds = getSelectedOptions(document.getElementById("device-status-filter"));
    const excludeRoleIds = getSelectedOptions(document.getElementById("device-role-exclude"));
    setFiltersToStorage({ statusIds, excludeRoleIds });
    resetDeviceCaches();
    resetInterfaceCaches();
    alert("Device filters applied. Device dropdowns will update next time you open them.");
  });

  document.getElementById("btn-reset-device-filters")?.addEventListener("click", function () {
    setFiltersToStorage({ statusIds: [], excludeRoleIds: [] });
    applyStoredFiltersToUI();
    resetDeviceCaches();
    resetInterfaceCaches();
    alert("Device filters reset.");
  });

  async function bulkApplyToSelected(clearValue) {
    const activeCell = table.getActiveCell && table.getActiveCell();
    if (!activeCell) {
      alert("Click a cell first (the column/value you want to apply).");
      return;
    }
    const field = activeCell.getColumn().getField();
    if (!field) {
      alert("Cannot determine the active column.");
      return;
    }

    // Only allow bulk actions on a safe subset of columns.
    const allowedFields = new Set([
      "device_a_id",
      "device_b_id",
      "medium",
      "speed",
      "sfp_a",
      "sfp_b",
      "status",
    ]);
    if (!allowedFields.has(field)) {
      alert("Bulk apply is only supported for Device/Medium/Speed/SFP/Status columns (not interfaces).");
      return;
    }

    const selectedRows = table.getSelectedRows();
    if (!selectedRows || selectedRows.length === 0) {
      alert("Select rows using the checkboxes first.");
      return;
    }

    const value = clearValue ? null : activeCell.getValue();
    if (!clearValue && (value === null || value === undefined || value === "")) {
      alert("Active cell has no value to fill.");
      return;
    }

    const updates = selectedRows.map((row) => {
      const data = row.getData();
      const patch = {};

      if (field === "device_a_id") {
        patch.device_a_id = value;
        patch.interface_a_id = null;
        patch.interface_a_name = "";
        patch.interface_a_display = "";
      } else if (field === "device_b_id") {
        patch.device_b_id = value;
        patch.interface_b_id = null;
        patch.interface_b_name = "";
        patch.interface_b_display = "";
      } else if (field === "sfp_a") {
        patch.sfp_a = clearValue ? "" : value;
      } else if (field === "sfp_b") {
        patch.sfp_b = clearValue ? "" : value;
      } else if (field === "medium") {
        patch.medium = clearValue ? "RJ45" : value;
      } else if (field === "speed") {
        patch.speed = clearValue ? "1G" : value;
      } else if (field === "status") {
        patch.status = clearValue ? "draft" : value;
      }

      row.update(patch);
      return patchRow({ ...data, ...patch })
        .then((serverData) => row.update(serverData))
        .catch((err) => {
          // eslint-disable-next-line no-console
          console.error("Bulk save failed:", err);
          throw err;
        });
    });

    showLoading();
    Promise.allSettled(updates)
      .then((results) => {
        const failed = results.filter((r) => r.status === "rejected");
        if (failed.length) {
          alert(`Bulk update completed with ${failed.length} failures. See console for details.`);
        }
        table.setData(`${apiBaseUrl}/plans/grid/?batch=${batchId}`);
      })
      .finally(() => hideLoading());
  }

  document.getElementById("btn-fill-selected")?.addEventListener("click", function () {
    bulkApplyToSelected(false);
  });

  document.getElementById("btn-clear-selected")?.addEventListener("click", function () {
    bulkApplyToSelected(true);
  });

  document.getElementById("btn-swap-selected")?.addEventListener("click", function () {
    swapRows(selectedIds());
  });

  document.getElementById("btn-color-selected")?.addEventListener("click", function () {
    colorRows(selectedIds(), document.getElementById("row-color-picker")?.value || "");
  });

  document.getElementById("btn-clear-color")?.addEventListener("click", function () {
    colorRows(selectedIds(), "");
  });

  document.getElementById("btn-materialize")?.addEventListener("click", function () {
    // eslint-disable-next-line no-alert
    if (!confirm("Create missing devices and named interfaces from unresolved matrix rows?")) return;
    const output = document.getElementById("materialize-result");
    showLoading();
    requestJson(`${apiBaseUrl}/batches/${batchId}/materialize-missing-devices/`, { method: "POST", body: "{}" })
      .then((data) => {
        if (output) {
          output.className = "alert alert-success materialize-result";
          output.textContent = [
            `Created devices: ${data.created_devices.length ? data.created_devices.join(", ") : "-"}`,
            `Reused devices: ${data.reused_devices.length ? data.reused_devices.join(", ") : "-"}`,
            `Created interfaces: ${data.created_interfaces.length ? data.created_interfaces.join(", ") : "-"}`,
          ].join("\n");
        }
        table.setData(`${apiBaseUrl}/plans/grid/?batch=${batchId}`);
      })
      .catch((err) => {
        if (output) {
          output.className = "alert alert-danger materialize-result";
          output.textContent = err.message;
        } else {
          alert(err.message);
        }
      })
      .finally(() => hideLoading());
  });

  document.getElementById("btn-add-row")?.addEventListener("click", function () {
    showLoading();
    fetch(`${apiBaseUrl}/plans/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      credentials: "same-origin",
      body: JSON.stringify({ batch: batchId, medium: "RJ45", speed: "1G", status: "draft" }),
    })
      .then((response) => response.json())
      .then((created) => {
        // Avoid reloading the entire grid (which can discard unsaved edits).
        const row = {
          id: created.id,
          row_order: created.row_order,
          device_a_id: null,
          device_a_name: created.device_a_name || "",
          device_a_display: created.device_a_display || "",
          interface_a_id: null,
          interface_a_name: created.interface_a_name || "",
          interface_a_display: created.interface_a_display || "",
          sfp_a: created.sfp_a || "",
          medium: created.medium || "RJ45",
          speed: created.speed || "1G",
          device_b_id: null,
          device_b_name: created.device_b_name || "",
          device_b_display: created.device_b_display || "",
          interface_b_id: null,
          interface_b_name: created.interface_b_name || "",
          interface_b_display: created.interface_b_display || "",
          sfp_b: created.sfp_b || "",
          notes: created.notes || "",
          status: created.status || "draft",
          validation_errors: created.validation_errors || [],
          validation_warnings: created.validation_warnings || [],
          row_color: created.row_color || "",
        };

        table.addRow(row);
        hideLoading();
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error("Failed to add row:", err);
        hideLoading();
        alert("Failed to add row");
      });
  });

  document.getElementById("btn-validate")?.addEventListener("click", function () {
    showLoading();
    fetch(`${apiBaseUrl}/batches/${batchId}/validate/`, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      credentials: "same-origin",
    })
      .then((response) => response.json())
      .then((data) => {
        alert(`Validated: ${data.success_count} success, ${data.error_count} errors`);
        table.setData(`${apiBaseUrl}/plans/grid/?batch=${batchId}`);
        hideLoading();
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error("Validation failed:", err);
        hideLoading();
        alert("Validation failed");
      });
  });

  document.getElementById("btn-approve")?.addEventListener("click", function () {
    showLoading();
    fetch(`${apiBaseUrl}/batches/${batchId}/approve_all/`, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      credentials: "same-origin",
    })
      .then((response) => response.json())
      .then((data) => {
        alert(`Approved ${data.approved_count} connections`);
        table.setData(`${apiBaseUrl}/plans/grid/?batch=${batchId}`);
        hideLoading();
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error("Approve failed:", err);
        hideLoading();
        alert("Approve failed");
      });
  });

  document.getElementById("btn-execute")?.addEventListener("click", function () {
    // eslint-disable-next-line no-alert
    if (!confirm("This will create cables in Nautobot. Continue?")) return;
    showLoading();
    fetch(`${apiBaseUrl}/batches/${batchId}/execute/`, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      credentials: "same-origin",
    })
      .then((response) => response.json())
      .then((data) => {
        alert(`Created ${data.success_count} cables, ${data.error_count} errors`);
        table.setData(`${apiBaseUrl}/plans/grid/?batch=${batchId}`);
        hideLoading();
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error("Execute failed:", err);
        hideLoading();
        alert("Execute failed");
      });
  });

  document.getElementById("btn-delete-selected")?.addEventListener("click", function () {
    const selected = table.getSelectedData();
    if (selected.length === 0) {
      alert("No rows selected");
      return;
    }

    // eslint-disable-next-line no-alert
    if (!confirm(`Delete ${selected.length} selected rows?`)) return;

    showLoading();
    const deletePromises = selected.map((row) =>
      fetch(`${apiBaseUrl}/plans/${row.id}/`, {
        method: "DELETE",
        headers: { "X-CSRFToken": csrfToken },
        credentials: "same-origin",
      })
    );

    Promise.all(deletePromises)
      .then(() => {
        table.setData(`${apiBaseUrl}/plans/grid/?batch=${batchId}`);
        hideLoading();
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error("Delete failed:", err);
        hideLoading();
        alert("Delete failed");
      });
  });

  document.getElementById("btn-import-xlsx")?.addEventListener("click", function () {
    document.getElementById("import-xlsx-file")?.click();
  });

  document.getElementById("import-xlsx-file")?.addEventListener("change", function (evt) {
    const file = evt.target.files && evt.target.files[0];
    if (!file) return;

    // eslint-disable-next-line no-alert
    const replaceExisting = confirm("Replace existing rows with the contents of this XLSX?");
    const formData = new FormData();
    formData.append("file", file);
    if (replaceExisting) formData.append("replace", "true");

    showLoading();
    fetch(`${apiBaseUrl}/batches/${batchId}/import-xlsx/`, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      credentials: "same-origin",
      body: formData,
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          alert(`Import failed: ${data.error}`);
        } else {
          alert(`Imported ${data.created_count} rows (skipped ${data.skipped_count}, errors ${data.error_count}).`);
        }
        table.setData(`${apiBaseUrl}/plans/grid/?batch=${batchId}`);
        hideLoading();
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error("Import failed:", err);
        hideLoading();
        alert("Import failed");
      })
      .finally(() => {
        // eslint-disable-next-line no-param-reassign
        evt.target.value = "";
      });
  });
})();
