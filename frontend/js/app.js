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
  ["shiftDate", "productionDate", "soundingDate", "dashTo"].forEach(
    (id) => ($(id).value = today()),
  );
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
  select("transferFrom", vessels);
  select("transferTo", vessels);
  populateFuelSources();
  select("productionVessel", vessels);
  select("soundingVessel", vessels);
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
      `Shift #${s.id} · ${s.status} · opening ${f(s.opening_fuel)} L`;

    await loadShiftReport();
    await loadShiftAttachments();
  } catch (e) {
    message(e.message, "error");
  }
}
async function establishInitialOpening() {
  try {
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

    table(
      "shiftReport",
      [
        "Opening",
        "Received",
        "Transfer in",
        "Engine use",
        "Transfer out",
        "Adjustments",
        "Advancement",
        "Dredging hours",
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
          activeShift.advancement_m == null ? "—" : f(activeShift.advancement_m),
          activeShift.dredging_hours == null ? "—" : f(activeShift.dredging_hours),
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
          t.adjustment_direction === "IN" ? "Adjustment In" : "Adjustment Out";
      }

      const type = String(t.transaction_type || "").replaceAll("_", " ");

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
        remarks: $("engineRemarks").value.trim() || null,
      }),
    });

    message(
      `Engine event recorded: ${f(consumption)} L over ${hours.toFixed(2)} hours (${lph.toFixed(2)} L/hr).`,
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

  lphField.value = lph.toFixed(3);

  display.textContent = `Calculated ${hours.toFixed(2)} hours × ${lph.toFixed(2)} L/hr = ${f(consumption)} L`;

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

async function getCurrentTransferShift(vesselId) {
  const todayDate = today();

  // First check Morning.
  try {
    const morning = await api(
      `/api/fuel/shift?${params({
        vessel_id: vesselId,
        shift_date: todayDate,
        shift_name: "MORNING",
      })}`,
    );

    if (morning && morning.status === "OPEN") {
      return morning;
    }
  } catch (e) {
    // Morning does not exist yet.
  }

  // Morning is closed or unavailable, so use Evening.
  try {
    const evening = await api(
      `/api/fuel/shift?${params({
        vessel_id: vesselId,
        shift_date: todayDate,
        shift_name: "EVENING",
      })}`,
    );

    if (evening && evening.status === "OPEN") {
      return evening;
    }
  } catch (e) {
    // Evening does not exist yet.
  }

  throw new Error(
    `No open shift found for vessel ${vesselId} today.`,
  );
}


async function createTransfer() {
  try {
    const fromVesselId = n($("transferFrom").value);
    const toVesselId = n($("transferTo").value);
    const selectedShift = $("transferShift").value;
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

    async function getShift(vesselId, shiftName) {
      return await api(
        `/api/fuel/shift?${params({
          vessel_id: vesselId,
          shift_date: today(),
          shift_name: shiftName,
        })}`,
      );
    }

    async function getCurrentShift(vesselId) {
      // Check Morning first.
      try {
        const morning = await getShift(vesselId, "MORNING");

        if (morning && morning.status === "OPEN") {
          return morning;
        }
      } catch (e) {
        // Morning does not exist.
      }

      // Morning is closed/not available, so use Evening.
      try {
        const evening = await getShift(vesselId, "EVENING");

        if (evening && evening.status === "OPEN") {
          return evening;
        }
      } catch (e) {
        // Evening does not exist.
      }

      throw Error(
        `No open current shift found for vessel ${vesselId}.`,
      );
    }

    let fromShift;
    let toShift;

    if (selectedShift) {
      // User explicitly selected Morning or Evening.
      fromShift = await getShift(fromVesselId, selectedShift);
      toShift = await getShift(toVesselId, selectedShift);

      if (!fromShift || fromShift.status !== "OPEN") {
        throw Error(
          `Source vessel does not have an open ${selectedShift.toLowerCase()} shift today.`,
        );
      }

      if (!toShift || toShift.status !== "OPEN") {
        throw Error(
          `Destination vessel does not have an open ${selectedShift.toLowerCase()} shift today.`,
        );
      }
    } else {
      // Auto mode.
      fromShift = await getCurrentShift(fromVesselId);
      toShift = await getCurrentShift(toVesselId);
    }

    const r = await api("/api/transfers", {
      method: "POST",
      body: JSON.stringify({
        from_vessel_id: fromVesselId,
        from_shift_id: fromShift.id,

        to_vessel_id: toVesselId,
        to_shift_id: toShift.id,

        initiated_quantity: quantity,
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
      x.from_vessel_id,
      x.to_vessel_id,
      f(x.initiated_quantity),
      f(x.received_quantity),
      f(x.loss_quantity),
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
              `${f(t.initiated_quantity)} L`,
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
      ["Current fuel", d.total_fuel],
      ["Received", d.total_received],
      ["Consumption", d.total_consumption],
      ["Transfer out", d.total_transfer_out],
      ["Advancement", d.total_advancement_m],
      ["Dredging hours", d.total_dredging_hours],
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
        "Transfer In",
        "Engine",
        "Transfer Out",
        "Closing",
        "Advancement",
        "Dredging Hours",
        "Flags",
      ],
      d.rows.map((x) => [
        x.shift_date,
        esc(x.vessel_name),
        esc(x.shift_name),
        f(x.opening_fuel),
        f(x.received_fuel),
        f(x.transfer_in),
        f(x.total_engine_consumption),
        f(x.transfer_out),
        f(x.closing_fuel),
        x.advancement_m == null ? "—" : f(x.advancement_m),
        x.dredging_hours == null ? "—" : f(x.dredging_hours),
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
              maximumFractionDigits: 2,
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
                      Number(
                        context.raw
                      ).toFixed(2)
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
                    ).toLocaleString()} L`,
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
                      value.toLocaleString()
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
    ["ID", "Project", "Site", "Vessel", "Code", "Type", "Threshold", "Status", "Actions"],
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
        f(x.fuel_threshold_litres),
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
      x.vessel_id,
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
      ["ID", "Username", "Name", "Role", "Status", "Actions"],
      rows.map((x) => [
        x.id,

        esc(x.username),

        esc(x.full_name),

        esc(x.role),

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
      if (b.dataset.page === "soundings") await loadSoundingShift();
      if (b.dataset.page === "dashboard") await loadDashboard();
      if (b.dataset.page === "charts") await loadCharts();
      if (b.dataset.page === "users" && me.role === "ADMIN") await loadUsers();
      if (b.dataset.page === "audit" && me.role === "ADMIN") await loadAudit(true);
    } catch (e) {
      message(e.message, "error");
    }
  }),
);
$('changeOpeningFuelButton').addEventListener('click', changeOpeningFuel);
$("shiftVessel").addEventListener("change", refreshShiftEquipment);
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
