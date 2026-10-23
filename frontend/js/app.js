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
  sites = [],
  vessels = [],
  equipment = [],
  currentUsers = [],
  activeShift,
  adminSelectedShift,
  adminEngineEvents = [],
  adminEditingEngineEventId = null,
  adminFuelTransactions = [],
  adminTransfers = [],
  adminSoundings = [],
  adminShiftAttachments = [],
  adminProductionRecords = [],
  adminEditingProductionId = null,
  transferShifts = null,
  transferShiftRequest = 0;

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

function litres(value) {
  if (value == null || !Number.isFinite(Number(value))) {
    return "—";
  }

  return Math.round(Number(value)).toLocaleString();
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
  const isMasterTable = [
    "projectsList",
    "sitesList",
    "vesselsList",
    "equipmentList",
  ].includes(id);
  $(id).innerHTML =
    `${isMasterTable ? '<div class="master-table-scroll">' : ""}<table><thead><tr>${heads.map((x) => `<th>${x}</th>`).join("")}</tr></thead><tbody>${rows.length ? rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${heads.length}" class="muted">No records.</td></tr>`}</tbody></table>${isMasterTable ? "</div>" : ""}`;

  if (isMasterTable && rows.length > 7) {
    const scroll = $(id).querySelector(".master-table-scroll");
    const renderedTable = scroll?.querySelector("table");
    const renderedRows = renderedTable?.tBodies[0]?.rows;

    if (scroll && renderedTable && renderedRows) {
      const headerHeight = renderedTable.tHead?.getBoundingClientRect().height || 0;
      const rowsHeight = Array.from(renderedRows)
        .slice(0, 7)
        .reduce((height, row) => height + row.getBoundingClientRect().height, 0);
      if (headerHeight > 0 && rowsHeight > 0) {
        scroll.style.maxHeight = `${Math.ceil(headerHeight + rowsHeight)}px`;
      }
    }
  }
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

function updateOpeningFuelPermission() {
  const openingFuel = $("openingFuel");

  if (!openingFuel) return;

  openingFuel.readOnly = true;
}

async function init() {
  me = await api("/api/auth/me");
  $("loginWrap").classList.add("hidden");
  $("appWrap").classList.remove("hidden");
  $("userChip").textContent = `${me.full_name || me.username} · ${me.role}`;
  updateOpeningFuelPermission();
  document
    .querySelectorAll(".management-only")
    .forEach(
      (x) =>
        (x.style.display = ["MANAGER", "ADMIN"].includes(me.role)
          ? ""
          : "none"),
    );

  document
    .querySelectorAll(".admin-only")
    .forEach((x) => (x.style.display = me.role === "ADMIN" ? "" : "none"));
  document.querySelectorAll(".manager-only").forEach((x) => {
    x.style.display = ["MANAGER", "ADMIN"].includes(me.role) ? "" : "none";
  });

  document.querySelectorAll(".management-only").forEach((x) => {
    x.style.display = ["MANAGER", "ADMIN"].includes(me.role) ? "" : "none";
  });
  await loadMaster();
  ["shiftDate", "productionDate", "soundingDate", "dashTo", "transferDate", "adminShiftFrom", "adminShiftTo"].forEach(
    (id) => ($(id).value = today()),
  );
  if ($("issueDate")) $("issueDate").value = today();
  $("transferReportFrom").value = new Date(Date.now() - 29 * 864e5).toISOString().slice(0, 10);
  $("transferReportTo").value = today();
  if ($("chartFrom")) {
    $("chartFrom").value = new Date(Date.now() - 29 * 864e5)
      .toISOString()
      .slice(0, 10);
  }

  if ($("chartTo")) {
    $("chartTo").value = today();
  }

  if ($("chartVesselChecks")) {
    renderChartVessels();
  }

  $("dashFrom").value = new Date(Date.now() - 29 * 864e5)
    .toISOString()
    .slice(0, 10);

  await refreshShiftEquipment();
  await loadDashboard();
  await refreshTransferShifts();
}

function clearShiftProductionFields() {
  $("advancementM").value = "";
  $("dredgingHours").value = "";
}

function populateShiftProductionFields() {
  updateOpeningFuelPermission();

  if (!activeShift) {
    clearShiftProductionFields();
    return;
  }

  $("advancementM").value =
    activeShift.advancement_m == null ? "" : String(activeShift.advancement_m);
  $("dredgingHours").value =
    activeShift.dredging_hours == null ? "" : String(activeShift.dredging_hours);
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
  const sel = $("receiptSourceSelect");
  if (!sel) return;

  sel.innerHTML = '<option value="">Select source</option>';

  vessels
    .filter(v => v.is_active !== false)
    .filter(v => v.type == "Tanker")
    .forEach(v => {
      const option = document.createElement("option");

      option.value = `vessel:${v.id}`;

      option.textContent = v.project_name
        ? `${v.name} (${v.project_name})`
        : v.name;

      sel.appendChild(option);
    });

  const manual = document.createElement("option");
  manual.value = "__MANUAL__";
  manual.textContent = "Other / Manual";
  sel.appendChild(manual);

  toggleManualFuelSource();
}

async function loadMaster() {
  [projects, sites, vessels, equipment, ] = await Promise.all([
    api("/api/projects"),
    api("/api/sites"),
    api("/api/vessels"),
    api("/api/equipment"),
  ]);

  // Existing application dropdowns
  select("shiftVessel", vessels);
  if ($("shiftVessel")) {
    $("shiftVessel").insertAdjacentHTML(
      "afterbegin",
      '<option value="" selected>Select a vessel</option>',
    );
  }
  select("transferFrom", vessels);
  select("transferTo", vessels);
  select("issueSourceVessel", vessels);
  $("issueSourceVessel").insertAdjacentHTML("afterbegin", '<option value="" selected>Select source vessel</option>');
  $("transferReportVessel").innerHTML = '<option value="">All vessels</option>' +
    vessels.map((vessel) => `<option value="${vessel.id}">${esc(vessel.name)}</option>`).join("");
  populateFuelSources();
  select("productionVessel", vessels);
  select("soundingVessel", vessels);
  select("adminShiftVessel", vessels);
  $("adminShiftVessel").innerHTML =
    '<option value="">All vessels</option>' +
    vessels
      .map((vessel) => `<option value="${vessel.id}">${esc(vessel.name)}</option>`)
      .join("");
  select("dashVessel", vessels, "name", true);
  select("productionProject", projects);

  // Masters dropdowns
  select("masterVesselProject", projects);
  select("masterEquipmentVessel", vessels);
  select("masterThresholdVessel", vessels);

  renderMasters();
  renderChartVessels();
}

async function createProject() {
  try {
    const name = $("masterProjectName").value.trim();
    const code = $("masterProjectCode").value.trim();

    if (!name) {
      throw Error("Project name is required.");
    }

    if (!code) {
      throw Error("Project code is required.");
    }

    await api("/api/projects", {
      method: "POST",
      body: JSON.stringify({
        name,
        code,
      }),
    });

    $("masterProjectName").value = "";
    $("masterProjectCode").value = "";

    message("Project created successfully.", "success");

    await loadMaster();

  } catch (e) {
    message(e.message, "error");
  }
}
async function createVessel() {
  try {
    const name = $("masterVesselName").value.trim();
    const vesselType = $("masterVesselType").value.trim();
    const projectId = n($("masterVesselProject").value);

    if (!name) {
      throw Error("Vessel name is required.");
    }

    if (!vesselType) {
      throw Error("Vessel type is required.");
    }

    if (!projectId) {
      throw Error("Select a project.");
    }

    await api("/api/vessels", {
      method: "POST",
      body: JSON.stringify({
        name,
        vessel_type: vesselType,
        project_id: projectId,
      }),
    });

    $("masterVesselName").value = "";
    $("masterVesselType").value = "";

    message("Vessel created successfully.", "success");

    await loadMaster();

  } catch (e) {
    message(e.message, "error");
  }
}
async function createEquipment() {
  try {
    const name = $("masterEquipmentName").value.trim();
    const equipmentType = $("masterEquipmentType").value;
    const code = $("masterEquipmentCode").value.trim();
    const vesselId = n($("masterEquipmentVessel").value);

    if (!name) {
      throw Error("Equipment name is required.");
    }

    if (!equipmentType) {
      throw Error("Select an equipment type.");
    }

    if (!code) {
      throw Error("Equipment code is required.");
    }

    if (!vesselId) {
      throw Error("Select a vessel.");
    }

    await api("/api/equipment", {
      method: "POST",
      body: JSON.stringify({
        name,
        equipment_type: equipmentType,
        code,
        vessel_id: vesselId,
      }),
    });

    $("masterEquipmentName").value = "";
    $("masterEquipmentCode").value = "";

    message("Equipment created successfully.", "success");

    await loadMaster();

  } catch (e) {
    message(e.message, "error");
  }
}

async function updateVesselThreshold() {
  try {
    const vesselId = n($("masterThresholdVessel").value);
    const value = n($("masterThresholdValue").value);

    if (!vesselId) {
      throw Error("Select a vessel.");
    }

    if (value < 0) {
      throw Error("Threshold cannot be negative.");
    }

    await api(`/api/vessels/${vesselId}/threshold`, {
      method: "PUT",
      body: JSON.stringify({
        fuel_threshold_litres: value,
      }),
    });

    message("Fuel threshold updated.", "success");

    await loadMaster();

  } catch (e) {
    message(e.message, "error");
  }
}

async function openShift() {
  try {
    if (!$("shiftVessel").value) {
      throw Error("Select a vessel before opening or loading a shift.");
    }
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
    populateShiftProductionFields();
    updateOpeningFuelPermission();
    $("shiftState").textContent =
      `Shift #${s.id} · ${s.status} · opening ${litres(s.opening_fuel)} L`;

    await loadShiftReport();
    await loadShiftAttachments();
  } catch (e) {
    message(e.message, "error");
  }
}
async function establishInitialOpening() {
  try {
    if (!$("shiftVessel").value) {
      throw Error("Select a vessel before setting its initial opening fuel.");
    }
    const rawOpeningFuel = prompt(
      "Initial opening fuel (L):",
      $("openingFuel").value || "0",
    );

    if (rawOpeningFuel === null) return;

    const openingFuel = Number(rawOpeningFuel);

    if (!Number.isFinite(openingFuel) || openingFuel < 0) {
      throw Error("Opening fuel must be a non-negative number.");
    }

    const s = await api("/api/fuel/shift/initial-opening", {
      method: "POST",
      body: JSON.stringify({
        vessel_id: n($("shiftVessel").value),
        shift_date: $("shiftDate").value,
        opening_fuel: openingFuel,
      }),
    });
    activeShift = s;
    $("openingFuel").value = s.opening_fuel;
    updateOpeningFuelPermission();
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
  clearShiftProductionFields();
  $("shiftState").textContent = "Select a shift, then open or load it.";
}
async function loadShiftReport() {
  try {
    if (!activeShift) return;

    const r = await api(`/api/fuel/shift/${activeShift.id}/report`);
    activeShift = r.shift;
    populateShiftProductionFields();

    const b = r.balance;
    const transactions = r.transactions || [];
    const engineEvents = await api(`/api/engine/events?shift_id=${activeShift.id}`);
    const engineEventById = new Map(engineEvents.map((event) => [Number(event.id), event]));

    table(
      "shiftReport",
      [
        "Opening",
        "Received",
        "Transfer in",
        "Engine use",
        "Transfer out",
        "Issued out",
        "Adjustments",
        "Advancement",
        "Dredging hours",
        "Closing",
      ],
      [
        [
          litres(b.opening_fuel),
          litres(b.received_fuel),
          litres(b.transfer_in),
          litres(b.engine_consumption),
          litres(b.transfer_out),
          litres(b.issue_out),
          `${litres(b.adjustment_in)} / ${litres(b.adjustment_out)}`,
          activeShift.advancement_m == null ? "—" : f(activeShift.advancement_m),
          activeShift.dredging_hours == null ? "—" : f(activeShift.dredging_hours),
          litres(b.closing_fuel),
        ],
      ],
    );

    $("shiftState").textContent =
      `Shift #${activeShift.id} · ${activeShift.status} · calculated closing ${litres(b.closing_fuel)} L`;

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
      } else if (t.transaction_type === "ISSUE_OUT") {
        details = "Issue to untracked vessel";
      } else if (t.transaction_type === "ADJUSTMENT") {
        details =
          t.adjustment_direction === "IN" ? "Adjustment In" : "Adjustment Out";
      }

      const type = String(t.transaction_type || "").replaceAll("_", " ");
      const isEngineEvent = t.transaction_type === "ENGINE_CONSUMPTION" && t.reference_type === "ENGINE_EVENT";
      const operatorRemark = isEngineEvent
        ? engineEventById.get(Number(t.reference_id))?.remarks
        : t.remarks;

      return [
        formatDateTime(t.transaction_date),
        type,
        details,
        `${litres(t.quantity)} L`,
        esc(operatorRemark || "-"),
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
async function changeOpeningFuel() {
  try {
    if (!activeShift) {
      throw Error("Open or load a shift first.");
    }

    if (activeShift.status !== "OPEN") {
      throw Error("Only an OPEN shift can be updated.");
    }

    const role = String(me?.role || "").trim().toUpperCase();

    if (!["MANAGER", "ADMIN"].includes(role)) {
      throw Error("Only a manager or administrator may edit opening fuel.");
    }

    const rawOpeningFuel = prompt(
      "New opening fuel (L):",
      String(activeShift.opening_fuel),
    );

    if (rawOpeningFuel === null) return;

    const openingFuel = Number(rawOpeningFuel);

    if (!Number.isFinite(openingFuel) || openingFuel < 0) {
      throw Error("Opening fuel must be a non-negative number.");
    }

    if (openingFuel === Number(activeShift.opening_fuel)) {
      message("Opening fuel was not changed.", "info");
      return;
    }

    const correctedShift = await api(
      `/api/fuel/shift/${activeShift.id}/opening`,
      {
        method: "PATCH",
        body: JSON.stringify({
          opening_fuel: openingFuel,
          reason: "Opening fuel updated from shift data form.",
        }),
      },
    );

    activeShift = correctedShift;
    $("openingFuel").value = correctedShift.opening_fuel;
    updateOpeningFuelPermission();
    message("Opening fuel saved.", "success");
    await loadShiftReport();
  } catch (e) {
    message(e.message, "error");
  }
}
async function saveShiftProductionData() {
  try {
    if (!activeShift) {
      throw Error("Open or load a shift first.");
    }

    if (activeShift.status !== "OPEN") {
      throw Error("Only an OPEN shift can be updated.");
    }

    const rawAdvancement = $("advancementM").value.trim();
    const rawDredgingHours = $("dredgingHours").value.trim();

    const advancement = rawAdvancement === "" ? null : Number(rawAdvancement);
    const dredgingHours = rawDredgingHours === "" ? null : Number(rawDredgingHours);

    if (advancement !== null && advancement < 0) {
      throw Error("Advancement cannot be negative.");
    }

    if (dredgingHours !== null && dredgingHours < 0) {
      throw Error("Dredging hours cannot be negative.");
    }

    const updatedShift = await api(
      `/api/fuel/shift/${activeShift.id}/production-data`,
      {
        method: "PUT",
        body: JSON.stringify({
          advancement_m: advancement,
          dredging_hours: dredgingHours,
        }),
      },
    );
    activeShift = updatedShift;

    message("Shift production data saved.", "success");
    await loadShiftReport();
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

      const vessel = vessels.find((v) => Number(v.id) === sourceVesselId);

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
        consumption,
        remarks: $("engineRemarks").value.trim() || null,
      }),
    });

    message(
      `Engine event recorded: ${litres(consumption)} L over ${hours.toFixed(2)} hours (${Math.round(lph).toLocaleString()} L/hr).`,
      "success",
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

  lphField.value = String(Math.round(lph));

  display.textContent = `Calculated ${hours.toFixed(2)} hours × ${Math.round(lph).toLocaleString()} L/hr = ${litres(consumption)} L`;

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

async function getTransferShift(vesselId, shiftDate, shiftName) {
  return await api(
    `/api/fuel/shift?${params({
      vessel_id: vesselId,
      shift_date: shiftDate,
      shift_name: shiftName,
    })}`,
  );
}

async function getCurrentTransferShift(vesselId, shiftDate = today()) {
  // First check Morning.
  try {
    const morning = await getTransferShift(vesselId, shiftDate, "MORNING");

    if (morning && morning.status === "OPEN") {
      return morning;
    }
  } catch (e) {
    // Morning does not exist yet.
  }

  // Morning is closed or unavailable, so use Evening.
  try {
    const evening = await getTransferShift(vesselId, shiftDate, "EVENING");

    if (evening && evening.status === "OPEN") {
      return evening;
    }
  } catch (e) {
    // Evening does not exist yet.
  }

  throw new Error(
    shiftDate === today()
      ? `No open current shift found for vessel ${vesselId}.`
      : `No open shift found for vessel ${vesselId} on ${shiftDate}.`,
  );
}

async function refreshTransferShifts() {
  const requestId = ++transferShiftRequest;
  const fromVesselId = n($("transferFrom").value);
  const toVesselId = n($("transferTo").value);
  const transferDate = $("transferDate").value || today();
  const selectedShift = $("transferShift").value;
  const isHistorical = transferDate < today();
  const info = $("transferShiftInfo");

  transferShifts = null;

  if (!fromVesselId || !toVesselId) {
    info.textContent = "Select source and destination vessels to load shifts.";
    return null;
  }

  if (fromVesselId === toVesselId) {
    info.textContent = "Source and destination vessels must be different.";
    return null;
  }

  info.textContent = "Loading shifts...";

  try {
    const [fromShift, toShift] = selectedShift && !isHistorical
      ? await Promise.all([
          getTransferShift(fromVesselId, transferDate, selectedShift),
          getTransferShift(toVesselId, transferDate, selectedShift),
        ])
      : await Promise.all([
          getCurrentTransferShift(fromVesselId, transferDate),
          getCurrentTransferShift(toVesselId, transferDate),
        ]);

    if (requestId !== transferShiftRequest) return null;

    const selectedShiftLabel = selectedShift && !isHistorical
      ? `${selectedShift.toLowerCase()} shift`
      : "shift";
    const transferDateLabel = transferDate === today()
      ? "today"
      : `on ${transferDate}`;

    if (fromShift.status !== "OPEN") {
      throw Error(
        `Source vessel does not have an open ${selectedShiftLabel} ${transferDateLabel}.`,
      );
    }
    if (toShift.status !== "OPEN") {
      throw Error(
        `Destination vessel does not have an open ${selectedShiftLabel} ${transferDateLabel}.`,
      );
    }

    transferShifts = {
      fromVesselId,
      toVesselId,
      transferDate,
      fromShift,
      toShift,
    };
    info.textContent =
      `Source: ${fromShift.shift_name} (${fromShift.status})\n` +
      `Destination: ${toShift.shift_name} (${toShift.status})`;
    return transferShifts;
  } catch (e) {
    if (requestId === transferShiftRequest) {
      info.textContent = e.message;
    }
    return null;
  }
}


async function createTransfer() {
  try {
    const fromVesselId = n($("transferFrom").value);
    const toVesselId = n($("transferTo").value);
    const quantity = n($("transferQty").value);

    if (!fromVesselId) {
      throw Error("Select the source vessel.");
    }

    if (!toVesselId) {
      throw Error("Select the destination vessel.");
    }

    if (fromVesselId === toVesselId) {
      throw Error("Source and destination vessels must be different.");
    }

    if (quantity <= 0) {
      throw Error("Transfer quantity must be greater than zero.");
    }

    const shifts = await refreshTransferShifts();
    if (!shifts) throw Error("Unable to load shifts for the selected date.");

    const { fromShift, toShift, transferDate } = shifts;

    const r = await api("/api/transfers", {
      method: "POST",
      body: JSON.stringify({
        from_vessel_id: fromVesselId,
        from_shift_id: fromShift.id,

        to_vessel_id: toVesselId,
        to_shift_id: toShift.id,

        initiated_quantity: quantity,
  transfer_date: `${transferDate}T00:00:00.000Z`,
        notes: $("transferNotes").value.trim() || null,
      }),
    });

    message(`Transfer #${r.id} initiated.`, "success");

    $("transferQty").value = "";
    $("transferNotes").value = "";

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
      chartVesselName(x.from_vessel_id),
      chartVesselName(x.to_vessel_id),
      litres(x.initiated_quantity),
      litres(x.received_quantity),
      litres(x.loss_quantity),
      esc(x.status),
      `${
        x.status === "INITIATED"
          ? `<button class="btn btn-sm" onclick="transferAction(${x.id},'receive')">Receive</button>`
          : ""
      }
${
  x.status === "RECEIVING_CONFIRMED"
    ? `<button class="btn btn-sm" onclick="transferAction(${x.id},'submit-review')">Submit for Review</button>`
    : ""
}
${
  x.status === "MANAGER_REVIEW" && ["MANAGER", "ADMIN"].includes(me.role)
    ? `<button class="btn btn-sm" onclick="transferAction(${x.id},'approve')">Approve</button>
       <button class="btn btn-sm" onclick="transferAction(${x.id},'reject')">Reject</button>`
    : ""
}`,
    ]),
  );
}

function transferReportQuery() {
  const query = new URLSearchParams();
  const fromDate = $("transferReportFrom").value;
  const toDate = $("transferReportTo").value;
  const status = $("transferReportStatus").value;
  const vesselId = $("transferReportVessel").value;
  if (fromDate) query.set("from_date", fromDate);
  if (toDate) query.set("to_date", toDate);
  if (status) query.set("status", status);
  if (vesselId) query.set("vessel_id", vesselId);
  return query.toString();
}

async function loadTransferReport() {
  if (me?.role !== "ADMIN") throw Error("Only an administrator can view transfer reports.");
  const rows = await api(`/api/transfers/admin/report?${transferReportQuery()}`);
  $("transferReportStatusMessage").textContent = `${rows.length} transfer${rows.length === 1 ? "" : "s"} found.`;
  table("transferReportList", ["ID", "From", "To", "Date", "Initiated (L)", "Received (L)", "Loss (L)", "Status", "Notes", "Manager remark", "Actions"], rows.map((row) => [
    row.id, esc(row.from_vessel), esc(row.to_vessel), formatDateTime(row.transfer_date),
    litres(row.initiated_quantity), litres(row.received_quantity), litres(row.loss_quantity),
    esc(row.status), esc(row.notes || "—"), esc(row.manager_remark || "—"),
    row.status === "BALANCES_UPDATED" && ["MISSING", "PARTIAL"].includes(row.ledger_state)
      ? `<button class="btn btn-sm" onclick="recordBalanceNeutralTransfer(${row.id})">Add to fuel transactions</button>`
      : esc(row.ledger_state || "—"),
  ]));
}

async function recordBalanceNeutralTransfer(transferId) {
  try {
    if (me?.role !== "ADMIN") throw Error("Only an administrator can record transfer transactions.");
    const reason = prompt("Reason for adding transfer entries without changing balances:", "Transfer already reflected in both vessels' opening balances");
    if (reason === null) return;
    if (!reason.trim()) throw Error("Enter a reason.");
    if (!confirm(`Add transfer #${transferId} to both vessels' fuel transactions for dashboard visibility?\n\nThis will not change either shift's opening or closing balance.`)) return;
    const result = await api(`/api/transfers/admin/${transferId}/record-balance-neutral-ledger`, {
      method: "POST",
      body: JSON.stringify({ reason: reason.trim() }),
    });
    message(result.created
      ? `Added ${result.created} transfer transaction entries. Shift balances were unchanged.`
      : "Transfer ledger entries are already recorded; balances are unchanged.", "success");
    await loadTransferReport();
  } catch (error) { message(error.message, "error"); }
}

async function exportTransferReport() {
  try {
    if (me?.role !== "ADMIN") throw Error("Only an administrator can export transfer reports.");
    const response = await fetch(`/api/transfers/admin/report.csv?${transferReportQuery()}`, {
      headers: { Authorization: `Bearer ${token()}` },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw Error(body?.detail || "Transfer export failed.");
    }
    const link = document.createElement("a");
    link.href = URL.createObjectURL(await response.blob());
    link.download = "insitefuel_transfers.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) { message(error.message, "error"); }
}

function showTransferView(view) {
  if (view === "report" && me?.role !== "ADMIN") return;
  $("transferRegisterView").classList.toggle("hidden", view !== "register");
  $("transferIssuesView").classList.toggle("hidden", view !== "issues");
  $("transferReportView").classList.toggle("hidden", view !== "report");
  document.querySelectorAll("[data-transfer-view]").forEach((button) =>
    button.classList.toggle("active", button.dataset.transferView === view));
  if (view === "report") loadTransferReport().catch((error) => message(error.message, "error"));
  if (view === "issues") loadFuelIssues().catch((error) => message(error.message, "error"));
}

async function resolveIssueShift() {
  const vesselId = n($("issueSourceVessel").value);
  const shiftDate = $("issueDate").value || today();
  if (!vesselId) throw Error("Select the source vessel.");
  const chosenShift = $("issueShift").value;
  const shift = chosenShift
    ? await getTransferShift(vesselId, shiftDate, chosenShift)
    : await getCurrentTransferShift(vesselId, shiftDate);
  if (shift.status !== "OPEN") throw Error("Select an open source shift.");
  return shift;
}

async function refreshIssueShift() {
  try {
    const shift = await resolveIssueShift();
    $("issueShiftInfo").textContent = `Issue will be recorded against ${shift.shift_name} shift #${shift.id} (${shift.shift_date}).`;
  } catch (error) {
    $("issueShiftInfo").textContent = error.message;
  }
}

async function createFuelIssue() {
  try {
    if (!me || !["OPERATOR", "MANAGER", "ADMIN"].includes(me.role)) {
      throw Error("You do not have permission to submit fuel issues.");
    }
    const shift = await resolveIssueShift();
    const receivingVessel = $("issueReceivingVessel").value.trim();
    const quantity = $("issueQuantity").value;
    if (!receivingVessel) throw Error("Enter the receiving vessel name.");
    if (!(Number(quantity) > 0)) throw Error("Quantity must be greater than zero.");
    await api("/api/issues", {
      method: "POST",
      body: JSON.stringify({
        vessel_id: n($("issueSourceVessel").value),
        shift_id: shift.id,
        receiving_vessel: receivingVessel,
        quantity: String(quantity),
        notes: $("issueNotes").value.trim() || null,
      }),
    });
    message("Issue submitted for administrator approval.", "success");
    $("issueReceivingVessel").value = "";
    $("issueQuantity").value = "";
    $("issueNotes").value = "";
    await loadFuelIssues();
  } catch (error) { message(error.message, "error"); }
}

async function reviewFuelIssue(id, decision) {
  try {
    if (decision === "approve" && !confirm("Approve this issue? If the source shift has later shifts, their opening and closing balances will be recalculated from this issue onward. Recorded transactions will stay unchanged, and approval will be blocked if a later shift would go below zero.")) return;
    const remark = prompt(decision === "approve" ? "Admin remark (optional):" : "Reason for rejection:");
    if (remark === null) return;
    if (decision === "reject" && !remark.trim()) throw Error("A rejection reason is required.");
    await api(`/api/issues/${id}/${decision}`, {
      method: "POST",
      body: JSON.stringify({ admin_remark: remark.trim() || null, reconcile_downstream: decision === "approve" }),
    });
    message(decision === "approve"
      ? "Issue approved; downstream shifts reconciled where needed."
      : "Issue rejected.", "success");
    await loadFuelIssues();
  } catch (error) { message(error.message, "error"); }
}

async function loadFuelIssues() {
  const rows = await api("/api/issues");
  table("fuelIssueList", ["ID", "Source", "Shift", "Receiving vessel", "Quantity (L)", "Notes", "Status", "Admin remark", "Actions"], rows.map((row) => [
    row.id, esc(chartVesselName(row.vessel_id)), row.shift_id,
    esc(row.receiving_vessel), litres(row.quantity), esc(row.notes || "—"),
    esc(row.status), esc(row.admin_remark || "—"),
    row.status === "PENDING" && me?.role === "ADMIN"
      ? `<button class="btn btn-sm" onclick="reviewFuelIssue(${row.id},'approve')">Approve &amp; Reconcile</button> <button class="btn btn-sm" onclick="reviewFuelIssue(${row.id},'reject')">Reject</button>`
      : "—",
  ]));
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
      litres(x.fuel_rate),
    ]),
  );
}
async function uploadShiftAttachment(type) {
  try {
    if (!activeShift?.id) {
      throw Error("Open or load a shift first.");
    }

    const inputMap = {
      bill: "billFile",
      transfer_note: "transferNoteFile",
      sounding: "soundingFile",
    };

    const inputId = inputMap[type];

    if (!inputId) {
      throw Error("Invalid attachment type.");
    }

    const file = $(inputId)?.files?.[0];

    if (!file) {
      throw Error("Choose a file first.");
    }

    // =========================================================
    // SOUNDING
    // =========================================================
    // Soundings are real Sounding records.
    if (type === "sounding") {
      const soundingList = await api(
        `/api/soundings?shift_id=${activeShift.id}`,
      );

      if (soundingList.length >= 5) {
        throw Error(
          "This shift already has the maximum of 5 soundings.",
        );
      }

      const allowedTypes = [
        "image/jpeg",
        "image/png",
        "image/webp",
      ];

      if (!allowedTypes.includes(file.type)) {
        throw Error(
          "Sounding must be a JPEG, PNG, or WebP image.",
        );
      }

      const data = new FormData();
      data.append("file", file);

      const attachment = await api(
        "/api/attachments/upload",
        {
          method: "POST",
          body: data,
        },
      );

      await api(
        `/api/soundings?${params({
          shift_id: activeShift.id,
          attachment_id: attachment.id,
        })}`,
        {
          method: "POST",
        },
      );

      $(inputId).value = "";

      message(
        "Sounding uploaded and submitted.",
        "success",
      );

      await loadShiftAttachments();
      await loadShiftReport();

      return;
    }

    // =========================================================
    // BILL
    // =========================================================
    if (type === "bill") {
      const data = new FormData();
      data.append("file", file);

      const attachment = await api(
        "/api/attachments/upload",
        {
          method: "POST",
          body: data,
        },
      );

      await api(
        `/api/shifts/${activeShift.id}/attachments`,
        {
          method: "POST",
          body: JSON.stringify({
            attachment_id: attachment.id,
            attachment_type: "BILL",
          }),
        },
      );

      $(inputId).value = "";

      message("Bill uploaded.", "success");

      await loadShiftAttachments();

      return;
    }

    // =========================================================
    // TRANSFER NOTE
    // =========================================================
    if (type === "transfer_note") {
      // First upload the physical file.
      const data = new FormData();
      data.append("file", file);

      const attachment = await api(
        "/api/attachments/upload",
        {
          method: "POST",
          body: data,
        },
      );

      // Find transfers associated with this shift.
      const transfers = await api("/api/transfers");

      const completedTransfers = transfers.filter(
        (transfer) =>
          transfer.status === "BALANCES_UPDATED" &&
          (
            transfer.from_shift_id === activeShift.id ||
            transfer.to_shift_id === activeShift.id
          ),
      );

      if (!completedTransfers.length) {
        throw Error(
          "No completed transfer is associated with this shift.",
        );
      }

      // If there is more than one completed transfer,
      // ask the user which transfer this note belongs to.
      let transfer;

      if (completedTransfers.length === 1) {
        transfer = completedTransfers[0];
      } else {
        const options = completedTransfers
          .map(
            (t, index) =>
              `${index + 1}. Transfer #${t.id} — ` +
              `${litres(t.initiated_quantity)} L`,
          )
          .join("\n");

        const answer = prompt(
          `Select the transfer this note belongs to:\n\n${options}\n\nEnter the number:`,
        );

        if (answer === null) {
          throw Error("Transfer note upload cancelled.");
        }

        const selectedIndex = Number(answer) - 1;

        if (
          !Number.isInteger(selectedIndex) ||
          selectedIndex < 0 ||
          selectedIndex >= completedTransfers.length
        ) {
          throw Error("Invalid transfer selection.");
        }

        transfer = completedTransfers[selectedIndex];
      }

      // Check existing notes on this transfer.
      const existingNotes = await api(
        `/api/transfers/${transfer.id}/attachments`,
      );

      if (existingNotes.length >= 5) {
        throw Error(
          `Transfer #${transfer.id} already has the maximum of 5 transfer notes.`,
        );
      }

      // Link the uploaded Attachment to the FuelTransfer.
      await api(
        `/api/transfers/${transfer.id}/attachments`,
        {
          method: "POST",
          body: JSON.stringify({
            attachment_id: attachment.id,
          }),
        },
      );

      $(inputId).value = "";

      message(
        `Transfer note linked to Transfer #${transfer.id}.`,
        "success",
      );

      await loadShiftAttachments();

      return;
    }

    throw Error("Invalid attachment type.");

  } catch (e) {
    message(e.message, "error");
  }
}

async function viewShiftAttachment(attachmentId) {
  try {
    const response = await fetch(
      `/api/attachments/${attachmentId}/download`,
      {
        headers: {
          Authorization: `Bearer ${token()}`,
        },
      }
    );

    if (!response.ok) {
      let detail = "Unable to open attachment.";

      try {
        const data = await response.json();
        detail = data.detail || detail;
      } catch {}

      throw new Error(detail);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);

    window.open(url, "_blank");

    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) {
    message(e.message, "error");
  }
}

async function loadShiftAttachments() {
  const list = $("attachmentList");

  if (!list) return;

  if (!activeShift) {
    list.innerHTML =
      '<div class="muted">Open a shift to view attachments.</div>';
    return;
  }

  try {
    // ---------------------------------------------------------
    // Load normal shift attachments + soundings + transfers
    // ---------------------------------------------------------
    const [attachments, soundings, transfers] = await Promise.all([
      api(`/api/shifts/${activeShift.id}/attachments`),
      api(`/api/soundings?shift_id=${activeShift.id}`),
      api("/api/transfers"),
    ]);

    const rows = [];

    // =========================================================
    // NORMAL SHIFT ATTACHMENTS
    // =========================================================
    // BILL and any legacy TRANSFER_NOTE attachments remain
    // visible here.
    for (const item of attachments) {
      // Soundings are now real Sounding records.
      if (item.attachment_type === "SOUNDING") {
        continue;
      }

      rows.push({
        type: item.attachment_type,
        filename: item.original_filename,
        attachment_id: item.attachment_id,
      });
    }

    // =========================================================
    // SHIFT SOUNDINGS
    // =========================================================
    soundings.forEach((sounding, index) => {
      rows.push({
        type: "SOUNDING",
        filename: `Sounding ${index + 1} of 5`,
        attachment_id: sounding.attachment_id,
      });
    });

    // =========================================================
    // TRANSFER NOTES
    // =========================================================
    // Find completed transfers belonging to this shift.
    const completedTransfers = transfers.filter(
      (transfer) =>
        transfer.status === "BALANCES_UPDATED" &&
        (
          Number(transfer.from_shift_id) === Number(activeShift.id) ||
          Number(transfer.to_shift_id) === Number(activeShift.id)
        ),
    );

    // Load notes for every completed transfer belonging to this shift.
    for (const transfer of completedTransfers) {
      const transferNotes = await api(
        `/api/transfers/${transfer.id}/attachments`,
      );

      transferNotes.forEach((note, index) => {
        rows.push({
          type: "TRANSFER NOTE",
          filename:
            `Transfer #${transfer.id} — ` +
            `Note ${index + 1} of 5`,
          attachment_id: note.attachment_id,
        });
      });
    }

    // =========================================================
    // NOTHING UPLOADED
    // =========================================================
    if (!rows.length) {
      list.innerHTML =
        '<div class="muted">No attachments yet.</div>';
      return;
    }

    // =========================================================
    // DISPLAY
    // =========================================================
    list.innerHTML = rows
      .map(
        (item) => `
          <div class="attachment-item">
            <div>
              <strong>${esc(item.type)}</strong>
              <div>${esc(item.filename)}</div>
            </div>

            <a
              href="#"
              onclick="viewShiftAttachment(${item.attachment_id}); return false;"
            >
              View
            </a>
          </div>
        `,
      )
      .join("");

  } catch (e) {
    list.innerHTML =
      `<div class="error">${esc(e.message)}</div>`;
  }
}
async function loadSoundingShift() {
  try {
    const vesselId = n($("soundingVessel").value);
    const shiftDate = $("soundingDate").value;
    const shiftName = $("soundingShift").value;

    if (!vesselId) {
      throw Error("Select a vessel.");
    }

    if (!shiftDate) {
      throw Error("Select a shift date.");
    }

    if (!shiftName) {
      throw Error("Select a shift.");
    }

    // ---------------------------------------------------------
    // Find the selected shift
    // ---------------------------------------------------------

    const shift = await api(
      `/api/fuel/shift?${params({
        vessel_id: vesselId,
        shift_date: shiftDate,
        shift_name: shiftName,
      })}`,
    );

    if (!shift) {
      throw Error("Shift not found.");
    }

    // ---------------------------------------------------------
    // Load soundings belonging to this shift
    // ---------------------------------------------------------

    const [status, soundings] = await Promise.all([
      api(`/api/soundings/status?shift_id=${shift.id}`),
      api(`/api/soundings?shift_id=${shift.id}`),
    ]);

    // ---------------------------------------------------------
    // Find vessel name
    // ---------------------------------------------------------

    const vessel = vessels.find(
      (v) => Number(v.id) === Number(vesselId),
    );

    const vesselName =
      vessel?.name || `Vessel ${vesselId}`;

    // ---------------------------------------------------------
    // Status summary
    // ---------------------------------------------------------

    const count = soundings.length;

    let statusText = status.status || "UNKNOWN";

    $("soundingStatus").innerHTML = `
      <div class="note">
        <strong>${esc(vesselName)}</strong>
        · ${esc(shiftName)}
        · ${esc(shiftDate)}
        <br>
        Soundings:
        <strong>${count} / 5</strong>
        · Status:
        <strong>${esc(statusText)}</strong>
      </div>
    `;

    // ---------------------------------------------------------
    // Sounding list
    // ---------------------------------------------------------

    if (!soundings.length) {
      $("soundingList").innerHTML =
        '<div class="muted">No soundings submitted for this shift.</div>';
    } else {
      $("soundingList").innerHTML = soundings
        .map(
          (sounding, index) => `
            <div class="attachment-item">
              <div>
                <strong>Sounding ${index + 1} of 5</strong>
                <div class="muted">
                  Submitted:
                  ${esc(formatDateTime(sounding.submitted_at))}
                </div>
              </div>

              <a
                href="#"
                onclick="viewShiftAttachment(${sounding.attachment_id}); return false;"
              >
                View
              </a>
            </div>
          `,
        )
        .join("");
    }

    // ---------------------------------------------------------
    // Missing / due section
    //
    // A shift requires at least one sounding.
    // ---------------------------------------------------------

    let missingMessage = "";

    if (count === 0) {
      missingMessage = `
        <div class="note note-warn">
          <strong>Sounding required.</strong>
          This shift has no sounding yet.
        </div>
      `;
    } else if (count < 5) {
      missingMessage = `
        <div class="muted">
          ${5 - count} additional sounding(s) may still be uploaded.
          Maximum is 5 per shift.
        </div>
      `;
    } else {
      missingMessage = `
        <div class="note note-ok">
          Maximum of 5 soundings reached for this shift.
        </div>
      `;
    }

    $("missingList").innerHTML = missingMessage;

  } catch (e) {
    $("soundingStatus").innerHTML =
      `<div class="error">${esc(e.message)}</div>`;

    $("soundingList").innerHTML = "";
    $("missingList").innerHTML = "";
  }
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
      ["Current fuel", d.total_fuel, true],
      ["Received", d.total_received, true],
      ["Transfer in", d.total_transfer_in, true],
      ["Consumption", d.total_consumption, true],
      ["Transfer out", d.total_transfer_out, true],
      ["Issued to untracked vessels", d.total_issue_out, true],
      ["Advancement", d.total_advancement_m, false],
      ["Dredging hours", d.total_dredging_hours, false],
    ]
      .map(
        ([a, v, isFuel]) =>
          `<div class="kpi"><div>${a}</div><strong>${isFuel ? litres(v) : f(v)}</strong></div>`,
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
        "Transfer In",
        "Engine",
        "Transfer Out",
        "Fuel Issues Out",
        "Closing",
        "Advancement",
        "Dredging Hours",
        "Flags",
      ],
      d.rows.map((x) => [
        x.shift_date,
        esc(x.vessel_name),
        esc(x.shift_name),
        litres(x.opening_fuel),
        litres(x.received_fuel),
        litres(x.transfer_in),
        litres(x.total_engine_consumption),
        litres(x.transfer_out),
        litres(x.issue_out),
        litres(x.closing_fuel),
        x.advancement_m == null ? "—" : f(x.advancement_m),
        x.dredging_hours == null ? "—" : f(x.dredging_hours),
        esc(x.flags.join(", ")),
      ]),
    );
    table(
      "balancesTable",
      ["Vessel", "Latest opening", "Latest closing", "Threshold", "Days left", "Flags"],
      b.map((x) => [
        esc(x.vessel_name),
        litres(x.latest_opening_fuel),
        litres(x.current_fuel),
        litres(x.fuel_threshold_litres),
        f(x.estimated_days_remaining),
        esc(x.flags.join(", ")),
      ]),
    );
    $("efficiencyView").innerHTML =
      `<div class="stat-row"><div class="stat-block"><div class="stat-label">Fuel consumed</div><div class="stat-val">${litres(e.total_consumption)} L</div></div><div class="stat-block"><div class="stat-label">Production</div><div class="stat-val">${f(e.total_production)} m³</div></div><div class="stat-block"><div class="stat-label">L / m³</div><div class="stat-val">${litres(e.consumption_per_unit)}</div></div></div>`;
  } catch (e) {
    message(e.message, "error");
  }
}
// ============================================================
// FUEL ANALYTICS / CHARTS
// ============================================================

let chartInstances = {};


// ============================================================
// VESSEL COLOURS
// ============================================================

const VESSEL_CHART_COLORS = [
  "#2563eb",
  "#059669",
  "#dc2626",
  "#d97706",
  "#7c3aed",
  "#0891b2",
  "#db2777",
  "#65a30d",
  "#9333ea",
  "#0f766e",
  "#ea580c",
  "#4f46e5",
];

function vesselChartColor(vesselId, index = 0) {
  const id = Number(vesselId);

  if (Number.isFinite(id) && id > 0) {
    return VESSEL_CHART_COLORS[
      (id - 1) % VESSEL_CHART_COLORS.length
    ];
  }

  return VESSEL_CHART_COLORS[
    index % VESSEL_CHART_COLORS.length
  ];
}


// ============================================================
// DESTROY EXISTING CHARTS
// ============================================================

function destroyCharts() {
  Object.values(chartInstances).forEach((chart) => {
    try {
      chart.destroy();
    } catch (_) {}
  });

  chartInstances = {};
}


// ============================================================
// VESSEL SELECTION
// ============================================================

function renderChartVessels() {
  const container = $("chartVesselChecks");

  if (!container) {
    return;
  }

  if (!vessels || !vessels.length) {
    container.innerHTML =
      `<div class="muted">No vessels available.</div>`;
    return;
  }

  container.innerHTML = vessels
    .filter((v) => v.is_active !== false)
    .map((vessel) => {
      const id = Number(vessel.id);
      const colour = vesselChartColor(id);

      return `
        <label
          class="vessel-checkbox-item"
          style="border-left: 3px solid ${colour};"
        >
          <input
            type="checkbox"
            value="${id}"
            onchange="updateChartVesselSummary()"
          />

          <span>
            ${esc(vessel.name)}
          </span>
        </label>
      `;
    })
    .join("");

  updateChartVesselSummary();
}


function selectAllChartVessels() {
  document
    .querySelectorAll(
      '#chartVesselChecks input[type="checkbox"]'
    )
    .forEach((checkbox) => {
      checkbox.checked = true;
    });

  updateChartVesselSummary();
}


function clearChartVessels() {
  document
    .querySelectorAll(
      '#chartVesselChecks input[type="checkbox"]'
    )
    .forEach((checkbox) => {
      checkbox.checked = false;
    });

  updateChartVesselSummary();
}


function getSelectedChartVessels() {
  return Array.from(
    document.querySelectorAll(
      '#chartVesselChecks input[type="checkbox"]:checked'
    )
  )
    .map((checkbox) => Number(checkbox.value))
    .filter((id) => Number.isFinite(id));
}


function updateChartVesselSummary() {
  const selected = getSelectedChartVessels();
  const summary = $("chartVesselSummary");

  if (!summary) {
    return;
  }

  if (!selected.length) {
    summary.textContent = "No vessels selected.";
    return;
  }

  const names = selected.map((id) => {
    const vessel = vessels.find(
      (v) => Number(v.id) === Number(id)
    );

    return vessel?.name || `Vessel ${id}`;
  });

  summary.textContent =
    `${selected.length} vessel(s) selected: ${names.join(", ")}`;
}


function chartVesselName(id) {
  const vessel = vessels.find(
    (v) => Number(v.id) === Number(id)
  );

  return vessel?.name || `Vessel ${id}`;
}

function chartVesselCode(id){
  const vessel = vessels.find(
    (v) => Number(v.id) === Number(id)
  );

  return vessel?.code || `Vessel ${id}`;
}


// ============================================================
// DATE HELPERS
// ============================================================

function chartDateKey(value) {
  if (!value) {
    return null;
  }

  if (
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}$/.test(value)
  ) {
    return value;
  }

  const d = new Date(value);

  if (Number.isNaN(d.getTime())) {
    return null;
  }

  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
}


function buildChartDateRange(fromDate, toDate) {
  const dates = [];

  const start = new Date(`${fromDate}T00:00:00`);
  const end = new Date(`${toDate}T00:00:00`);

  if (
    Number.isNaN(start.getTime()) ||
    Number.isNaN(end.getTime()) ||
    start > end
  ) {
    return dates;
  }

  const current = new Date(start);

  while (current <= end) {
    dates.push(
      [
        current.getFullYear(),
        String(current.getMonth() + 1).padStart(2, "0"),
        String(current.getDate()).padStart(2, "0"),
      ].join("-")
    );

    current.setDate(current.getDate() + 1);
  }

  return dates;
}


function chartDateLabel(date) {
  const d = new Date(`${date}T00:00:00`);

  if (Number.isNaN(d.getTime())) {
    return date;
  }

  return d.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
  });
}


function chartNumber(value) {
  const valueNumber = Number(value);

  return Number.isFinite(valueNumber)
    ? valueNumber
    : 0;
}


// ============================================================
// COMMON CHART OPTIONS
// ============================================================

function lineChartOptions(yTitle) {
  return {
    responsive: true,
    maintainAspectRatio: false,

    interaction: {
      mode: "index",
      intersect: false,
    },

    plugins: {
      legend: {
        position: "top",
        labels: {
          usePointStyle: true,
          padding: 16,
        },
      },

      tooltip: {
        callbacks: {
          label: (context) => {
            if (context.raw === null) {
              return `${context.dataset.label}: No data`;
            }

            return `${context.dataset.label}: ${chartNumber(
              context.raw
            ).toLocaleString(undefined, {
              maximumFractionDigits: 0,
            })} ${yTitle}`;
          },
        },
      },
    },

    scales: {
      x: {
        grid: {
          display: false,
        },

        ticks: {
          autoSkip: true,
          maxRotation: 0,
        },
      },

      y: {
        beginAtZero: true,

        title: {
          display: true,
          text: yTitle,
        },
        ticks: {
          callback: (value) => Math.round(Number(value)).toLocaleString(),
        },
      },
    },
  };
}


// ============================================================
// MAIN CHART LOADER
// ============================================================

async function loadCharts() {
  try {
    const fromDate = $("chartFrom").value;
    const toDate = $("chartTo").value;
    const shift = $("chartShift").value;

    if (!fromDate || !toDate) {
      throw Error(
        "Select both From Date and To Date."
      );
    }

    if (fromDate > toDate) {
      throw Error(
        "From Date cannot be after To Date."
      );
    }

    const selectedVessels =
      getSelectedChartVessels();

    if (!selectedVessels.length) {
      destroyCharts();

      $("chartArea").innerHTML = `
        <div class="card chart-empty">
          <h3>Select at least one vessel</h3>
          <p>
            Choose one or more vessels above
            and click Update Charts.
          </p>
        </div>
      `;

      return;
    }

    destroyCharts();

    $("chartArea").innerHTML = `
      <div class="card chart-loading">
        <strong>Loading fuel analytics...</strong>
      </div>
    `;


    // ==========================================================
    // FETCH FUEL DASHBOARD DATA
    // ==========================================================

    const query = new URLSearchParams();

    query.set("from_date", fromDate);
    query.set("to_date", toDate);
    query.set("page_size", "200");

    if (shift) {
      query.set("shift_name", shift);
    }

    const dashboard =
      await api(
        `/api/dashboard/fuel?${query.toString()}`
      );

    const allRows = Array.isArray(dashboard?.rows)
      ? dashboard.rows
      : [];
    for (let page = 2; page <= Number(dashboard?.total_pages || 0); page += 1) {
      query.set("page", String(page));
      const nextPage = await api(`/api/dashboard/fuel?${query.toString()}`);
      if (Array.isArray(nextPage?.rows)) allRows.push(...nextPage.rows);
    }


    // Only selected vessels.
    const selectedSet =
      new Set(selectedVessels.map(Number));

    const rows = allRows.filter(
      (row) =>
        selectedSet.has(
          Number(row.vessel_id)
        )
    );


    const dates =
      buildChartDateRange(
        fromDate,
        toDate
      );


    // ==========================================================
    // NO DATA
    // ==========================================================

    if (!rows.length) {
      $("chartArea").innerHTML = `
        <div class="card chart-empty">
          <h3>No data available</h3>
          <p>
            No fuel records were found for
            the selected vessels and date range.
          </p>
        </div>
      `;

      return;
    }


    // ==========================================================
    // PREPARE DAILY DATA
    // ==========================================================

    const daily = {};

    selectedVessels.forEach((vesselId) => {
      daily[vesselId] = {};

      dates.forEach((date) => {
        daily[vesselId][date] = {
          consumption: null,

          closing: null,

          me: 0,
          meHours: 0,

          aux: 0,
          auxHours: 0,

          dg: 0,
          dgHours: 0,

          hasData: false,
        };
      });
    });


    rows.forEach((row) => {
      const vesselId =
        Number(row.vessel_id);

      const date =
        chartDateKey(row.shift_date);

      if (
        !daily[vesselId] ||
        !date
      ) {
        return;
      }

      if (!daily[vesselId][date]) {
        daily[vesselId][date] = {
          consumption: null,
          closing: null,
          me: 0,
          meHours: 0,
          aux: 0,
          auxHours: 0,
          dg: 0,
          dgHours: 0,
          hasData: false,
        };
      }

      const item =
        daily[vesselId][date];

      item.hasData = true;


      // --------------------------------------------------------
      // Consumption
      // --------------------------------------------------------

      item.consumption =
        (item.consumption ?? 0) +
        chartNumber(
          row.total_engine_consumption
        );


      // --------------------------------------------------------
      // Closing balance
      //
      // If both Morning and Evening exist,
      // the later Evening row becomes the
      // end-of-day closing.
      // --------------------------------------------------------

      const closing =
        row.closing_fuel;

      if (
        closing !== null &&
        closing !== undefined
      ) {
        item.closing =
          chartNumber(closing);
      }


      // --------------------------------------------------------
      // ME
      // --------------------------------------------------------

      item.me +=
        chartNumber(
          row.me_consumption
        );

      item.meHours +=
        chartNumber(
          row.me_hours
        );


      // --------------------------------------------------------
      // AUX
      // --------------------------------------------------------

      item.aux +=
        chartNumber(
          row.aux_consumption
        );

      item.auxHours +=
        chartNumber(
          row.aux_hours
        );


      // --------------------------------------------------------
      // DG
      // --------------------------------------------------------

      item.dg +=
        chartNumber(
          row.dg_consumption
        );

      item.dgHours +=
        chartNumber(
          row.dg_hours
        );
    });


    // ==========================================================
    // CHART AREA
    // ==========================================================

    $("chartArea").innerHTML = `
      <div class="chart-grid">

        <!-- DAILY FUEL CONSUMPTION -->

        <div class="card chart-card chart-card-wide">
          <div class="chart-card-title">
            Daily Fuel Consumption
          </div>

          <div class="chart-card-subtitle">
            Daily engine fuel consumption by vessel
          </div>

          <div class="chart-container">
            <canvas id="dailyFuelChart"></canvas>
          </div>
        </div>


        <!-- L/HR -->

        <div class="card chart-card">
          <div class="chart-card-title">
            L/hr Efficiency
          </div>

          <div class="chart-card-subtitle">
            Calculated engine fuel rate by vessel
          </div>

          <div class="chart-container">
            <canvas id="efficiencyChart"></canvas>
          </div>
        </div>


        <!-- CLOSING -->

        <div class="card chart-card">
          <div class="chart-card-title">
            Closing Fuel Balance
          </div>

          <div class="chart-card-subtitle">
            End-of-day closing fuel by vessel
          </div>

          <div class="chart-container">
            <canvas id="closingBalanceChart"></canvas>
          </div>
        </div>


        <!-- VESSEL COMPARISON -->

        <div class="card chart-card">
          <div class="chart-card-title">
            Vessel Consumption Comparison
          </div>

          <div class="chart-card-subtitle">
            Total engine fuel consumed in selected period
          </div>

          <div class="chart-container">
            <canvas id="vesselConsumptionChart"></canvas>
          </div>
        </div>


        <!-- ENGINE MIX -->

        <div class="card chart-card">
          <div class="chart-card-title">
            Engine Fuel Mix
          </div>

          <div class="chart-card-subtitle">
            ME vs AUX vs DG
          </div>

          <div class="chart-container">
            <canvas id="engineMixChart"></canvas>
          </div>
        </div>

      </div>
    `;


    // ==========================================================
    // 1. DAILY FUEL CONSUMPTION
    // ==========================================================

    const dailyDatasets =
      selectedVessels.map(
        (vesselId, index) => {

          const colour =
            vesselChartColor(
              vesselId,
              index
            );

          return {
            label:
              chartVesselName(
                vesselId
              ),

            data: dates.map((date) => {
              const item =
                daily[vesselId]?.[date];

              if (!item?.hasData) {
                return null;
              }

              return item.consumption;
            }),

            borderColor: colour,
            backgroundColor: colour,

            borderWidth: 2,

            pointRadius: 3,
            pointHoverRadius: 5,

            tension: 0.25,

            fill: false,

            spanGaps: false,
          };
        }
      );


    chartInstances.daily =
      new Chart(
        $("dailyFuelChart"),
        {
          type: "line",

          data: {
            labels:
              dates.map(chartDateLabel),

            datasets:
              dailyDatasets,
          },

          options:
            lineChartOptions("L"),
        }
      );


    // ==========================================================
    // 2. L/HR EFFICIENCY
    // ==========================================================

    const efficiencyValues =
      selectedVessels.map(
        (vesselId) => {

          let litres = 0;
          let hours = 0;

          dates.forEach((date) => {
            const item =
              daily[vesselId]?.[date];

            if (!item?.hasData) {
              return;
            }

            litres +=
              item.me +
              item.aux +
              item.dg;

            hours +=
              item.meHours +
              item.auxHours +
              item.dgHours;
          });

          return hours > 0
            ? litres / hours
            : null;
        }
      );


    chartInstances.efficiency =
      new Chart(
        $("efficiencyChart"),
        {
          type: "bar",

          data: {
            labels:
              selectedVessels.map(
                chartVesselName
              ),

            datasets: [
              {
                label: "Average L/hr",

                data:
                  efficiencyValues,

                backgroundColor:
                  selectedVessels.map(
                    (id) =>
                      vesselChartColor(id)
                  ),

                borderWidth: 0,

                borderRadius: 5,
              },
            ],
          },

          options: {
            responsive: true,
            maintainAspectRatio: false,

            plugins: {
              legend: {
                display: false,
              },

              tooltip: {
                callbacks: {
                  label: (context) => {
                    if (
                      context.raw === null
                    ) {
                      return "No engine data";
                    }

                    return `${
                      Math.round(Number(context.raw)).toLocaleString()
                    } L/hr`;
                  },
                },
              },
            },

            scales: {
              x: {
                grid: {
                  display: false,
                },
              },

              y: {
                beginAtZero: true,

                title: {
                  display: true,
                  text: "L/hr",
                },
                ticks: {
                  callback: (value) => Math.round(Number(value)).toLocaleString(),
                },
              },
            },
          },
        }
      );


    // ==========================================================
    // 3. CLOSING BALANCE
    // ==========================================================

    const closingDatasets =
      selectedVessels.map(
        (vesselId, index) => {

          const colour =
            vesselChartColor(
              vesselId,
              index
            );

          return {
            label:
              chartVesselName(
                vesselId
              ),

            data: dates.map((date) => {
              const item =
                daily[vesselId]?.[date];

              if (
                !item?.hasData ||
                item.closing === null
              ) {
                return null;
              }

              return item.closing;
            }),

            borderColor: colour,
            backgroundColor: colour,

            borderWidth: 2,

            pointRadius: 3,
            pointHoverRadius: 5,

            tension: 0.25,

            fill: false,

            spanGaps: false,
          };
        }
      );


    chartInstances.closing =
      new Chart(
        $("closingBalanceChart"),
        {
          type: "line",

          data: {
            labels:
              dates.map(chartDateLabel),

            datasets:
              closingDatasets,
          },

          options:
            lineChartOptions("L"),
        }
      );


    // ==========================================================
    // 4. VESSEL COMPARISON
    // ==========================================================

    const vesselTotals =
      selectedVessels.map(
        (vesselId) => {

          let total = 0;

          dates.forEach((date) => {
            const item =
              daily[vesselId]?.[date];

            if (!item?.hasData) {
              return;
            }

            total +=
              chartNumber(
                item.consumption
              );
          });

          return {
            id: vesselId,

            name:
              chartVesselName(
                vesselId
              ),

            total,
          };
        }
      );


    chartInstances.comparison =
      new Chart(
        $("vesselConsumptionChart"),
        {
          type: "bar",

          data: {
            labels:
              vesselTotals.map(
                (x) => x.name
              ),

            datasets: [
              {
                label:
                  "Fuel consumption",

                data:
                  vesselTotals.map(
                    (x) => x.total
                  ),

                backgroundColor:
                  vesselTotals.map(
                    (x) =>
                      vesselChartColor(
                        x.id
                      )
                  ),

                borderWidth: 0,

                borderRadius: 5,
              },
            ],
          },

          options: {
            responsive: true,
            maintainAspectRatio: false,

            plugins: {
              legend: {
                display: false,
              },

              tooltip: {
                callbacks: {
                  label: (context) =>
                    `${chartNumber(
                      context.raw
                    ).toLocaleString(undefined, { maximumFractionDigits: 0 })} L`,
                },
              },
            },

            scales: {
              x: {
                grid: {
                  display: false,
                },
              },

              y: {
                beginAtZero: true,

                title: {
                  display: true,
                  text: "Litres",
                },
                ticks: {
                  callback: (value) => Math.round(Number(value)).toLocaleString(),
                },
              },
            },
          },
        }
      );


    // ==========================================================
    // 5. ENGINE MIX
    // ==========================================================

    let meTotal = 0;
    let auxTotal = 0;
    let dgTotal = 0;

    selectedVessels.forEach(
      (vesselId) => {

        dates.forEach((date) => {
          const item =
            daily[vesselId]?.[date];

          if (!item?.hasData) {
            return;
          }

          meTotal += item.me;
          auxTotal += item.aux;
          dgTotal += item.dg;
        });
      }
    );


    const engineTotal =
      meTotal +
      auxTotal +
      dgTotal;


    chartInstances.engineMix =
      new Chart(
        $("engineMixChart"),
        {
          type: "doughnut",

          data: {
            labels: [
              "ME",
              "AUX",
              "DG",
            ],

            datasets: [
              {
                data: [
                  meTotal,
                  auxTotal,
                  dgTotal,
                ],

                backgroundColor: [
                  "#2563eb",
                  "#059669",
                  "#d97706",
                ],

                borderWidth: 2,
              },
            ],
          },

          options: {
            responsive: true,
            maintainAspectRatio: false,

            cutout: "62%",

            plugins: {
              legend: {
                position: "bottom",

                labels: {
                  usePointStyle: true,
                  padding: 18,
                },
              },

              tooltip: {
                callbacks: {
                  label: (context) => {
                    const value =
                      chartNumber(
                        context.raw
                      );

                    const percentage =
                      engineTotal > 0
                        ? (
                            value /
                            engineTotal *
                            100
                          ).toFixed(1)
                        : "0.0";

                    return `${
                      context.label
                    }: ${
                      value.toLocaleString(undefined, { maximumFractionDigits: 0 })
                    } L (${
                      percentage
                    }%)`;
                  },
                },
              },
            },
          },
        }
      );


  } catch (e) {

    destroyCharts();

    const area =
      $("chartArea");

    if (area) {
      area.innerHTML = `
        <div class="card chart-error">
          <div class="note note-err">
            ${esc(e.message)}
          </div>
        </div>
      `;
    }
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
  // -----------------------------
  // PROJECTS
  // -----------------------------
  table(
    "projectsList",
    ["ID", "Name", "Code", "Description", "Status", "Actions"],
    projects.map((x) => [
      x.id,
      esc(x.name),
      esc(x.code),
      esc(x.description || ""),
      `<button
        class="btn btn-sm ${x.is_active ? "btn-success" : "btn-danger"}"
        onclick="toggleProjectActive(${x.id}, ${x.is_active})">
        ${x.is_active ? "Active" : "Inactive"}
      </button>`,
      `<button
        class="btn btn-sm btn-warn"
        onclick="editProject(${x.id})">
        Edit
      </button>`,
    ]),
  );


    // -----------------------------
  // SITES
  // -----------------------------
  table(
    "sitesList",
    ["Project", "Site", "Code", "Status", "Actions"],
    sites.map((x) => {
      const project = projects.find(
        (p) => Number(p.id) === Number(x.project_id),
      );

      return [
        project
          ? `${esc(project.name)} (${esc(project.code)})`
          : `Project ${x.project_id}`,
        esc(x.name),
        esc(x.site_code),
        `<button
          class="btn btn-sm ${x.is_active ? "btn-success" : "btn-danger"}"
          onclick="toggleSiteActive(${x.id}, ${x.is_active})">
          ${x.is_active ? "Active" : "Inactive"}
        </button>`,
        `<button
          class="btn btn-sm btn-warn"
          onclick="editSite(${x.id})">
          Edit
        </button>`,
      ];
    }),
  );


  // -----------------------------
  // VESSELS
  // -----------------------------
  table(
    "vesselsList",
    ["ID", "Project", "Site", "Vessel", "Code", "Type", "Manual min. (L)", "Status", "Actions"],
    vessels.map((x) => {
      const project = projects.find(
        (p) => Number(p.id) === Number(x.project_id),
      );

      const site = sites.find(
        (s) => Number(s.id) === Number(x.site_id),
      );

      return [
        x.id,
        project
          ? `${esc(project.name)} (${esc(project.code)})`
          : `Project ${x.project_id}`,
        site
          ? `${esc(site.name)} (${esc(site.site_code)})`
          : "No site assigned",
        esc(x.name),
        esc(x.code),
        esc(x.vessel_type),
        litres(x.fuel_threshold_litres),
        `<button
          class="btn btn-sm ${x.is_active ? "btn-success" : "btn-danger"}"
          onclick="toggleVesselActive(${x.id}, ${x.is_active})">
          ${x.is_active ? "Active" : "Inactive"}
        </button>`,
        `<button
          class="btn btn-sm btn-warn"
          onclick="editVessel(${x.id})">
          Edit
        </button>`,
      ];
    }),
  );

  // -----------------------------
  // EQUIPMENT
  // -----------------------------
  table(
    "equipmentList",
    ["ID", "Vessel", "Equipment", "Type", "Code", "Status", "Actions"],
    equipment.map((x) => [
      x.id,
      chartVesselCode(x.vessel_id),
      esc(x.name),
      esc(x.equipment_type),
      esc(x.code),
      `<button
        class="btn btn-sm ${x.is_active ? "btn-success" : "btn-danger"}"
        onclick="toggleEquipmentActive(${x.id}, ${x.is_active})">
        ${x.is_active ? "Active" : "Inactive"}
      </button>`,
      `<button
        class="btn btn-sm btn-warn"
        onclick="editEquipment(${x.id})">
        Edit
      </button>`,
    ]),
  );
}


// ============================================================
// PROJECTS
// ============================================================

function addProject() {
  const tableEl = document.querySelector("#projectsList table");
  if (!tableEl) return;

  const tbody = tableEl.querySelector("tbody");
  if (!tbody) return;

  // Prevent multiple add rows
  if (tbody.querySelector(".new-project-row")) return;

  const row = document.createElement("tr");
  row.className = "new-project-row";

  row.innerHTML = `
    <td>New</td>
    <td>
      <input
        type="text"
        id="newProjectName"
        placeholder="Project name"
      />
    </td>
    <td>
      <input
        type="text"
        id="newProjectCode"
        placeholder="Code"
      />
    </td>
    <td>
      <input
        type="text"
        id="newProjectDescription"
        placeholder="Description"
      />
    </td>
    <td>
      <button
        class="btn btn-sm btn-success"
        onclick="saveNewProject()">
        Save
      </button>
    </td>
    <td>
      <button
        class="btn btn-sm"
        onclick="renderMasters()">
        Cancel
      </button>
    </td>
  `;

  tbody.prepend(row);

  document.querySelector("#newProjectName")?.focus();
}


async function saveNewProject() {
  try {
    const name = document.querySelector("#newProjectName")?.value.trim();
    const code = document.querySelector("#newProjectCode")?.value.trim();
    const description =
      document.querySelector("#newProjectDescription")?.value.trim();

    if (!name) {
      throw Error("Project name is required.");
    }

    if (!code) {
      throw Error("Project code is required.");
    }

    await api("/api/projects", {
      method: "POST",
      body: JSON.stringify({
        name,
        code,
        description: description || null,
      }),
    });

    message("Project created successfully.", "success");

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}


async function editProject(id) {
  const project = projects.find(
    (x) => Number(x.id) === Number(id),
  );

  if (!project) {
    message("Project not found.", "error");
    return;
  }

  const tableEl = document.querySelector("#projectsList table");
  if (!tableEl) return;

  const rows = Array.from(
    tableEl.querySelectorAll("tbody tr"),
  );

  const row = rows.find(
    (r) => r.children[0]?.textContent.trim() === String(id),
  );

  if (!row) return;

  row.innerHTML = `
    <td>${project.id}</td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="editProjectName_${id}"
        value="${esc(project.name || "")}"
      />
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="editProjectCode_${id}"
        value="${esc(project.code || "")}"
      />
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="editProjectDescription_${id}"
        value="${esc(project.description || "")}"
      />
    </td>

    <td>
      <select
        class="master-inline-input"
        id="editProjectStatus_${id}">
        <option value="true" ${project.is_active ? "selected" : ""}>
          Active
        </option>
        <option value="false" ${!project.is_active ? "selected" : ""}>
          Inactive
        </option>
      </select>
    </td>

    <td>
      <button
        class="btn btn-sm btn-success"
        onclick="saveProject(${id})">
        Save
      </button>

      <button
        class="btn btn-sm"
        onclick="renderMasters()">
        Cancel
      </button>
    </td>
  `;

  document
    .querySelector(`#editProjectName_${id}`)
    ?.focus();
}


async function saveProject(id) {
  try {
    const name = document
      .querySelector(`#editProjectName_${id}`)
      ?.value.trim();

    const code = document
      .querySelector(`#editProjectCode_${id}`)
      ?.value.trim();

    const description = document
      .querySelector(`#editProjectDescription_${id}`)
      ?.value.trim();

    const isActive =
      document
        .querySelector(`#editProjectStatus_${id}`)
        ?.value === "true";

    if (!name) {
      throw Error("Project name is required.");
    }

    if (!code) {
      throw Error("Project code is required.");
    }

    const confirmed = confirm(
      `Save changes to project "${name}"?`,
    );

    if (!confirmed) return;

    await api(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name,
        code,
        description: description || null,
        is_active: isActive,
      }),
    });

    message("Project updated successfully.", "success");

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}


async function toggleProjectActive(id, currentlyActive) {
  const project = projects.find(
    (x) => Number(x.id) === Number(id),
  );

  if (!project) {
    message("Project not found.", "error");
    return;
  }

  const newStatus = !currentlyActive;

  const confirmed = confirm(
    `${newStatus ? "Activate" : "Deactivate"} project "${project.name}"?`,
  );

  if (!confirmed) return;

  try {
    await api(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: project.name,
        code: project.code,
        description: project.description || null,
        is_active: newStatus,
      }),
    });

    message(
      `Project "${project.name}" is now ${
        newStatus ? "Active" : "Inactive"
      }.`,
      "success",
    );

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}



// ============================================================
// SITES
// ============================================================

function addSite() {
  const tableEl = document.querySelector("#sitesList table");
  if (!tableEl) return;

  const tbody = tableEl.querySelector("tbody");
  if (!tbody) return;

  // Prevent multiple add rows
  if (tbody.querySelector(".new-site-row")) return;

  const projectOptions = projects
    .filter((p) => p.is_active !== false)
    .map(
      (p) => `
        <option value="${p.id}">
          ${esc(p.name)} (${esc(p.code)})
        </option>
      `,
    )
    .join("");

  const row = document.createElement("tr");
  row.className = "new-site-row";

  row.innerHTML = `
    <td>
      <select
        class="master-inline-input"
        id="newSiteProject">
        <option value="">Select Project</option>
        ${projectOptions}
      </select>
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="newSiteName"
        placeholder="Site name"
      />
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="newSiteCode"
        placeholder="Site code"
      />
    </td>

    <td>
      <span class="muted">Active</span>
    </td>

    <td>
      <button
        class="btn btn-sm btn-success"
        onclick="saveNewSite()">
        Save
      </button>

      <button
        class="btn btn-sm"
        onclick="renderMasters()">
        Cancel
      </button>
    </td>
  `;

  tbody.prepend(row);

  document.querySelector("#newSiteProject")?.focus();
}


async function saveNewSite() {
  try {
    const projectId = Number(
      document.querySelector("#newSiteProject")?.value,
    );

    const name =
      document.querySelector("#newSiteName")?.value.trim();

    const siteCode =
      document.querySelector("#newSiteCode")?.value.trim();

    if (!Number.isInteger(projectId) || projectId <= 0) {
      throw Error("Please select a project.");
    }

    if (!name) {
      throw Error("Site name is required.");
    }

    if (!siteCode) {
      throw Error("Site code is required.");
    }

    await api("/api/sites", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        name,
        site_code: siteCode,
        is_active: true,
      }),
    });

    message("Site created successfully.", "success");

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}


async function editSite(id) {
  const site = sites.find(
    (x) => Number(x.id) === Number(id),
  );

  if (!site) {
    message("Site not found.", "error");
    return;
  }

  const tableEl = document.querySelector("#sitesList table");
  if (!tableEl) return;

  const rows = Array.from(
    tableEl.querySelectorAll("tbody tr"),
  );

  const row = rows.find((r) => {
    const editButton = r.querySelector(
      `button[onclick="editSite(${id})"]`,
    );

    return !!editButton;
  });

  if (!row) return;

  const projectOptions = projects
    .filter((p) => p.is_active !== false || Number(p.id) === Number(site.project_id))
    .map(
      (p) => `
        <option
          value="${p.id}"
          ${Number(p.id) === Number(site.project_id) ? "selected" : ""}>
          ${esc(p.name)} (${esc(p.code)})
        </option>
      `,
    )
    .join("");

  row.innerHTML = `
    <td>
      <select
        class="master-inline-input"
        id="editSiteProject_${id}">
        ${projectOptions}
      </select>
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="editSiteName_${id}"
        value="${esc(site.name || "")}"
      />
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="editSiteCode_${id}"
        value="${esc(site.site_code || "")}"
      />
    </td>

    <td>
      <select
        class="master-inline-input"
        id="editSiteStatus_${id}">
        <option
          value="true"
          ${site.is_active ? "selected" : ""}>
          Active
        </option>

        <option
          value="false"
          ${!site.is_active ? "selected" : ""}>
          Inactive
        </option>
      </select>
    </td>

    <td>
      <button
        class="btn btn-sm btn-success"
        onclick="saveSite(${id})">
        Save
      </button>

      <button
        class="btn btn-sm"
        onclick="renderMasters()">
        Cancel
      </button>
    </td>
  `;

  document
    .querySelector(`#editSiteName_${id}`)
    ?.focus();
}


async function saveSite(id) {
  try {
    const projectId = Number(
      document.querySelector(`#editSiteProject_${id}`)?.value,
    );

    const name = document
      .querySelector(`#editSiteName_${id}`)
      ?.value.trim();

    const siteCode = document
      .querySelector(`#editSiteCode_${id}`)
      ?.value.trim();

    const isActive =
      document.querySelector(`#editSiteStatus_${id}`)?.value ===
      "true";

    if (!Number.isInteger(projectId) || projectId <= 0) {
      throw Error("Please select a project.");
    }

    if (!name) {
      throw Error("Site name is required.");
    }

    if (!siteCode) {
      throw Error("Site code is required.");
    }

    const confirmed = confirm(
      `Save changes to site "${name}"?`,
    );

    if (!confirmed) return;

    await api(`/api/sites/${id}`, {
      method: "PUT",
      body: JSON.stringify({
        project_id: projectId,
        name,
        site_code: siteCode,
        is_active: isActive,
      }),
    });

    message("Site updated successfully.", "success");

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}


async function toggleSiteActive(id, currentlyActive) {
  const site = sites.find(
    (x) => Number(x.id) === Number(id),
  );

  if (!site) {
    message("Site not found.", "error");
    return;
  }

  const newStatus = !currentlyActive;

  const confirmed = confirm(
    `${newStatus ? "Activate" : "Deactivate"} site "${site.name}"?`,
  );

  if (!confirmed) return;

  try {
    await api(`/api/sites/${id}`, {
      method: "PUT",
      body: JSON.stringify({
        project_id: site.project_id,
        name: site.name,
        site_code: site.site_code,
        is_active: newStatus,
      }),
    });

    message(
      `Site "${site.name}" is now ${
        newStatus ? "Active" : "Inactive"
      }.`,
      "success",
    );

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}


// ============================================================
// VESSELS
// ============================================================
const VESSEL_TYPES = [
  "Dredger",
  "Tug Boat",
  "Survey Boat",
  "House Boat",
  "Wooden Boat",
  "Steel Boat",
  "Fiber Boat",
  "Dredge Pump Boat",
  "Tanker",
];


function addVessel() {
  const tableEl = document.querySelector("#vesselsList table");
  if (!tableEl) return;

  const tbody = tableEl.querySelector("tbody");
  if (!tbody) return;

  if (tbody.querySelector(".new-vessel-row")) return;

  const projectOptions = projects
    .filter((p) => p.is_active !== false)
    .map(
      (p) =>
        `<option value="${p.id}">
          ${esc(p.name)} (${esc(p.code)})
        </option>`,
    )
    .join("");

  const typeOptions = VESSEL_TYPES
    .map(
      (type) =>
        `<option value="${esc(type)}">${esc(type)}</option>`,
    )
    .join("");

  const row = document.createElement("tr");
  row.className = "new-vessel-row";

  row.innerHTML = `
    <td>New</td>

    <td>
      <select
        id="newVesselProject"
        onchange="populateNewVesselSites()">
        <option value="">Select Project</option>
        ${projectOptions}
      </select>
    </td>

    <td>
      <select id="newVesselSite">
        <option value="">Select Project First</option>
      </select>
    </td>

    <td>
      <input
        type="text"
        id="newVesselName"
        placeholder="Vessel name"
      />
    </td>

    <td>
      <input
        type="text"
        id="newVesselCode"
        placeholder="Required code"
      />
    </td>

    <td>
      <select id="newVesselType">
        <option value="">Select Type</option>
        ${typeOptions}
      </select>
    </td>

    <td>
      <input
        type="number"
        id="newVesselThreshold"
        min="0"
        step="0.001"
        value="0"
      />
    </td>

    <td>
      <select id="newVesselStatus">
        <option value="true">Active</option>
        <option value="false">Inactive</option>
      </select>
    </td>

    <td>
      <button
        class="btn btn-sm btn-success"
        onclick="saveNewVessel()">
        Save
      </button>

      <button
        class="btn btn-sm"
        onclick="renderMasters()">
        Cancel
      </button>
    </td>
  `;

  tbody.prepend(row);

  document.querySelector("#newVesselName")?.focus();
}

function populateNewVesselSites() {
  const projectId = Number(
    document.querySelector("#newVesselProject")?.value,
  );

  const siteSelect = document.querySelector("#newVesselSite");

  if (!siteSelect) return;

  if (!projectId) {
    siteSelect.innerHTML =
      `<option value="">Select Project First</option>`;
    return;
  }

  const projectSites = sites
    .filter(
      (s) =>
        Number(s.project_id) === projectId &&
        s.is_active !== false,
    )
    .sort((a, b) =>
      String(a.name).localeCompare(String(b.name)),
    );

  siteSelect.innerHTML =
    `<option value="">Select Site</option>` +
    projectSites
      .map(
        (s) =>
          `<option value="${s.id}">
            ${esc(s.name)} (${esc(s.site_code)})
          </option>`,
      )
      .join("");
}

async function saveNewVessel() {
  try {
    const projectId = Number(
      document.querySelector("#newVesselProject")?.value,
    );

    const siteId = Number(
      document.querySelector("#newVesselSite")?.value,
    );

    const name = document
      .querySelector("#newVesselName")
      ?.value.trim();

    const code = document
      .querySelector("#newVesselCode")
      ?.value.trim();

    const vesselType = document
      .querySelector("#newVesselType")
      ?.value;

    const threshold = Number(
      document.querySelector("#newVesselThreshold")?.value,
    );

    const isActive =
      document.querySelector("#newVesselStatus")?.value === "true";

    if (!Number.isInteger(projectId) || projectId <= 0) {
      throw Error("Please select a project.");
    }

    if (!Number.isInteger(siteId) || siteId <= 0) {
      throw Error("Please select a site.");
    }

    if (!name) {
      throw Error("Vessel name is required.");
    }

    if (!code) {
      throw Error("Vessel code is required.");
    }

    if (!vesselType) {
      throw Error("Please select a vessel type.");
    }

    if (!Number.isFinite(threshold) || threshold < 0) {
      throw Error("Invalid fuel threshold.");
    }

    await api("/api/vessels", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        site_id: siteId,
        name,
        code,
        vessel_type: vesselType,
        is_active: isActive,
        fuel_threshold_litres: threshold,
      }),
    });

    message("Vessel created successfully.", "success");

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}


async function editVessel(id) {
  const vessel = vessels.find(
    (x) => Number(x.id) === Number(id),
  );

  if (!vessel) {
    message("Vessel not found.", "error");
    return;
  }

  const tableEl = document.querySelector("#vesselsList table");
  if (!tableEl) return;

  const rows = Array.from(
    tableEl.querySelectorAll("tbody tr"),
  );

  const row = rows.find(
    (r) => r.children[0]?.textContent.trim() === String(id),
  );

  if (!row) return;

  const projectOptions = projects
    .map(
      (p) =>
        `<option
          value="${p.id}"
          ${Number(p.id) === Number(vessel.project_id) ? "selected" : ""}>
          ${esc(p.name)} (${esc(p.code)})
        </option>`,
    )
    .join("");

  const siteOptions = sites
    .filter(
      (s) =>
        Number(s.project_id) === Number(vessel.project_id) &&
        s.is_active !== false,
    )
    .map(
      (s) =>
        `<option
          value="${s.id}"
          ${Number(s.id) === Number(vessel.site_id) ? "selected" : ""}>
          ${esc(s.name)} (${esc(s.site_code)})
        </option>`,
    )
    .join("");

  const typeOptions = VESSEL_TYPES
    .map(
      (type) =>
        `<option
          value="${esc(type)}"
          ${type === vessel.vessel_type ? "selected" : ""}>
          ${esc(type)}
        </option>`,
    )
    .join("");

  row.innerHTML = `
    <td>${vessel.id}</td>

    <td>
      <select
        class="master-inline-input"
        id="editVesselProject_${id}"
        onchange="populateEditVesselSites(${id})">
        ${projectOptions}
      </select>
    </td>

    <td>
      <select
        class="master-inline-input"
        id="editVesselSite_${id}">
        <option value="">Select Site</option>
        ${siteOptions}
      </select>
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="editVesselName_${id}"
        value="${esc(vessel.name || "")}"
      />
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="editVesselCode_${id}"
        value="${esc(vessel.code || "")}"
      />
    </td>

    <td>
      <select
        class="master-inline-input"
        id="editVesselType_${id}">
        <option value="">Select Type</option>
        ${typeOptions}
      </select>
    </td>

    <td>
      <input
        type="number"
        class="master-inline-input"
        id="editVesselThreshold_${id}"
        min="0"
        step="0.001"
        value="${vessel.fuel_threshold_litres ?? 0}"
      />
    </td>

    <td>
      <select
        class="master-inline-input"
        id="editVesselStatus_${id}">
        <option value="true" ${vessel.is_active ? "selected" : ""}>
          Active
        </option>
        <option value="false" ${!vessel.is_active ? "selected" : ""}>
          Inactive
        </option>
      </select>
    </td>

    <td>
      <button
        class="btn btn-sm btn-success"
        onclick="saveVessel(${id})">
        Save
      </button>

      <button
        class="btn btn-sm"
        onclick="renderMasters()">
        Cancel
      </button>
    </td>
  `;

  document
    .querySelector(`#editVesselName_${id}`)
    ?.focus();
}
function populateEditVesselSites(id) {
  const projectId = Number(
    document.querySelector(`#editVesselProject_${id}`)?.value,
  );

  const siteSelect = document.querySelector(
    `#editVesselSite_${id}`,
  );

  if (!siteSelect) return;

  if (!projectId) {
    siteSelect.innerHTML =
      `<option value="">Select Site</option>`;
    return;
  }

  const projectSites = sites
    .filter(
      (s) =>
        Number(s.project_id) === projectId &&
        s.is_active !== false,
    )
    .sort((a, b) =>
      String(a.name).localeCompare(String(b.name)),
    );

  siteSelect.innerHTML =
    `<option value="">Select Site</option>` +
    projectSites
      .map(
        (s) =>
          `<option value="${s.id}">
            ${esc(s.name)} (${esc(s.site_code)})
          </option>`,
      )
      .join("");
}


async function saveVessel(id) {
  try {
    const projectId = Number(
      document.querySelector(`#editVesselProject_${id}`)?.value,
    );

    const siteId = Number(
      document.querySelector(`#editVesselSite_${id}`)?.value,
    );

    const name = document
      .querySelector(`#editVesselName_${id}`)
      ?.value.trim();

    const code = document
      .querySelector(`#editVesselCode_${id}`)
      ?.value.trim();

    const vesselType = document
      .querySelector(`#editVesselType_${id}`)
      ?.value;

    const threshold = Number(
      document.querySelector(`#editVesselThreshold_${id}`)?.value,
    );

    const isActive =
      document
        .querySelector(`#editVesselStatus_${id}`)
        ?.value === "true";

    if (!Number.isInteger(projectId) || projectId <= 0) {
      throw Error("Please select a project.");
    }

    if (!Number.isInteger(siteId) || siteId <= 0) {
      throw Error("Please select a site.");
    }

    if (!name) {
      throw Error("Vessel name is required.");
    }

    if (!code) {
      throw Error("Vessel code is required.");
    }

    if (!vesselType) {
      throw Error("Please select a vessel type.");
    }

    if (!Number.isFinite(threshold) || threshold < 0) {
      throw Error("Invalid fuel threshold.");
    }

    const confirmed = confirm(
      `Save changes to vessel "${name}"?`,
    );

    if (!confirmed) return;

    await api(`/api/vessels/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        project_id: projectId,
        site_id: siteId,
        name,
        code,
        vessel_type: vesselType,
        is_active: isActive,
        fuel_threshold_litres: threshold,
      }),
    });

    message("Vessel updated successfully.", "success");

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}


async function toggleVesselActive(id, currentlyActive) {
  const vessel = vessels.find(
    (x) => Number(x.id) === Number(id),
  );

  if (!vessel) {
    message("Vessel not found.", "error");
    return;
  }

  const newStatus = !currentlyActive;

  const confirmed = confirm(
    `${newStatus ? "Activate" : "Deactivate"} vessel "${vessel.name}"?`,
  );

  if (!confirmed) return;

  try {
        await api(`/api/vessels/${id}`, {
          method: "PATCH",
          body: JSON.stringify({
            project_id: vessel.project_id,
            site_id: vessel.site_id,
            name: vessel.name,
            code: vessel.code,
            vessel_type: vessel.vessel_type,
            is_active: newStatus,
            fuel_threshold_litres:
              Number(vessel.fuel_threshold_litres || 0),
          }),
        });

    message(
      `Vessel "${vessel.name}" is now ${
        newStatus ? "Active" : "Inactive"
      }.`,
      "success",
    );

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}


// ============================================================
// EQUIPMENT
// ============================================================

function addEquipment() {
  const tableEl = document.querySelector("#equipmentList table");
  if (!tableEl) return;

  const tbody = tableEl.querySelector("tbody");
  if (!tbody) return;

  if (tbody.querySelector(".new-equipment-row")) return;

  const vesselOptions = vessels
    .filter((v) => v.is_active !== false)
    .map(
      (v) =>
        `<option value="${v.id}">
          ${esc(v.name)}
        </option>`,
    )
    .join("");

  const row = document.createElement("tr");
  row.className = "new-equipment-row";

  row.innerHTML = `
    <td>New</td>

    <td>
      <select id="newEquipmentVessel">
        <option value="">Select Vessel</option>
        ${vesselOptions}
      </select>
    </td>

    <td>
      <input
        type="text"
        id="newEquipmentName"
        placeholder="Equipment name"
      />
    </td>

    <td>
      <input
        type="text"
        id="newEquipmentType"
        placeholder="Equipment type"
      />
    </td>

    <td>
      <input
        type="text"
        id="newEquipmentCode"
        placeholder="Equipment code"
      />
    </td>

    <td>
      <select id="newEquipmentStatus">
        <option value="true">Active</option>
        <option value="false">Inactive</option>
      </select>
    </td>

    <td>
      <button
        class="btn btn-sm btn-success"
        onclick="saveNewEquipment()">
        Save
      </button>

      <button
        class="btn btn-sm"
        onclick="renderMasters()">
        Cancel
      </button>
    </td>
  `;

  tbody.prepend(row);

  document.querySelector("#newEquipmentName")?.focus();
}


async function saveNewEquipment() {
  try {
    const vesselId = Number(
      document.querySelector("#newEquipmentVessel")?.value,
    );

    const name = document
      .querySelector("#newEquipmentName")
      ?.value.trim();

    const equipmentType = document
      .querySelector("#newEquipmentType")
      ?.value.trim();

    const code = document
      .querySelector("#newEquipmentCode")
      ?.value.trim();

    if (!Number.isInteger(vesselId) || vesselId <= 0) {
      throw Error("Please select a vessel.");
    }

    if (!name) {
      throw Error("Equipment name is required.");
    }

    if (!equipmentType) {
      throw Error("Equipment type is required.");
    }

    if (!code) {
      throw Error("Equipment code is required.");
    }

    await api("/api/equipment", {
      method: "POST",
      body: JSON.stringify({
        vessel_id: vesselId,
        name,
        equipment_type: equipmentType,
        code,
      }),
    });

    message("Equipment created successfully.", "success");

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}


async function editEquipment(id) {
  const equipmentItem = equipment.find(
    (x) => Number(x.id) === Number(id),
  );

  if (!equipmentItem) {
    message("Equipment not found.", "error");
    return;
  }

  const tableEl = document.querySelector("#equipmentList table");
  if (!tableEl) return;

  const rows = Array.from(
    tableEl.querySelectorAll("tbody tr"),
  );

  const row = rows.find(
    (r) => r.children[0]?.textContent.trim() === String(id),
  );

  if (!row) return;

  const vesselOptions = vessels
    .map(
      (v) =>
        `<option
          value="${v.id}"
          ${Number(v.id) === Number(equipmentItem.vessel_id) ? "selected" : ""}>
          ${esc(v.name)}
        </option>`,
    )
    .join("");

  row.innerHTML = `
    <td>${equipmentItem.id}</td>

    <td>
      <select
        class="master-inline-input"
        id="editEquipmentVessel_${id}">
        ${vesselOptions}
      </select>
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="editEquipmentName_${id}"
        value="${esc(equipmentItem.name || "")}"
      />
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="editEquipmentType_${id}"
        value="${esc(equipmentItem.equipment_type || "")}"
      />
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="editEquipmentCode_${id}"
        value="${esc(equipmentItem.code || "")}"
      />
    </td>

    <td>
      <select
        class="master-inline-input"
        id="editEquipmentStatus_${id}">
        <option value="true" ${equipmentItem.is_active ? "selected" : ""}>
          Active
        </option>
        <option value="false" ${!equipmentItem.is_active ? "selected" : ""}>
          Inactive
        </option>
      </select>
    </td>

    <td>
      <button
        class="btn btn-sm btn-success"
        onclick="saveEquipment(${id})">
        Save
      </button>

      <button
        class="btn btn-sm"
        onclick="renderMasters()">
        Cancel
      </button>
    </td>
  `;

  document
    .querySelector(`#editEquipmentName_${id}`)
    ?.focus();
}


async function saveEquipment(id) {
  try {
    const vesselId = Number(
      document.querySelector(`#editEquipmentVessel_${id}`)?.value,
    );

    const name = document
      .querySelector(`#editEquipmentName_${id}`)
      ?.value.trim();

    const equipmentType = document
      .querySelector(`#editEquipmentType_${id}`)
      ?.value.trim();

    const code = document
      .querySelector(`#editEquipmentCode_${id}`)
      ?.value.trim();

    const isActive =
      document
        .querySelector(`#editEquipmentStatus_${id}`)
        ?.value === "true";

    if (!Number.isInteger(vesselId) || vesselId <= 0) {
      throw Error("Please select a vessel.");
    }

    if (!name) {
      throw Error("Equipment name is required.");
    }

    if (!equipmentType) {
      throw Error("Equipment type is required.");
    }

    if (!code) {
      throw Error("Equipment code is required.");
    }

    const confirmed = confirm(
      `Save changes to equipment "${name}"?`,
    );

    if (!confirmed) return;

    await api(`/api/equipment/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        vessel_id: vesselId,
        name,
        equipment_type: equipmentType,
        code,
        is_active: isActive,
      }),
    });

    message("Equipment updated successfully.", "success");

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}


async function toggleEquipmentActive(id, currentlyActive) {
  const equipmentItem = equipment.find(
    (x) => Number(x.id) === Number(id),
  );

  if (!equipmentItem) {
    message("Equipment not found.", "error");
    return;
  }

  const newStatus = !currentlyActive;

  const confirmed = confirm(
    `${newStatus ? "Activate" : "Deactivate"} equipment "${equipmentItem.name}"?`,
  );

  if (!confirmed) return;

  try {
    await api(`/api/equipment/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        vessel_id: equipmentItem.vessel_id,
        name: equipmentItem.name,
        equipment_type: equipmentItem.equipment_type,
        code: equipmentItem.code,
        is_active: newStatus,
      }),
    });

    message(
      `Equipment "${equipmentItem.name}" is now ${
        newStatus ? "Active" : "Inactive"
      }.`,
      "success",
    );

    await loadMaster();
  } catch (e) {
    message(e.message, "error");
  }
}
// ============================================================
// AUDIT LOG
// ============================================================

let auditOffset = 0;
const AUDIT_PAGE_SIZE = 100;

let auditUsers = [];


// ============================================================
// LOAD AUDIT USERS
// ============================================================

async function loadAuditUsers() {
  try {
    auditUsers = await api("/api/users");

    const selectEl = $("auditUser");

    if (!selectEl) {
      return;
    }

    selectEl.innerHTML = `
      <option value="">All users</option>
      ${auditUsers
        .map(
          (user) => `
            <option value="${user.id}">
              ${esc(user.username || `User ${user.id}`)}
            </option>
          `
        )
        .join("")}
    `;

  } catch (e) {
    console.warn("Could not load audit users:", e);
  }
}


// ============================================================
// GET USER NAME
// ============================================================

function auditUserName(userId) {
  if (userId === null || userId === undefined) {
    return "System";
  }

  const user = auditUsers.find(
    (x) => Number(x.id) === Number(userId)
  );

  if (user) {
    return user.username || `User ${userId}`;
  }

  return `User ${userId}`;
}


// ============================================================
// FORMAT AUDIT JSON
// ============================================================

function formatAuditJson(value) {
  if (
    value === null ||
    value === undefined
  ) {
    return "—";
  }

  try {
    return esc(
      JSON.stringify(
        value,
        null,
        2
      )
    );
  } catch (_) {
    return esc(String(value));
  }
}


// ============================================================
// ADMIN SHIFT MANAGEMENT
// ============================================================
async function loadAdminShifts() {
  try {
    if (me.role !== "ADMIN") {
      throw Error("Only an administrator can manage shifts.");
    }
    if (!confirmAdminEditorDiscard()) return;

    const vesselId = $("adminShiftVessel").value;
    const query = params({
      from_date: $("adminShiftFrom").value,
      to_date: $("adminShiftTo").value,
      vessel_id: vesselId,
      shift_name: $("adminShiftName").value,
      shift_status: $("adminShiftStatus").value,
    });

    adminSelectedShift = undefined;
    $("adminShiftSearchStatus").textContent = "Searching shifts...";
    $("adminShiftDetails").classList.add("hidden");

    const shifts = await api(`/api/fuel/admin/shifts?${query}`);

    table(
      "adminShiftResults",
      ["Date", "Vessel", "Shift", "Status", ""],
      shifts.map((shift) => [
        esc(shift.shift_date),
        esc(
          vessels.find((item) => Number(item.id) === Number(shift.vessel_id))?.name ||
          `Vessel #${shift.vessel_id}`,
        ),
        esc(shift.shift_name),
        esc(shift.status),
        `<button class="btn btn-sm" onclick="viewAdminShift(${shift.id})">View</button>`,
      ]),
    );
    $("adminShiftSearchStatus").textContent = shifts.length
      ? `${shifts.length} shift${shifts.length === 1 ? "" : "s"} found.`
      : "No shifts match the selected filters.";
  } catch (e) {
    $("adminShiftSearchStatus").textContent = e.message;
    message(e.message, "error");
  }
}

async function viewAdminShift(shiftId, skipUnsavedPrompt = false) {
  try {
    if (me.role !== "ADMIN") {
      throw Error("Only an administrator can view shift management.");
    }
    if (!skipUnsavedPrompt && !confirmAdminEditorDiscard()) return;

    const [report, engineEvents, soundings] = await Promise.all([
      api(`/api/fuel/shift/${shiftId}/report`),
      api(`/api/engine/events?shift_id=${shiftId}`),
      api(`/api/soundings?shift_id=${shiftId}`),
    ]);
    const shift = report.shift;
    adminSelectedShift = shift;
    adminFuelTransactions = report.transactions || [];
    const [outgoingTransfers, incomingTransfers] = await Promise.all([
      api(`/api/transfers?from_vessel_id=${shift.vessel_id}`),
      api(`/api/transfers?to_vessel_id=${shift.vessel_id}`),
    ]);
    const allTransfers = [...outgoingTransfers, ...incomingTransfers];
    $("adminShiftDetails").classList.remove("hidden");

    const vessel = vessels.find((item) => item.id === shift.vessel_id);
    const project = projects.find((item) => item.id === vessel?.project_id);
    const site = sites.find((item) => item.id === vessel?.site_id);
    const balance = report.balance;
    table("adminShiftSummary", ["Stored field", "Value"], [
      ["Date", esc(shift.shift_date)],
      ["Vessel", esc(vessel?.name || `Vessel #${shift.vessel_id}`)],
      ["Project", esc(project?.name || "-")],
      ["Site", esc(site?.name || "-")],
      ["Shift", esc(shift.shift_name)],
      ["Status", esc(shift.status)],
      ["Opening fuel", `${litres(shift.opening_fuel)} L`],
      ["Calculated closing fuel", `${litres(shift.calculated_closing_fuel)} L`],
      ["Calculated current balance", `${litres(balance.closing_fuel)} L`],
      ["Advancement", shift.advancement_m == null ? "—" : `${esc(shift.advancement_m)} m`],
      ["Dredging hours", shift.dredging_hours == null ? "—" : `${esc(shift.dredging_hours)} hr`],
      ["Created", esc(formatDateTime(shift.created_at))],
      ["Closed", esc(formatDateTime(shift.closed_at))],
    ]);
    $("adminShiftOperationalCard").classList.toggle("hidden", shift.status !== "OPEN");
    $("adminShiftCloseCard").classList.toggle("hidden", shift.status !== "OPEN");
    $("adminOpeningFuelCard").classList.toggle("hidden", shift.status !== "OPEN");
    $("adminOpeningFuelCurrent").value = shift.opening_fuel;
    $("adminOpeningFuelProposed").value = shift.opening_fuel;
    $("adminOpeningFuelReason").value = "";
    $("adminShiftAdvancement").value = shift.advancement_m ?? "";
    $("adminShiftDredgingHours").value = shift.dredging_hours ?? "";
    $("adminShiftDataReason").value = "";
    $("adminShiftCloseReason").value = "";

    table(
      "adminShiftTransactions",
      ["Date", "Type", "Direction", "Quantity", "Balance effect", "Source / Reference", "Remarks", ""],
      (report.transactions || []).map((transaction) => [
        esc(formatDateTime(transaction.transaction_date)),
        esc(String(transaction.transaction_type).replaceAll("_", " ")),
        esc(transaction.adjustment_direction || "-"),
        `${litres(transaction.quantity)} L`,
        transaction.affects_balance === false ? "Recorded only" : "Applied",
        esc(
          transaction.fuel_source ||
          (transaction.source_vessel_id
            ? `Vessel #${transaction.source_vessel_id}`
            : transaction.reference_type
              ? `${transaction.reference_type} #${transaction.reference_id}`
              : "-"),
        ),
        esc(transaction.remarks || "-"),
        shift.status === "OPEN" &&
          transaction.transaction_type === "RECEIPT" &&
          !transaction.reference_type &&
          !transaction.reference_id
          ? `<button class="btn btn-sm" onclick="correctAdminReceipt(${transaction.id})">Correct receipt</button>`
          : shift.status === "OPEN" &&
              transaction.transaction_type === "ADJUSTMENT" &&
              !transaction.reference_type
            ? `<button class="btn btn-sm" onclick="correctAdminAdjustment(${transaction.id})">Correct adjustment</button>`
            : "—",
      ]),
    );
    adminEngineEvents = engineEvents;
    select(
      "adminEngineEquipment",
      equipment.filter((item) => Number(item.vessel_id) === Number(shift.vessel_id)),
    );
    const canManageEvents = shift.status === "OPEN";
    $("adminEngineManagement").classList.toggle("hidden", !canManageEvents);
    cancelAdminEngineEdit(true);
    table(
      "adminShiftEngineEvents",
      ["Equipment", "Start", "Stop", "Hours", "Consumption", "Remarks", "Actions"],
      engineEvents.map((event) => {
        const item = equipment.find((equipmentItem) => equipmentItem.id === event.equipment_id);
        const actions = canManageEvents
          ? `<button class="btn btn-sm" onclick="beginAdminEngineEdit(${event.id})">Edit</button> <button class="btn btn-sm btn-ghost" onclick="deleteAdminEngineEvent(${event.id})">Delete</button>`
          : "—";
        return [
          esc(item?.name || `Equipment #${event.equipment_id}`),
          esc(formatDateTime(event.start_time)),
          esc(formatDateTime(event.stop_time)),
          esc(event.hours_run),
          `${litres(event.consumption)} L`,
          esc(event.remarks || "-"),
          actions,
        ];
      }),
    );
    table(
      "adminShiftSoundings",
      ["Reported date", "Submitted", "Submitted by", "Attachment", "Actions"],
      soundings.map((sounding) => [
        esc(sounding.report_date),
        esc(formatDateTime(sounding.submitted_at)),
        esc(sounding.submitted_by_user_id),
        `<button class="btn btn-sm" onclick="viewShiftAttachment(${sounding.attachment_id})">#${sounding.attachment_id}</button>`,
        shift.status === "OPEN"
          ? `<button class="btn btn-sm" onclick="correctAdminSounding(${sounding.id})">Edit</button> <button class="btn btn-sm btn-ghost" onclick="deleteAdminSounding(${sounding.id})">Delete</button>`
          : "—",
      ]),
    );
    adminSoundings = soundings;
    $("adminSoundingAddButton").classList.toggle("hidden", shift.status !== "OPEN");
    $("adminReopenCard").classList.toggle("hidden", shift.status !== "CLOSED");
    $("adminShiftReason").value = "";
    const selectedTransfers = allTransfers.filter((transfer) =>
      Number(transfer.from_shift_id) === Number(shift.id) ||
      Number(transfer.to_shift_id) === Number(shift.id),
    );
    await loadAdminShiftSupplementary(
      shift,
      report,
      engineEvents,
      soundings,
      selectedTransfers,
    );
  } catch (e) {
    message(e.message, "error");
  }
}

async function loadAdminShiftSupplementary(
  shift,
  report,
  engineEvents,
  soundings,
  transfersForShift,
) {
  adminTransfers = transfersForShift;
  const [production, attachments, shiftAudit, engineAudit, productionAudit, transferAudit, soundingAudit, fuelAudit, attachmentLinkAudit, transferNotes] = await Promise.all([
    api(`/api/production?shift_id=${shift.id}`),
    api(`/api/shifts/${shift.id}/attachments`),
    api(`/api/audit?entity=shifts&entity_id=${shift.id}&limit=500`),
    api("/api/audit?entity=engine_events&limit=500"),
    api("/api/audit?entity=ProductionRecord&limit=500"),
    api("/api/audit?entity=transfers&limit=500"),
    api("/api/audit?entity=soundings&limit=500"),
    api("/api/audit?entity=fuel_transactions&limit=500"),
    api("/api/audit?entity=shift_attachments&limit=500"),
    Promise.all(transfersForShift.map(async (transfer) => ({
      transferId: transfer.id,
      attachments: await api(`/api/transfers/${transfer.id}/attachments`),
    }))),
  ]);

  adminProductionRecords = production;
  adminShiftAttachments = attachments;
  cancelAdminProduction(true);
  table(
    "adminShiftProduction",
    ["ID", "Date", "As-per", "True", "Variance", "Fuel rate", "Remarks", "Actions"],
    production.map((record) => [
      record.id,
      esc(record.production_date),
      f(record.as_per_qty),
      f(record.true_qty),
      f(Number(record.true_qty) - Number(record.as_per_qty)),
      litres(record.fuel_rate),
      esc(record.remarks || "-"),
      `<button class="btn btn-sm" onclick="beginAdminProductionEdit(${record.id})">Edit</button> <button class="btn btn-sm btn-ghost" onclick="deleteAdminProduction(${record.id})">Delete</button>`,
    ]),
  );

  table(
    "adminShiftAttachments",
    ["Type", "File", "Size", "Added", "" , "Actions"],
    attachments.map((attachment) => [
      esc(attachment.attachment_type),
      esc(attachment.original_filename),
      `${f(attachment.file_size / 1024)} KB`,
      esc(formatDateTime(attachment.created_at)),
      `<button class="btn btn-sm" onclick="viewShiftAttachment(${attachment.attachment_id})">View</button>`,
      `<button class="btn btn-sm btn-ghost" onclick="removeAdminShiftAttachment(${attachment.id})">Unlink</button>`,
    ]),
  );

  const notesByTransfer = new Map(
    transferNotes.map((item) => [item.transferId, item.attachments]),
  );
  table(
    "adminShiftTransfers",
    ["ID", "From vessel / shift", "To vessel / shift", "Initiated", "Received", "Loss", "Transfer date", "Status", "Lifecycle", "Notes", "Documents", "Actions"],
    transfersForShift.map((transfer) => {
      const documents = notesByTransfer.get(transfer.id) || [];
      const documentLinks = documents.length
        ? documents.map((note) => `<a href="#" onclick="viewShiftAttachment(${note.attachment_id}); return false;">#${note.attachment_id}</a>`).join(" ")
        : "-";
      const actions = shift.status === "OPEN" && transfer.status !== "REJECTED"
        ? `<button class="btn btn-sm" onclick="correctAdminTransfer(${transfer.id})">Correct</button>`
        : "—";
      return [
        `#${transfer.id}`,
        `${esc(chartVesselName(transfer.from_vessel_id))} / #${transfer.from_shift_id}`,
        `${esc(chartVesselName(transfer.to_vessel_id))} / #${transfer.to_shift_id}`,
        `${litres(transfer.initiated_quantity)} L`,
        transfer.received_quantity == null ? "—" : `${litres(transfer.received_quantity)} L`,
        transfer.loss_quantity == null ? "—" : `${litres(transfer.loss_quantity)} L`,
        esc(formatDateTime(transfer.transfer_date)),
        esc(transfer.status),
        esc(
          `Initiated ${formatDateTime(transfer.initiated_at)} by #${transfer.initiated_by_user_id}; ` +
          `received ${formatDateTime(transfer.received_at)} by #${transfer.received_by_user_id ?? "—"}; ` +
          `reviewed ${formatDateTime(transfer.reviewed_at)} by #${transfer.reviewed_by_user_id ?? "—"}; ` +
          `approved ${formatDateTime(transfer.approved_at)} by #${transfer.approved_by_user_id ?? "—"}`,
        ),
        esc([transfer.notes, transfer.manager_remark].filter(Boolean).join(" · ") || "-"),
        documentLinks,
        actions,
      ];
    }),
  );

  const eventIds = new Set(engineEvents.map((event) => Number(event.id)));
  const productionIds = new Set(production.map((record) => Number(record.id)));
  const transferIds = new Set(transfersForShift.map((transfer) => Number(transfer.id)));
  const transactionIds = new Set((report.transactions || []).map((transaction) => Number(transaction.id)));
  const sameShift = (values) => Number(values?.shift_id) === Number(shift.id);
  const auditRows = [
    ...shiftAudit,
    ...engineAudit.filter((entry) => eventIds.has(Number(entry.entity_id)) || sameShift(entry.old_values) || sameShift(entry.new_values)),
    ...productionAudit.filter((entry) => productionIds.has(Number(entry.entity_id)) || sameShift(entry.old_values) || sameShift(entry.new_values)),
    ...transferAudit.filter((entry) => transferIds.has(Number(entry.entity_id))),
    ...soundingAudit.filter((entry) => sameShift(entry.old_values) || sameShift(entry.new_values)),
    ...fuelAudit.filter((entry) => transactionIds.has(Number(entry.entity_id))),
    ...attachmentLinkAudit.filter((entry) => sameShift(entry.old_values) || sameShift(entry.new_values)),
  ].sort((left, right) => new Date(right.created_at) - new Date(left.created_at));
  table(
    "adminShiftAudit",
    ["Time", "User", "Action", "Entity", "Reason", "Previous values", "New values"],
    auditRows.map((entry) => [
      esc(formatDateTime(entry.created_at)),
      esc(entry.user_id ?? "System"),
      esc(entry.action),
      `${esc(entry.entity)}${entry.entity_id == null ? "" : ` #${entry.entity_id}`}`,
      esc(entry.reason || "-"),
      esc(entry.old_values ? JSON.stringify(entry.old_values) : "-"),
      esc(entry.new_values ? JSON.stringify(entry.new_values) : "-"),
    ]),
  );
}

const adminActionsInFlight = new Set();

async function runAdminAction(key, action) {
  if (adminActionsInFlight.has(key)) {
    message("This operation is already in progress.", "info");
    return;
  }
  const actionName = key.split(":", 1)[0];
  const preserve =
    actionName === "saveAdminEngineEvent"
      ? "engine"
      : actionName === "saveAdminProduction"
        ? "production"
        : actionName === "saveAdminShiftOperationalData"
          ? "shift-operational"
          : actionName === "correctAdminOpeningFuel"
            ? "opening-fuel"
            : actionName === "closeAdminShift"
              ? "close-shift"
              : actionName === "reopenAdminShift"
                ? "reopen-shift"
                : null;
  if (!confirmAdminEditorDiscard(preserve)) return;
  adminActionsInFlight.add(key);
  try {
    return await action();
  } finally {
    adminActionsInFlight.delete(key);
  }
}

async function removeAdminShiftAttachment(linkId) {
  try {
    if (me.role !== "ADMIN") throw Error("Only an administrator can unlink attachments.");
    const attachment = adminShiftAttachments.find((item) => item.id === linkId);
    if (!attachment) throw Error("Shift attachment not found.");
    if (attachment.attachment_type === "SOUNDING") {
      throw Error("Manage sounding attachments through the sounding record.");
    }
    const reason = prompt(`Reason for unlinking ${attachment.original_filename}:`);
    if (reason === null) return;
    if (!reason.trim()) throw Error("Enter a correction reason.");
    if (!confirm(`Unlink ${attachment.original_filename} from Shift #${attachment.shift_id}? The file will be retained.\n\nReason: ${reason.trim()}`)) return;
    await api(`/api/shifts/${attachment.shift_id}/attachments/${attachment.id}`, {
      method: "DELETE",
      body: JSON.stringify({ reason: reason.trim() }),
    });
    await viewAdminShift(adminSelectedShift.id);
    message("Attachment unlinked; shared file retained.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function createAdminSounding() {
  try {
    if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
      throw Error("Soundings can only be added by an administrator to an OPEN shift.");
    }
    const attachmentText = prompt("Attachment ID for the uploaded sounding image:");
    if (attachmentText === null) return;
    const attachmentId = Number(attachmentText);
    if (!Number.isInteger(attachmentId) || attachmentId <= 0) {
      throw Error("Enter a valid attachment ID.");
    }
    await api(`/api/soundings/admin/${adminSelectedShift.id}`, {
      method: "POST",
      body: JSON.stringify({ attachment_id: attachmentId }),
    });
    await viewAdminShift(adminSelectedShift.id);
    message("Sounding added.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function correctAdminSounding(soundingId) {
  try {
    if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
      throw Error("Soundings can only be corrected by an administrator on an OPEN shift.");
    }
    const sounding = adminSoundings.find((item) => item.id === soundingId);
    if (!sounding) throw Error("Sounding not found for the selected shift.");
    const attachmentText = prompt("Replacement sounding image attachment ID:", sounding.attachment_id);
    if (attachmentText === null) return;
    const attachmentId = Number(attachmentText);
    if (!Number.isInteger(attachmentId) || attachmentId <= 0) {
      throw Error("Enter a valid attachment ID.");
    }
    const reason = prompt("Correction reason:");
    if (reason === null) return;
    if (!reason.trim()) throw Error("Enter a correction reason.");
    if (!confirm(`Change sounding #${sounding.id} attachment #${sounding.attachment_id} to #${attachmentId}?\n\nReason: ${reason.trim()}`)) return;
    await api(`/api/soundings/admin/${adminSelectedShift.id}/${sounding.id}`, {
      method: "PUT",
      body: JSON.stringify({ attachment_id: attachmentId, reason: reason.trim() }),
    });
    await viewAdminShift(adminSelectedShift.id);
    message("Sounding attachment corrected.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function deleteAdminSounding(soundingId) {
  try {
    if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
      throw Error("Soundings can only be deleted by an administrator on an OPEN shift.");
    }
    const sounding = adminSoundings.find((item) => item.id === soundingId);
    if (!sounding) throw Error("Sounding not found for the selected shift.");
    const reason = prompt(`Correction reason for deleting sounding #${sounding.id}:`);
    if (reason === null) return;
    if (!reason.trim()) throw Error("Enter a correction reason.");
    if (!confirm(`Delete sounding #${sounding.id}? The attachment file will be retained.\n\nReason: ${reason.trim()}`)) return;
    await api(`/api/soundings/admin/${adminSelectedShift.id}/${sounding.id}`, {
      method: "DELETE",
      body: JSON.stringify({ reason: reason.trim() }),
    });
    await viewAdminShift(adminSelectedShift.id);
    message("Sounding deleted.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

function adminDateTimeInput(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}

function calculateAdminEngineRate() {
  const start = new Date($("adminEngineStart").value);
  const stop = new Date($("adminEngineStop").value);
  const consumption = Number($("adminEngineConsumption").value);
  const hours = (stop - start) / 3600000;
  $("adminEngineRate").value =
    Number.isFinite(hours) && hours > 0 && consumption > 0
      ? (consumption / hours).toFixed(3)
      : "";
}

function cancelAdminEngineEdit(force = false) {
  const editor = $("adminEngineEditor");
  const hasValues = [
    $("adminEngineStart").value,
    $("adminEngineStop").value,
    $("adminEngineConsumption").value,
    $("adminEngineRemarks").value,
    $("adminEngineReason").value,
  ].some((value) => value !== "");
  if (
    !force &&
    !editor.classList.contains("hidden") &&
    hasValues &&
    !confirm("Discard unsaved engine event changes?")
  ) {
    return false;
  }
  adminEditingEngineEventId = null;
  editor.classList.add("hidden");
  $("adminEngineReasonWrap").classList.add("hidden");
  $("adminEngineEditorTitle").textContent = "Add engine event";
  $("adminEngineSaveButton").textContent = "Save Engine Event";
  $("adminEngineStart").value = "";
  $("adminEngineStop").value = "";
  $("adminEngineConsumption").value = "";
  $("adminEngineRate").value = "";
  $("adminEngineRemarks").value = "";
  $("adminEngineReason").value = "";
  return true;
}

function confirmAdminEditorDiscard(preserve = null) {
  const shift = adminSelectedShift;
  const numberChanged = (inputId, storedValue) => {
    const value = $(inputId).value;
    if (value === "") return storedValue != null;
    return storedValue == null || Number(value) !== Number(storedValue);
  };
  const operationalDirty =
    numberChanged("adminShiftAdvancement", shift?.advancement_m) ||
    numberChanged("adminShiftDredgingHours", shift?.dredging_hours) ||
    Boolean($("adminShiftDataReason").value.trim());
  const openingDirty =
    numberChanged("adminOpeningFuelProposed", shift?.opening_fuel) ||
    Boolean($("adminOpeningFuelReason").value.trim());
  const closeDirty = Boolean($("adminShiftCloseReason").value.trim());
  const reopenDirty = Boolean($("adminShiftReason").value.trim());
  const dirtyShiftEditors = [
    preserve !== "shift-operational" && operationalDirty ? "operational data" : null,
    preserve !== "opening-fuel" && openingDirty ? "opening fuel" : null,
    preserve !== "close-shift" && closeDirty ? "close reason" : null,
    preserve !== "reopen-shift" && reopenDirty ? "reopen reason" : null,
  ].filter(Boolean);
  if (
    dirtyShiftEditors.length &&
    !confirm(`Discard unsaved ${dirtyShiftEditors.join(", ")}?`)
  ) {
    return false;
  }

  const productionEditor = $("adminProductionEditor");
  const productionHasValues = [
    $("adminProductionAs").value,
    $("adminProductionTrue").value,
    $("adminProductionFuelRate").value,
    $("adminProductionRemarks").value,
    $("adminProductionReason").value,
  ].some((value) => value !== "");
  if (
    preserve !== "production" &&
    !productionEditor.classList.contains("hidden") &&
    productionHasValues &&
    !confirm("Discard unsaved production record changes?")
  ) {
    return false;
  }

  const engineEditor = $("adminEngineEditor");
  const engineHasValues = [
    $("adminEngineStart").value,
    $("adminEngineStop").value,
    $("adminEngineConsumption").value,
    $("adminEngineRemarks").value,
    $("adminEngineReason").value,
  ].some((value) => value !== "");
  if (
    preserve !== "engine" &&
    !engineEditor.classList.contains("hidden") &&
    engineHasValues &&
    !confirm("Discard unsaved engine event changes?")
  ) {
    return false;
  }

  if (preserve !== "production") cancelAdminProduction(true);
  if (preserve !== "engine") cancelAdminEngineEdit(true);
  if (preserve !== "shift-operational") {
    $("adminShiftAdvancement").value = shift?.advancement_m ?? "";
    $("adminShiftDredgingHours").value = shift?.dredging_hours ?? "";
    $("adminShiftDataReason").value = "";
  }
  if (preserve !== "opening-fuel") {
    $("adminOpeningFuelProposed").value = shift?.opening_fuel ?? "";
    $("adminOpeningFuelReason").value = "";
  }
  if (preserve !== "close-shift") $("adminShiftCloseReason").value = "";
  if (preserve !== "reopen-shift") $("adminShiftReason").value = "";
  return true;
}

function beginAdminEngineCreate() {
  if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
    message("Engine events can only be added by an administrator to an OPEN shift.", "error");
    return;
  }
  if (!confirmAdminEditorDiscard()) return;
  cancelAdminEngineEdit();
  $("adminEngineEditor").classList.remove("hidden");
  $("adminEngineEquipment").value = $("adminEngineEquipment").options[0]?.value || "";
}

function beginAdminEngineEdit(eventId) {
  if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
    message("Engine events can only be edited by an administrator on an OPEN shift.", "error");
    return;
  }
  const event = adminEngineEvents.find((item) => item.id === eventId);
  if (!event) {
    message("Engine event not found in the selected shift.", "error");
    return;
  }
  if (!confirmAdminEditorDiscard()) return;

  adminEditingEngineEventId = event.id;
  $("adminEngineEquipment").value = String(event.equipment_id);
  $("adminEngineStart").value = adminDateTimeInput(event.start_time);
  $("adminEngineStop").value = adminDateTimeInput(event.stop_time);
  $("adminEngineConsumption").value = event.consumption;
  $("adminEngineRemarks").value = event.remarks || "";
  $("adminEngineReason").value = "";
  $("adminEngineReasonWrap").classList.remove("hidden");
  $("adminEngineEditorTitle").textContent = `Edit engine event #${event.id}`;
  $("adminEngineSaveButton").textContent = "Save Correction";
  $("adminEngineEditor").classList.remove("hidden");
  calculateAdminEngineRate();
}

async function saveAdminEngineEvent() {
  try {
    if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
      throw Error("Engine events can only be changed by an administrator on an OPEN shift.");
    }
    const equipmentId = Number($("adminEngineEquipment").value);
    const start = new Date($("adminEngineStart").value);
    const stop = new Date($("adminEngineStop").value);
    const consumption = Number($("adminEngineConsumption").value);
    if (!equipmentId) throw Error("Select equipment.");
    if (Number.isNaN(start.getTime()) || Number.isNaN(stop.getTime())) {
      throw Error("Enter valid start and stop times.");
    }
    if (stop <= start) throw Error("Stop time must be after start time.");
    if (!Number.isFinite(consumption) || consumption <= 0) {
      throw Error("Engine consumption must be greater than zero.");
    }

    const hours = (stop - start) / 3600000;
    const payload = {
      equipment_id: equipmentId,
      start_time: start.toISOString(),
      stop_time: stop.toISOString(),
      lph_rate: Number((consumption / hours).toFixed(3)),
      consumption,
      remarks: $("adminEngineRemarks").value.trim() || null,
      reconcile_downstream: true,
    };
    let successMessage;
    if (adminEditingEngineEventId !== null) {
      const reason = $("adminEngineReason").value.trim();
      if (!reason) throw Error("Enter a correction reason.");
      const oldEvent = adminEngineEvents.find(
        (event) => event.id === adminEditingEngineEventId,
      );
      if (!oldEvent) throw Error("Engine event not found in the selected shift.");
      const oldEquipment = equipment.find(
        (item) => Number(item.id) === Number(oldEvent.equipment_id),
      )?.name || `Equipment #${oldEvent.equipment_id}`;
      const newEquipment = equipment.find(
        (item) => Number(item.id) === equipmentId,
      )?.name || `Equipment #${equipmentId}`;
      if (!confirm(
        `Correct engine event #${oldEvent.id}?\n` +
        `Equipment: ${oldEquipment} → ${newEquipment}\n` +
        `Start: ${formatDateTime(oldEvent.start_time)} → ${formatDateTime(start.toISOString())}\n` +
        `Stop: ${formatDateTime(oldEvent.stop_time)} → ${formatDateTime(stop.toISOString())}\n` +
        `Consumption: ${oldEvent.consumption} L → ${consumption} L\n` +
        `Remarks: ${oldEvent.remarks || "—"} → ${$("adminEngineRemarks").value.trim() || "—"}\n\n` +
        `Reason: ${reason}\n\n` +
        `If later shifts exist, their opening and closing fuel will be recalculated. Recorded transactions remain unchanged; the correction will be blocked if a later shift would become negative.`,
      )) return;
      payload.reason = reason;
      await api(
        `/api/engine/shift/${adminSelectedShift.id}/events/${adminEditingEngineEventId}`,
        { method: "PUT", body: JSON.stringify(payload) },
      );
      successMessage = "Engine event correction saved.";
    } else {
      if (!confirm("Add this engine event? If later shifts exist, their opening and closing fuel will be recalculated. Recorded transactions remain unchanged; the event will be blocked if a later shift would become negative.")) return;
      payload.shift_id = adminSelectedShift.id;
      await api(`/api/engine/shift/${adminSelectedShift.id}/events`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      successMessage = "Engine event added.";
    }

    const shiftId = adminSelectedShift.id;
    cancelAdminEngineEdit(true);
    await viewAdminShift(shiftId, true);
    message(successMessage, "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function deleteAdminEngineEvent(eventId) {
  try {
    if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
      throw Error("Engine events can only be deleted by an administrator on an OPEN shift.");
    }
    const event = adminEngineEvents.find((item) => item.id === eventId);
    if (!event) throw Error("Engine event not found in the selected shift.");

    const reason = prompt(`Correction reason for deleting engine event #${event.id}:`);
    if (reason === null) return;
    if (!reason.trim()) throw Error("Enter a correction reason.");
    if (!confirm(`Delete engine event #${event.id}?\n\nReason: ${reason.trim()}\n\nIf later shifts exist, their opening and closing fuel will be recalculated. Recorded transactions remain unchanged; the deletion will be blocked if a later shift would become negative.`)) return;

    await api(`/api/engine/shift/${adminSelectedShift.id}/events/${event.id}`, {
      method: "DELETE",
      body: JSON.stringify({ reason: reason.trim(), reconcile_downstream: true }),
    });
    await viewAdminShift(adminSelectedShift.id);
    message("Engine event deleted.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function saveAdminShiftOperationalData() {
  try {
    if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
      throw Error("Operational data can only be corrected by an administrator on an OPEN shift.");
    }
    const reason = $("adminShiftDataReason").value.trim();
    if (!reason) throw Error("Enter a correction reason.");
    const advancement = $("adminShiftAdvancement").value;
    const dredgingHours = $("adminShiftDredgingHours").value;
    const advancementValue = advancement === "" ? null : Number(advancement);
    const dredgingValue = dredgingHours === "" ? null : Number(dredgingHours);
    if (advancementValue !== null && (!Number.isFinite(advancementValue) || advancementValue < 0)) {
      throw Error("Advancement must be a non-negative number.");
    }
    if (dredgingValue !== null && (!Number.isFinite(dredgingValue) || dredgingValue < 0)) {
      throw Error("Dredging hours must be a non-negative number.");
    }

    const shift = adminSelectedShift;
    const confirmation =
      `Correct Shift #${shift.id}?\n` +
      `Advancement: ${shift.advancement_m ?? "—"} → ${advancementValue ?? "—"}\n` +
      `Dredging hours: ${shift.dredging_hours ?? "—"} → ${dredgingValue ?? "—"}\n` +
      `Reason: ${reason}`;
    if (!confirm(confirmation)) return;

    await api(`/api/fuel/admin/shift/${shift.id}/operational-data`, {
      method: "PUT",
      body: JSON.stringify({
        advancement_m: advancementValue,
        dredging_hours: dredgingValue,
        reason,
      }),
    });
    await viewAdminShift(shift.id, true);
    message("Shift operational data corrected.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function correctAdminOpeningFuel() {
  try {
    if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
      throw Error("Opening fuel can only be corrected by an administrator on an OPEN shift.");
    }
    const openingFuel = Number($("adminOpeningFuelProposed").value);
    const reason = $("adminOpeningFuelReason").value.trim();
    if (!Number.isFinite(openingFuel) || openingFuel < 0) {
      throw Error("Opening fuel must be a non-negative number.");
    }
    if (!reason) throw Error("Enter a correction reason.");
    const shift = adminSelectedShift;
    if (!confirm(`Correct opening fuel for Shift #${shift.id}?\n${shift.opening_fuel} L → ${openingFuel} L\n\nOpening and closing balances for every later shift will be recalculated. Recorded transactions will remain unchanged. The correction will be rejected if any closing balance becomes negative.\n\nReason: ${reason}`)) return;
    await api(`/api/fuel/admin/shift/${shift.id}/opening`, {
      method: "PATCH",
      body: JSON.stringify({ opening_fuel: openingFuel, reason }),
    });
    await viewAdminShift(shift.id, true);
    message("Opening fuel corrected and downstream shift balances reconciled.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function closeAdminShift() {
  try {
    if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
      throw Error("Only an administrator can close an OPEN shift here.");
    }
    const reason = $("adminShiftCloseReason").value.trim();
    if (!reason) throw Error("Enter a closing reason.");
    const shift = adminSelectedShift;
    if (!confirm(`Close Shift #${shift.id} (${shift.shift_name}, ${shift.shift_date})?\n\nReason: ${reason}`)) {
      return;
    }
    await api(`/api/fuel/admin/shift/${shift.id}/close`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
    await viewAdminShift(shift.id, true);
    message("Shift closed after backend validation.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

function cancelAdminProduction(force = false) {
  const editor = $("adminProductionEditor");
  const hasValues = [
    $("adminProductionAs").value,
    $("adminProductionTrue").value,
    $("adminProductionFuelRate").value,
    $("adminProductionRemarks").value,
    $("adminProductionReason").value,
  ].some((value) => value !== "");
  if (!force && !editor.classList.contains("hidden") && hasValues && !confirm("Discard this production record edit?")) {
    return false;
  }
  adminEditingProductionId = null;
  editor.classList.add("hidden");
  $("adminProductionReasonWrap").classList.add("hidden");
  $("adminProductionEditorTitle").textContent = "Add production record";
  $("adminProductionSaveButton").textContent = "Save";
  $("adminProductionAs").value = "";
  $("adminProductionTrue").value = "";
  $("adminProductionFuelRate").value = "";
  $("adminProductionRemarks").value = "";
  $("adminProductionReason").value = "";
  return true;
}

function beginAdminProductionCreate() {
  if (me.role !== "ADMIN" || !adminSelectedShift) {
    message("Select a shift before adding production.", "error");
    return;
  }
  if (!confirmAdminEditorDiscard()) return;
  cancelAdminProduction(true);
  $("adminProductionEditor").classList.remove("hidden");
}

function beginAdminProductionEdit(productionId) {
  if (me.role !== "ADMIN") {
    message("Only an administrator can edit production records.", "error");
    return;
  }
  const record = adminProductionRecords.find((item) => item.id === productionId);
  if (!record) {
    message("Production record not found for this shift.", "error");
    return;
  }
  if (!confirmAdminEditorDiscard()) return;
  cancelAdminProduction(true);
  adminEditingProductionId = record.id;
  $("adminProductionAs").value = record.as_per_qty;
  $("adminProductionTrue").value = record.true_qty;
  $("adminProductionFuelRate").value = record.fuel_rate ?? "";
  $("adminProductionRemarks").value = record.remarks || "";
  $("adminProductionReasonWrap").classList.remove("hidden");
  $("adminProductionEditorTitle").textContent = `Edit production record #${record.id}`;
  $("adminProductionSaveButton").textContent = "Save Correction";
  $("adminProductionEditor").classList.remove("hidden");
}

async function saveAdminProduction() {
  try {
    if (me.role !== "ADMIN" || !adminSelectedShift) {
      throw Error("Select a shift before saving production.");
    }
    const asPer = Number($("adminProductionAs").value);
    const trueQuantity = Number($("adminProductionTrue").value);
    const fuelRateText = $("adminProductionFuelRate").value;
    const fuelRate = fuelRateText === "" ? null : Number(fuelRateText);
    if (!Number.isFinite(asPer) || asPer < 0 || !Number.isFinite(trueQuantity) || trueQuantity < 0) {
      throw Error("Production quantities must be non-negative numbers.");
    }
    if (fuelRate !== null && (!Number.isFinite(fuelRate) || fuelRate < 0)) {
      throw Error("Fuel rate must be a non-negative number.");
    }

    const isEditing = adminEditingProductionId !== null;
    const payload = {
      as_per_qty: asPer,
      true_qty: trueQuantity,
      fuel_rate: fuelRate,
      remarks: $("adminProductionRemarks").value.trim() || null,
    };
    if (isEditing) {
      const reason = $("adminProductionReason").value.trim();
      if (!reason) throw Error("Enter a correction reason.");
      const oldRecord = adminProductionRecords.find(
        (record) => record.id === adminEditingProductionId,
      );
      if (!oldRecord) throw Error("Production record not found for this shift.");
      if (!confirm(
        `Correct production record #${oldRecord.id}?\n` +
        `As-per: ${oldRecord.as_per_qty} → ${asPer}\n` +
        `True: ${oldRecord.true_qty} → ${trueQuantity}\n` +
        `Fuel rate: ${oldRecord.fuel_rate ?? "—"} → ${fuelRate ?? "—"}\n` +
        `Remarks: ${oldRecord.remarks || "—"} → ${$("adminProductionRemarks").value.trim() || "—"}\n\n` +
        `Reason: ${reason}`,
      )) return;
      payload.reason = reason;
      await api(`/api/production/admin/${adminEditingProductionId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    } else {
      const vessel = vessels.find((item) => Number(item.id) === Number(adminSelectedShift.vessel_id));
      if (!vessel) throw Error("Shift vessel not found.");
      await api("/api/production/admin", {
        method: "POST",
        body: JSON.stringify({
          ...payload,
          project_id: vessel.project_id,
          vessel_id: adminSelectedShift.vessel_id,
          shift_id: adminSelectedShift.id,
          production_date: adminSelectedShift.shift_date,
        }),
      });
    }
    const shiftId = adminSelectedShift.id;
    await viewAdminShift(shiftId, true);
    message(isEditing ? "Production record corrected." : "Production record added.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function deleteAdminProduction(productionId) {
  try {
    if (me.role !== "ADMIN") throw Error("Only an administrator can delete production records.");
    const record = adminProductionRecords.find((item) => item.id === productionId);
    if (!record) throw Error("Production record not found for this shift.");
    const reason = prompt(`Correction reason for deleting production record #${record.id}:`);
    if (reason === null) return;
    if (!reason.trim()) throw Error("Enter a correction reason.");
    if (!confirm(`Delete production record #${record.id} (${record.production_date})?\n\nReason: ${reason.trim()}`)) return;
    await api(`/api/production/admin/${record.id}`, {
      method: "DELETE",
      body: JSON.stringify({ reason: reason.trim() }),
    });
    await viewAdminShift(adminSelectedShift.id);
    message("Production record deleted.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function correctAdminReceipt(transactionId) {
  try {
    if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
      throw Error("Receipts can only be corrected by an administrator on an OPEN shift.");
    }
    const transaction = adminFuelTransactions.find((item) => item.id === transactionId);
    if (
      !transaction ||
      transaction.transaction_type !== "RECEIPT" ||
      transaction.reference_type != null ||
      transaction.reference_id != null
    ) {
      throw Error("Only a standalone receipt for the selected shift can be corrected.");
    }

    const quantityText = prompt("Corrected receipt quantity (L):", transaction.quantity);
    if (quantityText === null) return;
    const quantity = Number(quantityText);
    if (!Number.isFinite(quantity) || quantity <= 0) {
      throw Error("Receipt quantity must be greater than zero.");
    }
    const sourceVesselText = prompt(
      "Source vessel ID (leave blank for a manual source):",
      transaction.source_vessel_id ?? "",
    );
    if (sourceVesselText === null) return;
    const sourceVesselId = sourceVesselText.trim() === "" ? null : Number(sourceVesselText);
    if (sourceVesselId !== null && (!Number.isInteger(sourceVesselId) || sourceVesselId <= 0)) {
      throw Error("Source vessel ID must be a positive integer.");
    }
    const fuelSource = prompt("Fuel source name:", transaction.fuel_source || "");
    if (fuelSource === null) return;
    const remarks = prompt("Receipt remarks:", transaction.remarks || "");
    if (remarks === null) return;
    const reason = prompt("Correction reason:");
    if (reason === null) return;
    if (!reason.trim()) throw Error("Enter a correction reason.");

    const oldSource = transaction.source_vessel_id
      ? `Vessel #${transaction.source_vessel_id}`
      : transaction.fuel_source || "Manual source";
    const newSource = sourceVesselId
      ? `Vessel #${sourceVesselId}`
      : fuelSource.trim() || "Manual source";
    if (
      !confirm(
        `Correct receipt #${transaction.id}?\n` +
        `Quantity: ${transaction.quantity} L → ${quantity} L\n` +
        `Source: ${oldSource} → ${newSource}\n` +
        `Remarks: ${transaction.remarks || "—"} → ${remarks.trim() || "—"}\n\n` +
        `Reason: ${reason.trim()}\n\n` +
        `If later shifts exist, their opening and closing fuel will be recalculated. Recorded transactions remain unchanged; the correction will be blocked if a later shift would become negative.`,
      )
    ) {
      return;
    }

    await api(`/api/fuel/admin/receipts/${transaction.id}/correct`, {
      method: "POST",
      body: JSON.stringify({
        quantity,
        source_vessel_id: sourceVesselId,
        fuel_source: fuelSource.trim() || null,
        remarks: remarks.trim() || null,
        reason: reason.trim(),
        reconcile_downstream: true,
      }),
    });
    await viewAdminShift(adminSelectedShift.id, true);
    message("Receipt corrected; downstream shifts reconciled where needed.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function correctAdminAdjustment(transactionId) {
  try {
    if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
      throw Error("Adjustments can only be corrected by an administrator on an OPEN shift.");
    }
    const transaction = adminFuelTransactions.find((item) => item.id === transactionId);
    if (!transaction) throw Error("Adjustment transaction not found.");
    const quantity = prompt("Corrected adjustment quantity:", transaction.quantity);
    if (quantity === null) return;
    const parsedQuantity = Number(quantity);
    if (!Number.isFinite(parsedQuantity) || parsedQuantity <= 0) {
      throw Error("Quantity must be greater than zero.");
    }
    const direction = prompt("Corrected direction (IN or OUT):", transaction.adjustment_direction || "IN");
    if (direction === null) return;
    const normalizedDirection = direction.trim().toUpperCase();
    if (!["IN", "OUT"].includes(normalizedDirection)) throw Error("Direction must be IN or OUT.");
    const reason = prompt("Correction reason:");
    if (reason === null) return;
    if (!reason.trim()) throw Error("Enter a correction reason.");
    if (!confirm(`Correct adjustment #${transaction.id}?\n${transaction.adjustment_direction} ${transaction.quantity} L → ${normalizedDirection} ${parsedQuantity} L\n\nReason: ${reason.trim()}\n\nIf later shifts exist, their opening and closing fuel will be recalculated. Recorded transactions remain unchanged; the correction will be blocked if a later shift would become negative.`)) return;

    await api(`/api/fuel/admin/adjustments/${transaction.id}/correct`, {
      method: "POST",
      body: JSON.stringify({ quantity: parsedQuantity, direction: normalizedDirection, reason: reason.trim(), reconcile_downstream: true }),
    });
    await viewAdminShift(adminSelectedShift.id);
    message("Adjustment corrected; downstream shifts reconciled where needed.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function correctAdminTransfer(transferId) {
  try {
    if (me.role !== "ADMIN" || adminSelectedShift?.status !== "OPEN") {
      throw Error("Transfer corrections require an administrator and an OPEN selected shift.");
    }
    const transfer = adminTransfers.find((item) => item.id === transferId);
    if (!transfer) throw Error("Transfer not found for this shift.");
    const initiatedText = prompt("Corrected initiated quantity (L):", transfer.initiated_quantity);
    if (initiatedText === null) return;
    const initiated = Number(initiatedText);
    if (!Number.isFinite(initiated) || initiated <= 0) throw Error("Initiated quantity must be greater than zero.");

    let received = null;
    if (transfer.status !== "INITIATED") {
      const receivedText = prompt("Corrected received quantity (L):", transfer.received_quantity);
      if (receivedText === null) return;
      received = Number(receivedText);
      if (!Number.isFinite(received) || received < 0) throw Error("Received quantity cannot be negative.");
    }
    const notes = prompt("Transfer notes:", transfer.notes || "");
    if (notes === null) return;
    const reason = prompt("Correction reason:");
    if (reason === null) return;
    if (!reason.trim()) throw Error("Enter a correction reason.");
    const oldQuantities = `${transfer.initiated_quantity} / ${transfer.received_quantity ?? "—"}`;
    const newQuantities = `${initiated} / ${received ?? "—"}`;
    if (oldQuantities === newQuantities && notes === (transfer.notes || "")) {
      throw Error("No transfer values changed.");
    }
    if (!confirm(
      `Correct transfer #${transfer.id}?\n` +
      `Initiated / received: ${oldQuantities} → ${newQuantities}\n` +
      `Notes: ${transfer.notes || "—"} → ${notes.trim() || "—"}\n\n` +
      `Reason: ${reason.trim()}\n\n` +
      `If this approved transfer changes fuel, later shifts for the affected vessels will be recalculated. Recorded transactions remain unchanged; the correction will be blocked if a later shift would become negative.`,
    )) return;

    const payload = { initiated_quantity: initiated, notes, reason: reason.trim(), reconcile_downstream: true };
    if (received !== null) payload.received_quantity = received;
    await api(`/api/transfers/admin/${transfer.id}/correct`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await viewAdminShift(adminSelectedShift.id);
    message("Transfer corrected; downstream shifts reconciled where needed.", "success");
  } catch (e) {
    message(e.message, "error");
  }
}

async function reopenAdminShift() {
  try {
    if (me.role !== "ADMIN") {
      throw Error("Only an administrator can reopen shifts.");
    }
    if (!adminSelectedShift || adminSelectedShift.status !== "CLOSED") {
      throw Error("Only a closed shift can be reopened.");
    }

    const reason = $("adminShiftReason").value.trim();
    if (!reason) throw Error("Enter a correction reason.");

    const shift = adminSelectedShift;
    const vessel = vessels.find((item) => item.id === shift.vessel_id);
    const label = `${vessel?.name || `Vessel #${shift.vessel_id}`} · ${shift.shift_date} · ${shift.shift_name}`;
    if (!confirm(`Reopen ${label}?\n\nReason: ${reason}`)) return;

    await api(`/api/fuel/shift/${shift.id}/reopen`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
    $("adminShiftReason").value = "";
    message("Shift reopened. Existing fuel transactions and transfer balances were not changed.", "success");
    await loadAdminShifts();
    await viewAdminShift(shift.id, true);
  } catch (e) {
    message(e.message, "error");
  }
}


// ============================================================
// FORMAT AUDIT DATE
// ============================================================

function formatAuditDate(value) {
  if (!value) {
    return "—";
  }

  const d = new Date(value);

  if (Number.isNaN(d.getTime())) {
    return esc(String(value));
  }

  return d.toLocaleString();
}


// ============================================================
// LOAD AUDIT
// ============================================================

async function loadAudit(reset = false) {
  try {

    if (me.role !== "ADMIN") {
      throw Error(
        "Only an administrator can view the audit log."
      );
    }

    if (reset) {
      auditOffset = 0;
    }


    // Load users the first time.
    if (!auditUsers.length) {
      await loadAuditUsers();
    }


    const paramsObj = {
      limit: AUDIT_PAGE_SIZE,
      offset: auditOffset,
    };


    const action =
      $("auditAction")?.value.trim();

    const entity =
      $("auditEntity")?.value.trim();

    const entityId =
      $("auditEntityId")?.value.trim();

    const userId =
      $("auditUser")?.value;


    if (action) {
      paramsObj.action = action;
    }

    if (entity) {
      paramsObj.entity = entity;
    }

    if (entityId) {
      paramsObj.entity_id = Number(entityId);
    }

    if (userId) {
      paramsObj.user_id = Number(userId);
    }


    const query =
      params(paramsObj);


    const rows =
      await api(
        `/api/audit?${query}`
      );


    renderAudit(rows);


    const status =
      $("auditStatus");

    if (status) {
      if (!rows.length) {
        status.textContent =
          "No audit records found.";
      } else {
        status.textContent =
          `Showing records ${
            auditOffset + 1
          }–${
            auditOffset + rows.length
          }`;
      }
    }


    renderAuditPagination(rows.length);

  } catch (e) {

    const list =
      $("auditList");

    if (list) {
      list.innerHTML = `
        <div class="note note-err">
          ${esc(e.message)}
        </div>
      `;
    }

    message(
      e.message,
      "error"
    );
  }
}


// ============================================================
// RENDER AUDIT TABLE
// ============================================================

function renderAudit(rows) {

  const container =
    $("auditList");

  if (!container) {
    return;
  }


  if (!rows.length) {

    container.innerHTML = `
      <div class="muted">
        No audit records match the selected filters.
      </div>
    `;

    return;
  }


  container.innerHTML = `

    <table>

      <thead>
        <tr>
          <th>Date / Time</th>
          <th>User</th>
          <th>Action</th>
          <th>Entity</th>
          <th>Entity ID</th>
          <th>Reason</th>
          <th>Details</th>
        </tr>
      </thead>

      <tbody>

        ${rows
          .map(
            (audit) => `

              <tr>

                <td class="mono">
                  ${formatAuditDate(
                    audit.created_at
                  )}
                </td>


                <td>
                  <strong>
                    ${esc(
                      auditUserName(
                        audit.user_id
                      )
                    )}
                  </strong>

                  <div class="muted">
                    ID: ${
                      audit.user_id ?? "System"
                    }
                  </div>
                </td>


                <td>
                  <span class="audit-action-pill">
                    ${esc(
                      audit.action
                    )}
                  </span>
                </td>


                <td>
                  ${esc(
                    audit.entity
                  )}
                </td>


                <td>
                  ${
                    audit.entity_id ??
                    "—"
                  }
                </td>


                <td>
                  ${
                    audit.reason
                      ? esc(audit.reason)
                      : "—"
                  }
                </td>


                <td>

                  <details>

                    <summary>
                      View changes
                    </summary>

                    <div class="audit-details">

                      <div>
                        <strong>
                          Details
                        </strong>

                        <div class="audit-detail-text">
                          ${
                            audit.details
                              ? esc(
                                  audit.details
                                )
                              : "—"
                          }
                        </div>
                      </div>


                      <div>

                        <strong>
                          Old Values
                        </strong>

                        <pre>${formatAuditJson(
                          audit.old_values
                        )}</pre>

                      </div>


                      <div>

                        <strong>
                          New Values
                        </strong>

                        <pre>${formatAuditJson(
                          audit.new_values
                        )}</pre>

                      </div>

                    </div>

                  </details>

                </td>

              </tr>

            `
          )
          .join("")}

      </tbody>

    </table>

  `;
}


// ============================================================
// AUDIT PAGINATION
// ============================================================

function renderAuditPagination(rowCount) {

  const container =
    $("auditPagination");

  if (!container) {
    return;
  }


  const hasPrevious =
    auditOffset > 0;

  const hasNext =
    rowCount === AUDIT_PAGE_SIZE;


  container.innerHTML = `

    <button
      class="btn btn-sm"
      ${hasPrevious ? "" : "disabled"}
      onclick="previousAuditPage()"
    >
      Previous
    </button>


    <span class="muted">
      Page ${
        Math.floor(
          auditOffset /
          AUDIT_PAGE_SIZE
        ) + 1
      }
    </span>


    <button
      class="btn btn-sm"
      ${hasNext ? "" : "disabled"}
      onclick="nextAuditPage()"
    >
      Next
    </button>

  `;
}


// ============================================================
// NEXT PAGE
// ============================================================

async function nextAuditPage() {

  auditOffset +=
    AUDIT_PAGE_SIZE;

  await loadAudit();

}


// ============================================================
// PREVIOUS PAGE
// ============================================================

async function previousAuditPage() {

  auditOffset =
    Math.max(
      0,
      auditOffset -
        AUDIT_PAGE_SIZE
    );

  await loadAudit();

}


// ============================================================
// CLEAR AUDIT FILTERS
// ============================================================

function clearAuditFilters() {

  if ($("auditAction")) {
    $("auditAction").value = "";
  }

  if ($("auditEntity")) {
    $("auditEntity").value = "";
  }

  if ($("auditEntityId")) {
    $("auditEntityId").value = "";
  }

  if ($("auditUser")) {
    $("auditUser").value = "";
  }

  auditOffset = 0;

  loadAudit(true);
}

// ============================================================
// USERS
// ============================================================

async function loadUsers() {
  try {
    const rows = await api("/api/users");

    // Store users for inline editing/status changes.
    currentUsers = rows;

    table(
      "usersList",
      ["ID", "Username", "Name", "Role", "Projects", "Status", "Actions"],
      rows.map((x) => [
        x.id,

        esc(x.username),

        esc(x.full_name),

        esc(x.role),

        x.role === "ADMIN"
          ? "All projects"
          : esc((x.project_ids || [])
              .map((id) => projects.find((project) => Number(project.id) === Number(id))?.name)
              .filter(Boolean)
              .join(", ") || "None assigned"),

        `<button
          class="btn btn-sm ${x.is_active ? "btn-success" : "btn-danger"}"
          onclick="toggleUserActive(${x.id}, ${x.is_active})"
        >
          ${x.is_active ? "Active" : "Inactive"}
        </button>`,

        `
          <button
            class="btn btn-sm btn-warn"
            onclick="editUser(${x.id})"
          >
            Edit
          </button>

          <button
            class="btn btn-sm"
            onclick="resetUserPassword(${x.id})"
          >
            Reset Password
          </button>
        `,
      ]),
    );

    const backups = await api("/api/backup");

    table(
      "backupsList",
      ["Filename", "Created"],
      backups.map((x) => [
        esc(x.filename || x),
        esc(x.created_at || ""),
      ]),
    );

  } catch (e) {
    message(e.message, "error");
  }
}


// ============================================================
// ADD USER
// ============================================================

function addUser() {
  const tableEl = document.querySelector("#usersList table");

  if (!tableEl) {
    message("Users table not found.", "error");
    return;
  }

  const tbody = tableEl.querySelector("tbody");

  if (!tbody) {
    message("Users table body not found.", "error");
    return;
  }

  if (tbody.querySelector(".new-user-row")) {
    return;
  }

  const row = document.createElement("tr");

  row.className = "new-user-row";

  row.innerHTML = `
    <td>New</td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="newUserUsername"
        placeholder="Username"
      >
    </td>

    <td>
      <input
        type="text"
        class="master-inline-input"
        id="newUserFullName"
        placeholder="Full name"
      >
    </td>

    <td>
      <select
        class="master-inline-input"
        id="newUserRole"
      >
        <option value="OPERATOR">OPERATOR</option>
        <option value="MANAGER">MANAGER</option>
        <option value="ADMIN">ADMIN</option>
      </select>
    </td>

    <td>
      <select class="master-inline-input" id="newUserProjects" multiple size="3">
        ${projects.map((project) => '<option value="' + project.id + '">' + esc(project.name) + '</option>').join("")}
      </select>
      <small>Ctrl-click to select multiple projects</small>
    </td>

    <td>
      <select
        class="master-inline-input"
        id="newUserStatus"
      >
        <option value="true">Active</option>
        <option value="false">Inactive</option>
      </select>
    </td>

    <td>
      <input
        type="password"
        class="master-inline-input"
        id="newUserPassword"
        placeholder="Initial password"
      >

      <div class="mt8">
        <button
          class="btn btn-sm btn-success"
          onclick="saveNewUser()"
        >
          Save
        </button>

        <button
          class="btn btn-sm"
          onclick="cancelNewUser()"
        >
          Cancel
        </button>
      </div>
    </td>
  `;

  tbody.prepend(row);

  document
    .querySelector("#newUserUsername")
    ?.focus();
}


function cancelNewUser() {
  loadUsers();
}


async function saveNewUser() {
  try {
    const username = document
      .querySelector("#newUserUsername")
      ?.value.trim();

    const fullName = document
      .querySelector("#newUserFullName")
      ?.value.trim();

    const role = document
      .querySelector("#newUserRole")
      ?.value;

    const password = document
      .querySelector("#newUserPassword")
      ?.value;

    const projectIds = Array.from(
      document.querySelector("#newUserProjects")?.selectedOptions || [],
    ).map((option) => Number(option.value));

    const isActive =
      document
        .querySelector("#newUserStatus")
        ?.value === "true";

    if (!username) {
      throw Error("Username is required.");
    }

    if (!fullName) {
      throw Error("Full name is required.");
    }

    if (!["ADMIN", "MANAGER", "OPERATOR"].includes(role)) {
      throw Error("Invalid user role.");
    }

    if (!password) {
      throw Error("Initial password is required.");
    }

    const confirmed = confirm(
      `Create user "${username}" as ${role}?`
    );

    if (!confirmed) {
      return;
    }

    await api("/api/users", {
      method: "POST",
      body: JSON.stringify({
        username: username,
        password: password,
        role: role,
        full_name: fullName,
        project_ids: role === "ADMIN" ? [] : projectIds,
      }),
    });

    message(
      `User "${username}" created successfully.`,
      "success"
    );

    await loadUsers();

  } catch (e) {
    message(e.message, "error");
  }
}


// ============================================================
// EDIT USER - INLINE
// ============================================================

async function editUser(id) {
  try {
    const user = await api(`/api/users/${id}`);

    const tableEl = document.querySelector("#usersList table");

    if (!tableEl) {
      message("Users table not found.", "error");
      return;
    }

    const rows = Array.from(
      tableEl.querySelectorAll("tbody tr")
    );

    const row = rows.find(
      (r) =>
        r.children[0] &&
        r.children[0].textContent.trim() === String(id)
    );

    if (!row) {
      message("User row not found.", "error");
      return;
    }

    row.innerHTML = `
      <td>
        ${user.id}
      </td>

      <td>
        <input
          type="text"
          class="master-inline-input"
          id="editUserUsername_${id}"
          value="${esc(user.username || "")}"
        >
      </td>

      <td>
        <input
          type="text"
          class="master-inline-input"
          id="editUserFullName_${id}"
          value="${esc(user.full_name || "")}"
        >
      </td>

      <td>
        <select
          class="master-inline-input"
          id="editUserRole_${id}"
        >
          <option
            value="OPERATOR"
            ${user.role === "OPERATOR" ? "selected" : ""}
          >
            OPERATOR
          </option>

          <option
            value="MANAGER"
            ${user.role === "MANAGER" ? "selected" : ""}
          >
            MANAGER
          </option>

          <option
            value="ADMIN"
            ${user.role === "ADMIN" ? "selected" : ""}
          >
            ADMIN
          </option>
        </select>
      </td>

      <td>
        <select class="master-inline-input" id="editUserProjects_${id}" multiple size="3">
          ${projects.map((project) => '<option value="' + project.id + '"' + ((user.project_ids || []).map(Number).includes(Number(project.id)) ? " selected" : "") + '>' + esc(project.name) + '</option>').join("")}
        </select>
        <small>${user.role === "ADMIN" ? "Admins can access all projects." : "Ctrl-click to select multiple projects"}</small>
      </td>

      <td>
        <select
          class="master-inline-input"
          id="editUserStatus_${id}"
        >
          <option
            value="true"
            ${user.is_active ? "selected" : ""}
          >
            Active
          </option>

          <option
            value="false"
            ${!user.is_active ? "selected" : ""}
          >
            Inactive
          </option>
        </select>
      </td>

      <td>
        <button
          class="btn btn-sm btn-success"
          onclick="saveUser(${id})"
        >
          Save
        </button>

        <button
          class="btn btn-sm"
          onclick="loadUsers()"
        >
          Cancel
        </button>
      </td>
    `;

    document
      .querySelector(`#editUserUsername_${id}`)
      ?.focus();

  } catch (e) {
    message(e.message, "error");
  }
}


// ============================================================
// SAVE USER EDIT
// ============================================================

async function saveUser(id) {
  try {
    const username = document
      .querySelector(`#editUserUsername_${id}`)
      ?.value.trim();

    const fullName = document
      .querySelector(`#editUserFullName_${id}`)
      ?.value.trim();

    const role = document
      .querySelector(`#editUserRole_${id}`)
      ?.value;

    const isActive =
      document
        .querySelector(`#editUserStatus_${id}`)
        ?.value === "true";

    const projectIds = Array.from(
      document.querySelector("#editUserProjects_" + id)?.selectedOptions || [],
    ).map((option) => Number(option.value));

    if (!username) {
      throw Error("Username is required.");
    }

    if (!fullName) {
      throw Error("Full name is required.");
    }

    if (!["ADMIN", "MANAGER", "OPERATOR"].includes(role)) {
      throw Error("Invalid user role.");
    }

    if (
      me &&
      Number(id) === Number(me.id) &&
      !isActive
    ) {
      throw Error("You cannot deactivate your own account.");
    }

    const confirmed = confirm(
      `Save changes to user "${username}"?`
    );

    if (!confirmed) {
      return;
    }

    await api(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        username: username,
        role: role,
        full_name: fullName,
        is_active: isActive,
        project_ids: role === "ADMIN" ? [] : projectIds,
      }),
    });

    message(
      `User "${username}" updated successfully.`,
      "success"
    );

    await loadUsers();

  } catch (e) {
    message(e.message, "error");
  }
}


// ============================================================
// STATUS TOGGLE
// ============================================================

async function toggleUserActive(id, currentlyActive) {
  try {
    const user = await api(`/api/users/${id}`);

    const newStatus = !currentlyActive;

    if (
      me &&
      Number(id) === Number(me.id) &&
      !newStatus
    ) {
      throw Error("You cannot deactivate your own account.");
    }

    const confirmed = confirm(
      `${newStatus ? "Activate" : "Deactivate"} user "${user.username}"?`
    );

    if (!confirmed) {
      return;
    }

    await api(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        username: user.username,
        role: user.role,
        full_name: user.full_name,
        is_active: newStatus,
      }),
    });

    message(
      `User "${user.username}" is now ${
        newStatus ? "Active" : "Inactive"
      }.`,
      "success"
    );

    await loadUsers();

  } catch (e) {
    message(e.message, "error");
  }
}


// ============================================================
// RESET PASSWORD
// ============================================================

async function resetUserPassword(id) {
  try {
    const user = await api(`/api/users/${id}`);

    const newPassword = prompt(
      `Enter new password for "${user.username}":`
    );

    if (newPassword === null) {
      return;
    }

    if (!newPassword) {
      throw Error("New password is required.");
    }

    const confirmed = confirm(
      `Reset password for "${user.username}"?`
    );

    if (!confirmed) {
      return;
    }

    await api(`/api/users/${id}/reset-password`, {
      method: "POST",
      body: JSON.stringify({
        new_password: newPassword,
      }),
    });

    message(
      `Password for "${user.username}" was reset successfully.`,
      "success"
    );

  } catch (e) {
    message(e.message, "error");
  }
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
[
  "saveAdminEngineEvent",
  "deleteAdminEngineEvent",
  "reopenAdminShift",
  "saveAdminShiftOperationalData",
  "correctAdminOpeningFuel",
  "closeAdminShift",
  "saveAdminProduction",
  "deleteAdminProduction",
  "correctAdminReceipt",
  "correctAdminAdjustment",
  "correctAdminTransfer",
  "createAdminSounding",
  "correctAdminSounding",
  "deleteAdminSounding",
  "removeAdminShiftAttachment",
].forEach((name) => {
  const original = window[name];
  if (typeof original !== "function") return;
  window[name] = (...args) =>
    runAdminAction(`${name}:${args[0] ?? "selected"}`, () => original(...args));
});

let selectedIotPayload = null;
let iotPayloadOffset = 0;
const IOT_PAYLOAD_PAGE_SIZE = 100;

async function loadIotPayloads() {
  const status = $("iotStatusFilter")?.value || "";
  await api("/api/iot/payloads/process-ready", { method: "POST" });
  const rows = await api(`/api/iot/payloads?limit=${IOT_PAYLOAD_PAGE_SIZE}&offset=${iotPayloadOffset}${status ? `&status=${encodeURIComponent(status)}` : ""}`);
  $("iotPayloadList").innerHTML = `<table><thead><tr><th>ID</th><th>Received</th><th>External vessel</th><th>Window</th><th>Status</th><th>Issues</th><th></th></tr></thead><tbody>${rows.length ? rows.map((row) => `<tr>
    <td>${row.id}</td><td>${esc(formatDateTime(row.received_at))}</td><td>${esc(row.external_vessel_id || "—")}</td>
    <td>${esc(row.window_start ? `${formatDateTime(row.window_start)} – ${formatDateTime(row.window_end)}` : "—")}</td>
    <td>${esc(row.status)}</td><td>${esc((row.errors || []).join("; ") || (row.warnings || []).join("; ") || "—")}</td>
    <td><button class="btn btn-ghost" onclick="openIotPayload(${row.id})">Inspect</button></td></tr>`).join("") : `<tr><td colspan="7" class="muted">No payloads found.</td></tr>`}</tbody></table>`;
  $("iotPayloadPagination").innerHTML = `${iotPayloadOffset ? '<button class="btn btn-ghost" onclick="changeIotPayloadPage(-1)">Previous</button>' : ""}<span class="muted">Showing ${rows.length ? iotPayloadOffset + 1 : 0}–${iotPayloadOffset + rows.length}</span>${rows.length === IOT_PAYLOAD_PAGE_SIZE ? '<button class="btn btn-ghost" onclick="changeIotPayloadPage(1)">Next</button>' : ""}`;
}

function changeIotPayloadPage(direction) {
  iotPayloadOffset = Math.max(0, iotPayloadOffset + direction * IOT_PAYLOAD_PAGE_SIZE);
  loadIotPayloads().catch((error) => message(error.message, "error"));
}

async function openIotPayload(id) {
  const [payload, options] = await Promise.all([
    api(`/api/iot/payloads/${id}`), api("/api/iot/mapping-options"),
  ]);
  selectedIotPayload = payload;
  const names = [...new Set([
    ...(payload.raw_payload?.engineRunDetails || []).map((x) => x?.engine),
    ...(payload.raw_payload?.fuelStock || []).map((x) => x?.engine),
  ].filter((name) => typeof name === "string" && name.trim()).map((name) => name.trim()))];
  const currentVessel = options.vessels.find((v) => v.iot_vessel_id === payload.external_vessel_id);
  const canMap = ["AWAITING_MAPPING", "REJECTED"].includes(payload.status);
  $("iotPayloadDetail").innerHTML = `<div class="card mt8"><div class="section-head"><span class="dot"></span>Payload #${payload.id} · ${esc(payload.status)}</div>
    <p><strong>Received:</strong> ${esc(formatDateTime(payload.received_at))} · <strong>Internal vessel:</strong> ${esc(payload.vessel_id ?? "Not mapped")}</p>
    ${payload.errors?.length ? `<div class="note note-err">${payload.errors.map(esc).join("<br>")}</div>` : ""}
    ${payload.warnings?.length ? `<div class="note note-warn">${payload.warnings.map(esc).join("<br>")}</div>` : ""}
    ${payload.status === "READY" ? `<div class="flex mt8"><button class="btn btn-primary" onclick="applyReadyIotPayload(${payload.id})">Apply payload</button></div>` : ""}
    ${canMap ? `<div class="grid mt8"><div><label for="iotMapVessel">Map external vessel ${esc(payload.external_vessel_id || "")}</label><select id="iotMapVessel"><option value="">Select vessel</option>${options.vessels.map((v) => `<option value="${v.id}" ${currentVessel?.id === v.id ? "selected" : ""}>${esc(v.name)}${v.iot_vessel_id ? ` · ${esc(v.iot_vessel_id)}` : ""}</option>`).join("")}</select></div></div>
      <div id="iotEngineMappings" class="grid mt8">${names.map((name, i) => `<div><label for="iotEngineMap${i}">Vendor engine: ${esc(name)}</label><select id="iotEngineMap${i}" data-engine="${esc(name)}"><option value="">Select equipment</option></select></div>`).join("")}</div>
      <div class="flex mt8"><button class="btn btn-primary" onclick="saveIotPayloadMapping()">Save mapping and apply</button></div>` : ""}
    <details class="mt8"><summary>Raw JSON</summary><pre class="iot-raw-json">${esc(JSON.stringify(payload.raw_payload, null, 2))}</pre></details>
    ${payload.result ? `<details class="mt8"><summary>Processing result</summary><pre class="iot-raw-json">${esc(JSON.stringify(payload.result, null, 2))}</pre></details>` : ""}
    </div>`;
  if (canMap) {
    const fill = () => {
      const vesselId = Number($("iotMapVessel").value);
      const choices = options.equipment.filter((e) => e.vessel_id === vesselId);
      document.querySelectorAll("#iotEngineMappings select").forEach((sel) => {
        const current = choices.find((e) => e.iot_engine_name?.toLowerCase() === sel.dataset.engine.toLowerCase());
        sel.innerHTML = `<option value="">Select equipment</option>${choices.map((e) => `<option value="${e.id}" ${current?.id === e.id ? "selected" : ""}>${esc(e.name)}${e.iot_engine_name ? ` · ${esc(e.iot_engine_name)}` : ""}</option>`).join("")}`;
      });
    };
    $("iotMapVessel").addEventListener("change", fill);
    fill();
  }
}

async function applyReadyIotPayload(id) {
  try {
    const outcome = await api(`/api/iot/payloads/${id}/reprocess`, { method: "POST" });
    message(outcome.status === "PROCESSED" ? "Payload applied to its reporting-date shift." : `Payload status: ${outcome.status}.`, outcome.status === "PROCESSED" ? "success" : "warn");
    await loadIotPayloads();
    await openIotPayload(id);
  } catch (error) { message(error.message, "error"); }
}

async function saveIotPayloadMapping() {
  try {
    const vesselId = Number($("iotMapVessel").value);
    if (!vesselId) throw Error("Select the internal vessel.");
    const vendorId = String(selectedIotPayload.external_vessel_id || "").trim();
    if (!vendorId) throw Error("This payload has no valid external vessel ID to map.");
    const engineSelects = [...document.querySelectorAll("#iotEngineMappings select")];
    if (engineSelects.some((item) => !item.value)) throw Error("Map each vendor engine name to existing equipment before applying.");
    await api(`/api/iot/vessels/${vesselId}/mapping`, { method: "PUT", body: JSON.stringify({ iot_vessel_id: vendorId }) });
    for (const item of engineSelects) {
      await api(`/api/iot/equipment/${Number(item.value)}/mapping`, { method: "PUT", body: JSON.stringify({ iot_engine_name: item.dataset.engine }) });
    }
    const result = await api(`/api/iot/payloads/${selectedIotPayload.id}`);
    message(result.status === "PROCESSED" ? "Mappings saved and queued payloads were applied in reporting-window order." : `Mappings saved. Payload status: ${result.status}.`, result.status === "PROCESSED" ? "success" : "warn");
    await loadIotPayloads();
    await openIotPayload(selectedIotPayload.id);
  } catch (error) { message(error.message, "error"); }
}

$("iotStatusFilter")?.addEventListener("change", () => {
  iotPayloadOffset = 0;
  loadIotPayloads().catch((error) => message(error.message, "error"));
});

document.querySelectorAll(".tab-btn").forEach((b) =>
  b.addEventListener("click", async () => {
    if (b.dataset.page === "adminShifts" && me.role !== "ADMIN") {
      message("Only an administrator can manage shifts.", "error");
      return;
    }

    document
      .querySelectorAll(".tabPage")
      .forEach((x) => x.classList.add("hidden"));
    $(b.dataset.page).classList.remove("hidden");
    document
      .querySelectorAll(".tab-btn")
      .forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    try {
      if (b.dataset.page === "transfers") {
        await loadTransfers();
        if (me.role === "OPERATOR") showTransferView("issues");
      }
      if (b.dataset.page === "production") await loadProduction();
      if (b.dataset.page === "soundings") await loadSoundingShift();
      if (b.dataset.page === "dashboard") await loadDashboard();
      if (b.dataset.page === "charts") await loadCharts();
      if (b.dataset.page === "users" && me.role === "ADMIN") await loadUsers();
      if (b.dataset.page === "adminShifts" && me.role === "ADMIN") await loadAdminShifts();
      if (b.dataset.page === "audit" && me.role === "ADMIN") await loadAudit(true);
      if (b.dataset.page === "iotInbox" && me.role === "ADMIN") await loadIotPayloads();
    } catch (e) {
      message(e.message, "error");
    }
  }),
);
document.querySelectorAll("[data-transfer-view]").forEach((button) =>
  button.addEventListener("click", () => showTransferView(button.dataset.transferView)),
);
$('issueSourceVessel').addEventListener("change", refreshIssueShift);
$('issueDate').addEventListener("change", refreshIssueShift);
$('issueShift').addEventListener("change", refreshIssueShift);
$('changeOpeningFuelButton').addEventListener('click', changeOpeningFuel);
$("shiftVessel").addEventListener("change", refreshShiftEquipment);
$("transferFrom").addEventListener("change", refreshTransferShifts);
$("transferTo").addEventListener("change", refreshTransferShifts);
$("transferDate").addEventListener("change", refreshTransferShifts);
$("transferShift").addEventListener("change", refreshTransferShifts);
$("soundingVessel").addEventListener("change", loadSoundingShift);
$("soundingDate").addEventListener("change", loadSoundingShift);
$("soundingShift").addEventListener("change", loadSoundingShift);
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
