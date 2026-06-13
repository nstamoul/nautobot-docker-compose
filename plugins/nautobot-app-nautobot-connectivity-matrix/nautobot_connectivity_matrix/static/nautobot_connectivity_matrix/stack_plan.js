(function () {
  "use strict";

  const configElement = document.getElementById("stack-plan-config");
  if (!configElement) return;

  const config = JSON.parse(configElement.textContent);
  const choices = config.choices || {};
  const defaults = config.defaults || {};
  const apiBaseUrl = config.apiBaseUrl || "/api/plugins/nautobot-connectivity-matrix";

  const csrfToken = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || "";
  const rowId = () => `row-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  function choiceLabel(listName, value) {
    const match = (choices[listName] || []).find((item) => String(item.value) === String(value));
    return match ? match.label : (value || "");
  }

  function choiceValues(listName) {
    return (choices[listName] || []).map((item) => ({ value: item.value, label: item.label }));
  }

  function populateSelect(id, listName, selectedValue) {
    const select = document.getElementById(id);
    if (!select) return;
    select.innerHTML = '<option value=""></option>';
    let items = choices[listName] || [];
    if (listName === "locations") {
      const tenantId = selectedDefault("stack-default-tenant");
      items = items.filter((item) => !tenantId || String(item.tenant) === String(tenantId));
    }
    items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.value;
      option.textContent = item.label;
      if (selectedValue && String(selectedValue) === String(item.value)) option.selected = true;
      select.appendChild(option);
    });
  }

  populateSelect("stack-default-tenant", "tenants");
  populateSelect("stack-default-location", "locations");
  populateSelect("stack-default-status", "statuses", defaults.status);

  function selectedDefault(id) {
    return document.getElementById(id)?.value || "";
  }

  document.getElementById("stack-default-tenant")?.addEventListener("change", function () {
    populateSelect("stack-default-location", "locations");
  });

  function firstRowForStack(table, stackId) {
    return table
      .getData()
      .filter((row) => String(row.stack_id) === String(stackId))
      .sort((a, b) => Number(a.member_position || 0) - Number(b.member_position || 0))[0];
  }

  function isStackHeader(data) {
    return String(data.member_position || "1") === "1";
  }

  function markInherited(cell) {
    cell.getElement().classList.toggle("inherited-cell", !isStackHeader(cell.getRow().getData()));
  }

  function stackHeaderText(cell) {
    const data = cell.getRow().getData();
    return isStackHeader(data) ? `Stack ${data.stack_id}` : "";
  }

  function inheritedChoiceFormatter(listName, fieldName) {
    return function (cell) {
      const data = cell.getRow().getData();
      markInherited(cell);
      if (isStackHeader(data)) return choiceLabel(listName, cell.getValue());
      const header = firstRowForStack(cell.getTable(), data.stack_id);
      return header ? choiceLabel(listName, header[fieldName]) : "";
    };
  }

  function initialRows() {
    return [
      { id: rowId(), stack_id: 1, stack_hostname: "", member_position: 1, device_type: "", module_type: "", role: "", platform: "" },
      { id: rowId(), stack_id: 1, stack_hostname: "", member_position: 2, device_type: "", module_type: "", role: "", platform: "" },
      { id: rowId(), stack_id: 2, stack_hostname: "", member_position: 1, device_type: "", module_type: "", role: "", platform: "" },
      { id: rowId(), stack_id: 2, stack_hostname: "", member_position: 2, device_type: "", module_type: "", role: "", platform: "" },
    ];
  }

  function normalizeStack(table, stackId) {
    const rows = table
      .getRows()
      .filter((row) => String(row.getData().stack_id) === String(stackId));
    rows
      .sort((a, b) => Number(a.getData().member_position || 0) - Number(b.getData().member_position || 0))
      .forEach((row, index) => {
        row.update({ member_position: index + 1 });
      });
  }

  function maxStackId(table) {
    return table.getData().reduce((max, row) => Math.max(max, Number(row.stack_id || 0)), 0);
  }

  const table = new Tabulator("#stack-plan-grid", {
    data: initialRows(),
    height: "620px",
    layout: "fitColumns",
    index: "id",
    selectable: true,
    movableRows: true,
    clipboard: true,
    clipboardPasteParser: "table",
    clipboardPasteAction: "insert",
    filterMode: "local",
    sortMode: "local",
    headerFilterLiveFilter: true,
    headerFilterLiveFilterDelay: 250,
    rowFormatter: function (row) {
      const data = row.getData();
      row.getElement().classList.toggle("stack-band-a", Number(data.stack_id || 0) % 2 === 1);
      row.getElement().classList.toggle("stack-band-b", Number(data.stack_id || 0) % 2 === 0);
    },
    rowMoved: function (row) {
      normalizeStack(table, row.getData().stack_id);
      table.redraw(true);
    },
    columns: [
      { title: "", rowHandle: true, formatter: "handle", headerSort: false, width: 32, hozAlign: "center" },
      {
        title: "",
        formatter: "rowSelection",
        titleFormatter: "rowSelection",
        headerSort: false,
        width: 38,
        hozAlign: "center",
      },
      {
        title: "Stack",
        field: "stack_id",
        width: 105,
        formatter: stackHeaderText,
        headerFilter: "input",
        headerFilterFunc: function (value, _rowValue, data) {
          return String(data.stack_id || "").includes(String(value || ""));
        },
      },
      {
        title: "Hostname",
        field: "stack_hostname",
        editor: "input",
        editable: function (cell) {
          return isStackHeader(cell.getRow().getData());
        },
        minWidth: 180,
        headerFilter: "input",
        formatter: function (cell) {
          markInherited(cell);
          return isStackHeader(cell.getRow().getData()) ? (cell.getValue() || "") : "";
        },
      },
      {
        title: "Member",
        field: "member_position",
        editor: "number",
        width: 95,
        hozAlign: "right",
        headerFilter: "input",
      },
      {
        title: "Device Type",
        field: "device_type",
        editor: "list",
        editorParams: { values: choiceValues("deviceTypes"), autocomplete: true, allowEmpty: true, listOnEmpty: true },
        formatter: (cell) => choiceLabel("deviceTypes", cell.getValue()),
        minWidth: 235,
        headerFilter: "input",
      },
      {
        title: "Uplink Module",
        field: "module_type",
        editor: "list",
        editorParams: { values: choiceValues("moduleTypes"), autocomplete: true, allowEmpty: true, listOnEmpty: true },
        formatter: (cell) => choiceLabel("moduleTypes", cell.getValue()),
        minWidth: 220,
        headerFilter: "input",
      },
      {
        title: "Role",
        field: "role",
        editor: "list",
        editable: function (cell) {
          return isStackHeader(cell.getRow().getData());
        },
        editorParams: { values: choiceValues("roles"), autocomplete: true, allowEmpty: true, listOnEmpty: true },
        formatter: inheritedChoiceFormatter("roles", "role"),
        minWidth: 150,
        headerFilter: "input",
      },
      {
        title: "Platform",
        field: "platform",
        editor: "list",
        editable: function (cell) {
          return isStackHeader(cell.getRow().getData());
        },
        editorParams: { values: choiceValues("platforms"), autocomplete: true, allowEmpty: true, listOnEmpty: true },
        formatter: inheritedChoiceFormatter("platforms", "platform"),
        minWidth: 140,
        headerFilter: "input",
      },
    ],
  });

  table.on("cellEdited", function () {
    table.redraw(true);
  });

  document.getElementById("btn-stack-add")?.addEventListener("click", function () {
    const stackId = maxStackId(table) + 1;
    table.addRow({
      id: rowId(),
      stack_id: stackId,
      stack_hostname: "",
      member_position: 1,
      device_type: "",
      module_type: "",
      role: "",
      platform: "",
    });
  });

  document.getElementById("btn-stack-add-member")?.addEventListener("click", function () {
    const selected = table.getSelectedRows()[0];
    const stackId = selected ? selected.getData().stack_id : maxStackId(table) || 1;
    const data = table.getData();
    const members = data.filter((row) => String(row.stack_id) === String(stackId));
    const selectedData = selected ? selected.getData() : {};
    const header = firstRowForStack(table, stackId) || {};
    const newMember = {
      id: rowId(),
      stack_id: stackId,
      stack_hostname: "",
      member_position: members.length + 1,
      device_type: selectedData.device_type || header.device_type || "",
      module_type: selectedData.module_type || header.module_type || "",
      role: "",
      platform: "",
    };
    const lastStackIndex = data.reduce((last, row, index) => (String(row.stack_id) === String(stackId) ? index : last), -1);
    data.splice(lastStackIndex + 1, 0, newMember);
    let position = 1;
    data.forEach((row) => {
      if (String(row.stack_id) === String(stackId)) {
        row.member_position = position;
        position += 1;
      }
    });
    table.setData(data).then(() => table.redraw(true));
  });

  document.getElementById("btn-stack-delete")?.addEventListener("click", function () {
    const selected = table.getSelectedRows();
    selected.forEach((row) => row.delete());
    table.redraw(true);
  });

  document.getElementById("btn-stack-materialize")?.addEventListener("click", async function () {
    const resultBox = document.getElementById("stack-result");
    resultBox.style.display = "block";
    resultBox.className = "alert alert-info stack-result";
    resultBox.textContent = "Materializing...";

    const payload = {
      defaults: {
        tenant: selectedDefault("stack-default-tenant"),
        location: selectedDefault("stack-default-location"),
        status: selectedDefault("stack-default-status"),
      },
      rows: table.getData().map((row) => {
        return {
          stack_id: row.stack_id,
          stack_hostname: isStackHeader(row) ? row.stack_hostname : "",
          member_position: row.member_position,
          device_type: row.device_type,
          module_type: row.module_type,
          role: isStackHeader(row) ? row.role : "",
          platform: isStackHeader(row) ? row.platform : "",
        };
      }),
    };

    try {
      const response = await fetch(`${apiBaseUrl}/stack-plan/materialize/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Materialize failed");
      const errors = (body.errors || []).map((item) => `Row ${item.row || "-"}: ${item.error}`).join("\n");
      resultBox.className = body.error_rows ? "alert alert-warning stack-result" : "alert alert-success stack-result";
      resultBox.textContent = [
        `Created devices: ${body.created_devices}`,
        `Skipped rows: ${body.skipped_rows}`,
        `Error rows: ${body.error_rows}`,
        errors,
      ].filter(Boolean).join("\n");
    } catch (error) {
      resultBox.className = "alert alert-danger stack-result";
      resultBox.textContent = error.message;
    }
  });
})();
