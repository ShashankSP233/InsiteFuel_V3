"use strict";
const $ = (id) => document.getElementById(id),
  today = () => new Date().toISOString().slice(0, 10),
  n = (v) => Number(v || 0),
  f = (v) =>
    v == null
      ? "—"
      : n(v).toLocaleString(undefined, { maximumFractionDigits: 3 });
let me,
  projects = [],
  vessels = [],
  equipment = [],
  activeShift;
const token = () => sessionStorage.getItem("insitefuel.session");
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
function message(text, type = "info") {
  $("globalMsg").innerHTML =
    `<div class="note note-${type === "error" ? "err" : type === "success" ? "ok" : type === "warn" ? "warn" : ""}">${esc(text)}</div>`;
}


async function api(path, options = {}) {
  const headers = {
    ...(options.body instanceof FormData
      ? {}
      : { "Content-Type": "application/json" }),
    ...(options.headers || {}),
  };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  const r = await fetch(path, { ...options, headers });
  if (r.status === 401) {
    sessionStorage.removeItem("insitefuel.session");
    showLogin();
    throw Error("Session expired. Please sign in again.");
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) throw Error(data?.detail || data?.message || "Request failed");
  return data;
}

function formatDateTime(value) {
  if (!value) return "-";

  const d = new Date(value);

  if (Number.isNaN(d.getTime())) {
    return value;
  }

  return d.toLocaleString();
}


function fmt(value) {
  const n = Number(value ?? 0);

  if (!Number.isFinite(n)) {
    return "0.000";
  }

  return n.toFixed(3);
}

function formatDateTime(value) {
  if (!value) return "-";

  const d = new Date(value);

  if (Number.isNaN(d.getTime())) {
    return value;
  }

  return d.toLocaleString();
}

function select(id, rows, label = "name", blank = false) {
  const el = $(id);
  if (!el) return;
  el.innerHTML =
    (blank ? '<option value="">All vessels</option>' : "") +
    rows
      .filter((x) => x.is_active !== false)
      .map((x) => `<option value="${x.id}">${esc(x[label])}</option>`)
      .join("");
}
function params(data) {
  const q = new URLSearchParams();
  Object.entries(data).forEach(([k, v]) => {
    if (v !== "" && v != null) q.append(k, v);
  });
  return q.toString();
}
function table(id, heads, rows) {
  $(id).innerHTML =
    `<table><thead><tr>${heads.map((x) => `<th>${x}</th>`).join("")}</tr></thead><tbody>${rows.length ? rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${heads.length}" class="muted">No records.</td></tr>`}</tbody></table>`;
}
async function login() {
  try {
    const r = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("loginUser").value,
        password: $("loginPass").value,
      }),
    });
    sessionStorage.setItem("insitefuel.session", r.session_token);
    await init();
  } catch (e) {
    $("loginMsg").textContent = e.message;
  }
}
function showLogin() {
  $("appWrap").classList.add("hidden");
  $("loginWrap").classList.remove("hidden");
}
async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } finally {
    sessionStorage.removeItem("insitefuel.session");
    showLogin();
  }
}
async function init() {
  me = await api("/api/auth/me");
  $("loginWrap").classList.add("hidden");
  $("appWrap").classList.remove("hidden");
  $("userChip").textContent = `${me.full_name || me.username} · ${me.role}`;
  document.querySelectorAll(".admin-only").forEach((x) => {
    x.style.display = me.role === "ADMIN" ? "" : "none";
  });

  document.querySelectorAll(".manager-only").forEach((x) => {
    x.style.display = ["MANAGER", "ADMIN"].includes(me.role) ? "" : "none";
  });

  document.querySelectorAll(".management-only").forEach((x) => {
    x.style.display = ["MANAGER", "ADMIN"].includes(me.role) ? "" : "none";
  });
  await loadMaster();
  ["shiftDate", "productionDate", "soundingDate", "dashTo"].forEach(
    (id) => ($(id).value = today()),
  );
  $("dashFrom").value = new Date(Date.now() - 29 * 864e5)
    .toISOString()
    .slice(0, 10);
  await refreshShiftEquipment();
  await loadDashboard();
}

function toggleManualFuelSource() {
  const selectEl = $("receiptSourceSelect");
  const wrap = $("manualFuelSourceWrap");
  const manual = $("receiptSourceManual");

  const isManual = selectEl.value === "__MANUAL__";

  wrap.classList.toggle("hidden", !isManual);

  if (!isManual) {
    manual.value = "";
  }
}

function populateFuelSources() {
  const el = $("receiptSourceSelect");
  if (!el) return;

  el.innerHTML =
    `<option value="">Select source</option>` +
    vessels
      .filter((v) => v.is_active !== false)
      .map(
        (v) =>
          `<option value="vessel:${v.id}">
            ${esc(v.name)}
          </option>`
      )
      .join("") +
    `<option value="__MANUAL__">Other / Manual</option>`;
}

async function loadMaster() {
  [projects, vessels, equipment] = await Promise.all([
    api("/api/projects"),
    api("/api/vessels"),
    api("/api/equipment"),
  ]);
  select("shiftVessel", vessels);
  select("transferFrom", vessels);
  select("transferTo", vessels);
  populateFuelSources();
  select("productionVessel", vessels);
  select("soundingVessel", vessels);
  select("dashVessel", vessels, "name", true);
  select("productionProject", projects);
  renderMasters();
}
async function refreshShiftEquipment() {
  const v = $("shiftVessel").value;
  select(
    "engineEquipment",
    equipment.filter((x) => String(x.vessel_id) === String(v)),
  );
  activeShift = undefined;
  $("shiftReport").innerHTML = "";
  $("shiftState").textContent = "Select a shift, then open or load it.";
}
async function openShift() {
  try {
    const body = {
      vessel_id: n($("shiftVessel").value),
      shift_date: $("shiftDate").value,
      shift_name: $("shiftName").value,
    };
    let s;
    try {
      s = await api(`/api/fuel/shift?${params(body)}`);
    } catch (e) {
      s = await api("/api/fuel/shift/open", {
        method: "POST",
        body: JSON.stringify(body),
      });
    }
    activeShift = s;
    $("openingFuel").value = s.opening_fuel;
    $("shiftState").textContent =
      `Shift #${s.id} · ${s.status} · opening ${f(s.opening_fuel)} L`;

    await loadShiftReport();
    await loadShiftAttachments();

  } catch (e) {
    message(e.message, "error");
  }
}
async function establishInitialOpening() {
  try {
    if (me.role === "OPERATOR")
      throw Error(
        "Only a manager or administrator may establish an initial opening.",
      );
    const s = await api("/api/fuel/shift/initial-opening", {
      method: "POST",
      body: JSON.stringify({
        vessel_id: n($("shiftVessel").value),
        shift_date: $("shiftDate").value,
        opening_fuel: n($("openingFuel").value),
      }),
    });
    activeShift = s;
    message(`Initial opening created for shift #${s.id}.`, "success");

    await loadShiftReport();
    await loadShiftAttachments();
  } catch (e) {
    message(e.message, "error");
  }
}
async function refreshShiftEquipment() {
  const v = $("shiftVessel").value;

  select(
    "engineEquipment",
    equipment.filter((x) => String(x.vessel_id) === String(v)),
  );

  activeShift = undefined;
  $("shiftReport").innerHTML = "";
  $("attachmentList").innerHTML = "";
  $("shiftState").textContent = "Select a shift, then open or load it.";
}
async function loadShiftReport() {
  try {
    if (!activeShift) return;

    const r = await api(`/api/fuel/shift/${activeShift.id}/report`);
    activeShift = r.shift;

    const b = r.balance;
    const transactions = r.transactions || [];

    table(
      "shiftReport",
      [
        "Opening",
        "Received",
        "Transfer in",
        "Engine use",
        "Transfer out",
        "Adjustments",
        "Closing",
      ],
      [
        [
          f(b.opening_fuel),
          f(b.received_fuel),
          f(b.transfer_in),
          f(b.engine_consumption),
          f(b.transfer_out),
          `${f(b.adjustment_in)} / ${f(b.adjustment_out)}`,
          f(b.closing_fuel),
        ],
      ],
    );

    $("shiftState").textContent =
      `Shift #${activeShift.id} · ${activeShift.status} · calculated closing ${f(b.closing_fuel)} L`;

    const eventRows = transactions.map((t) => {
      let details = "-";

      if (
        t.transaction_type === "ENGINE_CONSUMPTION" &&
        t.reference_type === "ENGINE_EVENT"
      ) {
        details = `Engine Event #${t.reference_id}`;
      } else if (t.transaction_type === "RECEIPT") {
        details = t.fuel_source || "Fuel Receipt";
      } else if (t.transaction_type === "TRANSFER_IN") {
        details = "Transfer In";
      } else if (t.transaction_type === "TRANSFER_OUT") {
        details = "Transfer Out";
      } else if (t.transaction_type === "ADJUSTMENT") {
        details =
          t.adjustment_direction === "IN"
            ? "Adjustment In"
            : "Adjustment Out";
      }

      const type = String(t.transaction_type || "")
        .replaceAll("_", " ");

      return [
        formatDateTime(t.transaction_date),
        type,
        details,
        `${f(t.quantity)} L`,
        esc(t.remarks || "-"),
      ];
    });

    table(
      "shiftEvents",
      ["Time", "Type", "Details", "Quantity", "Remarks"],
      eventRows,
    );
  } catch (e) {
    message(e.message, "error");
  }
}
async function addReceipt() {
  try {
    if (!activeShift) {
      throw Error("Open or load a shift first.");
    }

    const source = $("receiptSourceSelect").value;

    if (!source) {
      throw Error("Select where the fuel was received from.");
    }

    let fuelSource = null;
    let sourceVesselId = null;

    if (source === "__MANUAL__") {
      fuelSource = $("receiptSourceManual").value.trim();

      if (!fuelSource) {
        throw Error("Enter the manual fuel source.");
      }
    } else if (source.startsWith("vessel:")) {
      sourceVesselId = Number(source.split(":")[1]);

      const vessel = vessels.find(
        (v) => Number(v.id) === sourceVesselId
      );

      fuelSource = vessel?.name || null;
    }

    const quantity = n($("receiptQty").value);

    if (quantity <= 0) {
      throw Error("Fuel received quantity must be greater than zero.");
    }

    await api("/api/fuel/receipt", {
      method: "POST",
      body: JSON.stringify({
        vessel_id: activeShift.vessel_id,
        shift_date: activeShift.shift_date,
        shift_name: activeShift.shift_name,
        transaction_type: "RECEIPT",
        quantity,
        fuel_source: fuelSource,
        source_vessel_id: sourceVesselId,
        remarks: $("receiptRemarks").value.trim() || null,
      }),
    });

    message("Fuel received recorded.", "success");

    $("receiptQty").value = "";
    $("receiptRemarks").value = "";
    $("receiptSourceSelect").value = "";
    $("receiptSourceManual").value = "";
    toggleManualFuelSource();

    await loadShiftReport();

  } catch (e) {
    message(e.message, "error");
  }
}
async function addEngine() {
  try {
    if (!activeShift) {
      throw Error("Open or load a shift first.");
    }

    const startValue = $("engineStart").value;
    const stopValue = $("engineStop").value;
    const consumption = n($("engineConsumption").value);

    if (!startValue || !stopValue) {
      throw Error("Enter both engine start and stop times.");
    }

    if (consumption <= 0) {
      throw Error("Engine consumption must be greater than zero.");
    }

    const start = new Date(startValue);
    const stop = new Date(stopValue);

    if (Number.isNaN(start.getTime()) || Number.isNaN(stop.getTime())) {
      throw Error("Invalid engine start or stop time.");
    }

    if (stop <= start) {
      throw Error("Engine stop time must be after start time.");
    }

    const hours = (stop - start) / 3600000;

    if (hours <= 0) {
      throw Error("Engine duration must be greater than zero.");
    }

    const lph = consumption / hours;

    await api("/api/engine/event", {
      method: "POST",
      body: JSON.stringify({
        equipment_id: n($("engineEquipment").value),
        shift_id: activeShift.id,
        start_time: start.toISOString(),
        stop_time: stop.toISOString(),
        lph_rate: Number(lph.toFixed(3)),
        remarks: $("engineRemarks").value.trim() || null,
      }),
    });

    message(
      `Engine event recorded: ${f(consumption)} L over ${hours.toFixed(2)} hours (${lph.toFixed(2)} L/hr).`,
      "success"
    );

    $("engineStart").value = "";
    $("engineStop").value = "";
    $("engineConsumption").value = "";
    $("engineLphCalculated").value = "";
    $("engineRemarks").value = "";

    $("engineCalculation").classList.add("hidden");

    await loadShiftReport();

  } catch (e) {
    message(e.message, "error");
  }
}

function calculateEngineRate() {
  const startValue = $("engineStart").value;
  const stopValue = $("engineStop").value;
  const consumption = n($("engineConsumption").value);

  const display = $("engineCalculation");
  const lphField = $("engineLphCalculated");

  if (!startValue || !stopValue || consumption <= 0) {
    lphField.value = "";
    display.classList.add("hidden");
    return;
  }

  const start = new Date(startValue);
  const stop = new Date(stopValue);

  if (
    Number.isNaN(start.getTime()) ||
    Number.isNaN(stop.getTime()) ||
    stop <= start
  ) {
    lphField.value = "";
    display.classList.add("hidden");
    return;
  }

  const hours = (stop - start) / 3600000;
  const lph = consumption / hours;

  lphField.value = lph.toFixed(3);

  display.textContent =
    `Calculated ${hours.toFixed(2)} hours × ${lph.toFixed(2)} L/hr = ${f(consumption)} L`;

  display.classList.remove("hidden");
}

async function closeShift() {
  try {
    if (!activeShift) throw Error("Open or load a shift first.");
    await api(`/api/fuel/shift/${activeShift.id}/close`, { method: "POST" });
    message("Shift closed.", "success");
    await loadShiftReport();
  } catch (e) {
    message(e.message, "error");
  }
}
async function createTransfer() {
  try {
    const r = await api("/api/transfers", {
      method: "POST",
      body: JSON.stringify({
        from_vessel_id: n($("transferFrom").value),
        from_shift_id: n($("transferFromShift").value),
        to_vessel_id: n($("transferTo").value),
        to_shift_id: n($("transferToShift").value),
        initiated_quantity: n($("transferQty").value),
        notes: $("transferNotes").value || null,
      }),
    });
    message(`Transfer #${r.id} initiated.`, "success");
    await loadTransfers();
  } catch (e) {
    message(e.message, "error");
  }
}
async function transferAction(id, action) {
  try {
    let body = {};
    if (action === "receive") {
      const qty = prompt("Received quantity (L):");
      if (qty == null) return;
      body = { received_quantity: n(qty) };
    }
    if (action === "approve" || action === "reject")
      body = { manager_remark: prompt("Manager remark:") || "" };
    await api(`/api/transfers/${id}/${action}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    await loadTransfers();
  } catch (e) {
    message(e.message, "error");
  }
}
async function loadTransfers() {
  const rows = await api("/api/transfers");
  table(
    "transferList",
    ["ID", "From", "To", "Initiated", "Received", "Loss", "Status", "Actions"],
    rows.map((x) => [
      x.id,
      x.from_vessel_id,
      x.to_vessel_id,
      f(x.initiated_quantity),
      f(x.received_quantity),
      f(x.loss_quantity),
      esc(x.status),
      `${x.status === "INITIATED" ? `<button class="btn btn-sm" onclick="transferAction(${x.id},'receive')">Receive</button>` : ""} ${x.status === "RECEIVED" ? `<button class="btn btn-sm" onclick="transferAction(${x.id},'submit-review')">Submit</button>` : ""} ${["SUBMITTED_FOR_REVIEW", "PENDING_REVIEW"].includes(x.status) && me.role !== "OPERATOR" ? `<button class="btn btn-sm" onclick="transferAction(${x.id},'approve')">Approve</button> <button class="btn btn-sm" onclick="transferAction(${x.id},'reject')">Reject</button>` : ""}`,
    ]),
  );
}
async function saveProduction() {
  try {
    const r = await api("/api/production", {
      method: "POST",
      body: JSON.stringify({
        project_id: n($("productionProject").value),
        vessel_id: n($("productionVessel").value),
        shift_id: n($("productionShift").value),
        production_date: $("productionDate").value,
        as_per_qty: n($("productionAs").value),
        true_qty: n($("productionTrue").value),
        fuel_rate:
          $("productionRate").value === ""
            ? null
            : n($("productionRate").value),
        remarks: $("productionRemarks").value || null,
      }),
    });
    message(`Production saved; variance ${f(r.quantity_variance)}.`, "success");
    await loadProduction();
  } catch (e) {
    message(e.message, "error");
  }
}
async function loadProduction() {
  const rows = await api("/api/production");
  table(
    "productionList",
    ["ID", "Date", "Project", "Vessel", "Shift", "As-per", "True", "Fuel rate"],
    rows.map((x) => [
      x.id,
      x.production_date,
      x.project_id,
      x.vessel_id,
      x.shift_id,
      f(x.as_per_qty),
      f(x.true_qty),
      f(x.fuel_rate),
    ]),
  );
}
async function uploadSounding() {
  try {
    const file = $("soundingFile").files[0];
    if (!file) throw Error("Choose a photo or document first.");
    const data = new FormData();
    data.append("file", file);
    const attachment = await api("/api/attachments/upload", {
      method: "POST",
      body: data,
    });
    await api(
      `/api/soundings?${params({ vessel_id: $("soundingVessel").value, report_date: $("soundingDate").value, attachment_id: attachment.id })}`,
      { method: "POST" },
    );
    message("Sounding uploaded and submitted.", "success");
    await loadSoundings();
  } catch (e) {
    message(e.message, "error");
  }
}
async function uploadShiftAttachment(type) {
  try {
    if (!activeShift) {
      throw Error("Open or load a shift first.");
    }

    const inputMap = {
      bill: "billFile",
      transfer_note: "transferNoteFile",
      sounding: "soundingFile",
    };

    const typeMap = {
      bill: "BILL",
      transfer_note: "TRANSFER_NOTE",
      sounding: "SOUNDING",
    };

    const input = $(inputMap[type]);

    if (!input || !input.files[0]) {
      throw Error("Choose a file first.");
    }

    const file = input.files[0];

    // Step 1: upload the physical file
    const data = new FormData();
    data.append("file", file);

    const attachment = await api("/api/attachments/upload", {
      method: "POST",
      body: data,
    });

    // Step 2: associate the uploaded file with this shift
    await api(`/api/shifts/${activeShift.id}/attachments`, {
      method: "POST",
      body: JSON.stringify({
        attachment_id: attachment.id,
        attachment_type: typeMap[type],
      }),
    });

    message(
      `${type.replace("_", " ")} attachment uploaded successfully.`,
      "success"
    );

    input.value = "";

    // Step 3: refresh the attachment list
    await loadShiftAttachments();

  } catch (e) {
    message(e.message, "error");
  }
}

async function loadShiftAttachments() {
  const list = $("attachmentList");

  if (!list) return;

  if (!activeShift) {
    list.innerHTML = "<div class=\"muted\">Open a shift to view attachments.</div>";
    return;
  }

  try {
    const attachments = await api(
      `/api/shifts/${activeShift.id}/attachments`
    );

    if (!attachments.length) {
      list.innerHTML = "<div class=\"muted\">No attachments yet.</div>";
      return;
    }

    list.innerHTML = attachments.map((item) => `
      <div class="attachment-item">
        <div>
          <strong>${item.attachment_type}</strong>
          <div>${item.original_filename}</div>
        </div>

        <a
          href="/api/attachments/${item.attachment_id}/download"
          target="_blank"
          rel="noopener"
        >
          View
        </a>
      </div>
    `).join("");

  } catch (e) {
    list.innerHTML = `<div class="error">${e.message}</div>`;
  }
}
async function loadSoundings() {
  const d = $("soundingDate").value;
  const [missing, status] = await Promise.all([
    api(`/api/dashboard/missing-soundings?report_date=${d}`),
    api(
      `/api/soundings/status?vessel_id=${$("soundingVessel").value}&report_date=${d}`,
    ),
  ]);
  $("soundingStatus").textContent =
    `Selected vessel: ${status.status} (${status.sounding_count} attachment(s)).`;
  table(
    "missingList",
    ["Vessel", "Date", "Status", "Deadline"],
    missing.map((x) => [
      esc(x.vessel_name),
      x.report_date,
      esc(x.status),
      new Date(x.deadline).toLocaleString(),
    ]),
  );
}
function dashQuery() {
  return params({
    from_date: $("dashFrom").value,
    to_date: $("dashTo").value,
    vessel_id: $("dashVessel").value,
    shift_name: $("dashShift").value,
    page_size: 200,
  });
}
async function loadDashboard() {
  try {
    const q = dashQuery(),
      [d, b, e] = await Promise.all([
        api(`/api/dashboard/fuel?${q}`),
        api(`/api/dashboard/vessel-balances?${q}`),
        api(`/api/dashboard/efficiency?${q}`),
      ]);
    $("kpis").innerHTML = [
      ["Current fuel", d.total_fuel],
      ["Received", d.total_received],
      ["Consumption", d.total_consumption],
      ["Transfer out", d.total_transfer_out],
      ["Low fuel", d.low_fuel_count],
    ]
      .map(
        ([a, v]) =>
          `<div class="kpi"><div>${a}</div><strong>${f(v)}</strong></div>`,
      )
      .join("");
    table(
      "dashboardTable",
      [
        "Date",
        "Vessel",
        "Shift",
        "Opening",
        "Received",
        "Engine",
        "Out",
        "Closing",
        "Flags",
      ],
      d.rows.map((x) => [
        x.shift_date,
        esc(x.vessel_name),
        esc(x.shift_name),
        f(x.opening_fuel),
        f(x.received_fuel),
        f(x.total_engine_consumption),
        f(x.transfer_out),
        f(x.closing_fuel),
        esc(x.flags.join(", ")),
      ]),
    );
    table(
      "balancesTable",
      ["Vessel", "Current fuel", "Threshold", "Days left", "Flags"],
      b.map((x) => [
        esc(x.vessel_name),
        f(x.current_fuel),
        f(x.fuel_threshold_litres),
        f(x.estimated_days_remaining),
        esc(x.flags.join(", ")),
      ]),
    );
    $("efficiencyView").innerHTML =
      `<div class="stat-row"><div class="stat-block"><div class="stat-label">Fuel consumed</div><div class="stat-val">${f(e.total_consumption)} L</div></div><div class="stat-block"><div class="stat-label">Production</div><div class="stat-val">${f(e.total_production)} m³</div></div><div class="stat-block"><div class="stat-label">L / m³</div><div class="stat-val">${f(e.consumption_per_unit)}</div></div></div>`;
  } catch (e) {
    message(e.message, "error");
  }
}
async function loadCharts() {
  try {
    const p = new URLSearchParams({
      from_date: $("dashFrom").value,
      to_date: $("dashTo").value,
    });
    if ($("dashVessel").value) p.append("vessel_ids", $("dashVessel").value);
    const r = await api(`/api/dashboard/charts?${p}`);
    table(
      "trendTable",
      ["Date", "Fuel consumption"],
      r.daily_fuel_consumption.map((x) => [x.date, f(x.consumption)]),
    );
    $("engineSplit").innerHTML = `<div class="stat-row">${[
      ["ME", r.engine_split.me_litres],
      ["AUX", r.engine_split.aux_litres],
      ["DG", r.engine_split.dg_litres],
      ["Total", r.engine_split.total_litres],
    ]
      .map(
        ([a, v]) =>
          `<div class="stat-block"><div class="stat-label">${a}</div><div class="stat-val">${f(v)} L</div></div>`,
      )
      .join("")}</div>`;
    table(
      "vesselComparison",
      ["Vessel", "Consumption"],
      r.vessel_comparison.map((x) => [esc(x.vessel_name), f(x.consumption)]),
    );
  } catch (e) {
    message(e.message, "error");
  }
}
async function downloadExport(type) {
  try {
    const r = await fetch(`/api/export/${type}?${dashQuery()}`, {
      headers: { Authorization: `Bearer ${token()}` },
    });
    if (!r.ok) throw Error("Export failed.");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await r.blob());
    a.download = `insitefuel.${type === "excel" ? "xlsx" : type}`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) {
    message(e.message, "error");
  }
}
function renderMasters() {
  table(
    "projectsList",
    ["ID", "Name", "Code", "Status"],
    projects.map((x) => [
      x.id,
      esc(x.name),
      esc(x.code),
      x.is_active ? "Active" : "Inactive",
    ]),
  );
  table(
    "vesselsList",
    ["ID", "Project", "Vessel", "Code", "Threshold"],
    vessels.map((x) => [
      x.id,
      x.project_id,
      esc(x.name),
      esc(x.code),
      f(x.fuel_threshold_litres),
    ]),
  );
  table(
    "equipmentList",
    ["ID", "Vessel", "Equipment", "Type", "Code", "Status"],
    equipment.map((x) => [
      x.id,
      x.vessel_id,
      esc(x.name),
      esc(x.equipment_type),
      esc(x.code),
      x.is_active ? "Active" : "Inactive",
    ]),
  );
}
async function loadUsers() {
  const rows = await api("/api/users");
  table(
    "usersList",
    ["ID", "Username", "Name", "Role", "Status"],
    rows.map((x) => [
      x.id,
      esc(x.username),
      esc(x.full_name),
      esc(x.role),
      x.is_active ? "Active" : "Inactive",
    ]),
  );
  const backups = await api("/api/backup");
  table(
    "backupsList",
    ["Filename", "Created"],
    backups.map((x) => [esc(x.filename || x), esc(x.created_at || "")]),
  );
}
async function createBackup() {
  try {
    const r = await api("/api/backup", { method: "POST" });
    message(r.message, "success");
    await loadUsers();
  } catch (e) {
    message(e.message, "error");
  }
}
document.querySelectorAll(".tab-btn").forEach((b) =>
  b.addEventListener("click", async () => {
    document
      .querySelectorAll(".tabPage")
      .forEach((x) => x.classList.add("hidden"));
    $(b.dataset.page).classList.remove("hidden");
    document
      .querySelectorAll(".tab-btn")
      .forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    try {
      if (b.dataset.page === "transfers") await loadTransfers();
      if (b.dataset.page === "production") await loadProduction();
      if (b.dataset.page === "soundings") await loadSoundings();
      if (b.dataset.page === "dashboard") await loadDashboard();
      if (b.dataset.page === "charts") await loadCharts();
      if (b.dataset.page === "users" && me.role === "ADMIN") await loadUsers();
    } catch (e) {
      message(e.message, "error");
    }
  }),
);
$("shiftVessel").addEventListener("change", refreshShiftEquipment);
$("productionProject").addEventListener("change", () =>
  select(
    "productionVessel",
    vessels.filter(
      (v) => String(v.project_id) === $("productionProject").value,
    ),
  ),
);
window.addEventListener("load", async () => {
  if (token())
    try {
      await init();
    } catch (_) {
      showLogin();
    }
});
