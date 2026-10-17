"""
Parsing and validation of the shift-data payloads sent by the IoT vendor.

This module is deliberately free of database and framework imports so the
vendor's (somewhat loose) format is handled in one place and can be tested
on its own.

What the vendor sends (one JSON object per vessel per 12-hour window):

    vesselId, vesselName, startTime, endTime      "YYYY-MM-DD HH:MM"
    fuelStock[]          engine, rob, refill, drain
    engineRunDetails[]   engine, startTime/stopTime "HH:MM", fuelConsumed,
                         durationInSeconds OR runTimeInSeconds, ...
    rpmBucketsInSeconds[], totals[]   (informational only)

Rules applied here:

* ``startTime`` / ``stopTime`` of each run are authoritative.  The vendor's
  duration fields are only cross-checked (warning on mismatch).
* ``fuelConsumed`` is already in litres; numeric values are passed through
  unchanged (apart from the database's 0.001 L precision). ``null`` or
  ``"N/A"`` runs carry no measured fuel and are reported as skipped.
* ``totals`` is only cross-checked against the runs (warning on mismatch).
* The shift a window belongs to is selected by its local start date and time
  in iot_service: before noon is MORNING; noon or later is EVENING.
* Structural problems and overlapping runs of the same engine are *errors*:
  the payload is rejected rather than risk double-counting fuel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.utils.time import IST

# A reporting window is 12 hours in practice; refuse anything longer than a day.
MAX_WINDOW = timedelta(hours=24)

_DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S")
_TIME_FORMATS = ("%H:%M", "%H:%M:%S")

# Vendor duration vs. (stop - start) tolerance before we warn.
DURATION_TOLERANCE_SECONDS = 60
# Vendor totals vs. sum of runs tolerance (litres) before we warn.
FUEL_TOLERANCE_LITRES = Decimal("0.01")


@dataclass
class EngineRun:
    engine: str
    start: datetime
    stop: datetime
    fuel_litres: Decimal | None  # None => not measured ("N/A" / null)

    @property
    def hours(self) -> Decimal:
        return Decimal(str((self.stop - self.start).total_seconds())) / Decimal(3600)


@dataclass
class FuelStockRow:
    engine: str
    rob: Decimal
    refill: Decimal
    drain: Decimal


@dataclass
class ParsedWindow:
    external_vessel_id: str | None = None
    vessel_name: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    runs: list[EngineRun] = field(default_factory=list)
    stock: list[FuelStockRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------
def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def _parse_time(value: Any):
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _to_decimal(value: Any) -> Decimal | None:
    """Number -> Decimal. Raises ValueError for anything that is not a number."""
    if isinstance(value, bool):
        raise ValueError("boolean is not a number")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValueError(f"{value!r} is not a number") from exc
    raise ValueError(f"{value!r} is not a number")


def _is_not_measured(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and value.strip().upper() in {"", "N/A", "NA", "NULL", "-"}
    )


def _non_negative(row: dict, key: str, where: str, errors: list[str]) -> Decimal:
    raw = row.get(key)
    if raw is None:
        return Decimal(0)
    try:
        number = _to_decimal(raw)
    except ValueError as exc:
        errors.append(f"{where}: {key} {exc}.")
        return Decimal(0)
    if number < 0:
        errors.append(f"{where}: {key} cannot be negative ({number}).")
        return Decimal(0)
    return number


# ----------------------------------------------------------------------
# main entry point
# ----------------------------------------------------------------------
def parse_payload(raw: Any) -> ParsedWindow:
    """
    The target shift (MORNING/EVENING, date) is selected in iot_service from
    the reporting window's start time; this parser only validates the window.
    """
    result = ParsedWindow()
    errors, warnings = result.errors, result.warnings

    if not isinstance(raw, dict):
        errors.append("Payload must be a JSON object.")
        return result

    # -- vessel ----------------------------------------------------------
    vessel_id = raw.get("vesselId")
    if vessel_id is None or str(vessel_id).strip() == "":
        errors.append("vesselId is required.")
    else:
        result.external_vessel_id = str(vessel_id).strip()
    if isinstance(raw.get("vesselName"), str):
        result.vessel_name = raw["vesselName"].strip() or None

    # -- window ----------------------------------------------------------
    start = _parse_datetime(raw.get("startTime"))
    end = _parse_datetime(raw.get("endTime"))
    if start is None:
        errors.append("startTime is missing or not in 'YYYY-MM-DD HH:MM' format.")
    if end is None:
        errors.append("endTime is missing or not in 'YYYY-MM-DD HH:MM' format.")

    window_end_exclusive = None
    if start and end:
        if end <= start:
            errors.append("endTime must be after startTime.")
        elif end - start > MAX_WINDOW:
            errors.append("A reporting window cannot be longer than 24 hours.")
        else:
            result.window_start, result.window_end = start, end
            # endTime is a minute label ("11:59" means up to 11:59:59).
            window_end_exclusive = end + timedelta(minutes=1)

    # -- engine runs ----------------------------------------------------
    runs_raw = raw.get("engineRunDetails")
    if runs_raw is None:
        runs_raw = []
    if not isinstance(runs_raw, list):
        errors.append("engineRunDetails must be a list.")
        runs_raw = []

    for index, row in enumerate(runs_raw, start=1):
        where = f"engineRunDetails[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{where}: must be an object.")
            continue
        engine = row.get("engine")
        if not isinstance(engine, str) or not engine.strip():
            errors.append(f"{where}: engine is required.")
            continue
        engine = engine.strip()
        where = f"{where} ({engine})"

        t_start, t_stop = _parse_time(row.get("startTime")), _parse_time(row.get("stopTime"))
        if t_start is None or t_stop is None:
            errors.append(f"{where}: startTime/stopTime must be 'HH:MM'.")
            continue
        if result.window_start is None:
            continue  # window already invalid; cannot place the run in time
        # Runs carry only a time of day: place them on the window's date, or
        # the next day for a window that crosses midnight.
        crosses_midnight = result.window_start.date() != result.window_end.date()
        run_start = datetime.combine(result.window_start.date(), t_start, tzinfo=IST)
        if crosses_midnight and run_start < result.window_start:
            run_start += timedelta(days=1)
        run_stop = datetime.combine(run_start.date(), t_stop, tzinfo=IST)
        if crosses_midnight and run_stop <= run_start:
            run_stop += timedelta(days=1)
        if run_stop <= run_start:
            errors.append(f"{where}: stopTime {t_stop:%H:%M} is not after startTime {t_start:%H:%M}.")
            continue
        if run_start < result.window_start or run_stop > window_end_exclusive:
            errors.append(f"{where}: run {t_start:%H:%M}-{t_stop:%H:%M} lies outside the reporting window.")
            continue

        fuel: Decimal | None = None
        if not _is_not_measured(row.get("fuelConsumed")):
            try:
                fuel = _to_decimal(row.get("fuelConsumed"))
            except ValueError as exc:
                errors.append(f"{where}: fuelConsumed {exc}.")
                continue
            if fuel < 0:
                errors.append(f"{where}: fuelConsumed cannot be negative ({fuel}).")
                continue

        declared = row.get("durationInSeconds", row.get("runTimeInSeconds"))
        if declared is not None:
            try:
                declared_s = _to_decimal(declared)
                actual_s = Decimal(str((run_stop - run_start).total_seconds()))
                if abs(declared_s - actual_s) > DURATION_TOLERANCE_SECONDS:
                    warnings.append(
                        f"{where}: vendor duration {declared_s}s does not match "
                        f"{t_start:%H:%M}-{t_stop:%H:%M} ({actual_s}s); start/stop times were used."
                    )
            except ValueError:
                warnings.append(f"{where}: unreadable duration {declared!r} ignored.")

        result.runs.append(EngineRun(engine, run_start, run_stop, fuel))

    # overlapping runs of the same engine => the same running time would be counted twice
    by_engine: dict[str, list[EngineRun]] = {}
    for run in result.runs:
        by_engine.setdefault(run.engine, []).append(run)
    for engine, engine_runs in by_engine.items():
        engine_runs.sort(key=lambda r: r.start)
        for earlier, later in zip(engine_runs, engine_runs[1:]):
            if later.start < earlier.stop:
                errors.append(
                    f"Engine '{engine}' has overlapping runs "
                    f"{earlier.start:%H:%M}-{earlier.stop:%H:%M} and "
                    f"{later.start:%H:%M}-{later.stop:%H:%M}."
                )

    # -- fuel stock -----------------------------------------------------
    stock_raw = raw.get("fuelStock")
    if stock_raw is None:
        stock_raw = []
    if not isinstance(stock_raw, list):
        errors.append("fuelStock must be a list.")
        stock_raw = []
    seen_stock: set[str] = set()
    for index, row in enumerate(stock_raw, start=1):
        where = f"fuelStock[{index}]"
        if not isinstance(row, dict) or not isinstance(row.get("engine"), str) or not row["engine"].strip():
            errors.append(f"{where}: engine is required.")
            continue
        engine = row["engine"].strip()
        where = f"{where} ({engine})"
        if engine in seen_stock:
            errors.append(f"{where}: engine appears more than once in fuelStock.")
            continue
        seen_stock.add(engine)
        result.stock.append(
            FuelStockRow(
                engine=engine,
                rob=_non_negative(row, "rob", where, errors),
                refill=_non_negative(row, "refill", where, errors),
                drain=_non_negative(row, "drain", where, errors),
            )
        )

    _cross_check_totals(raw, result)
    return result


def _cross_check_totals(raw: dict, result: ParsedWindow) -> None:
    """Warn when the vendor's own ``totals`` disagree with the run list."""
    totals = raw.get("totals")
    if not isinstance(totals, list):
        return

    window_seconds = None
    if result.window_start and result.window_end:
        window_seconds = Decimal(str((result.window_end - result.window_start).total_seconds() + 60))

    engine_sum = Decimal(0)
    have_engine_rows = False
    for row in totals:
        if not isinstance(row, dict) or not isinstance(row.get("engine"), str):
            continue
        engine = row["engine"].strip()
        try:
            declared_fuel = None if _is_not_measured(row.get("fuelConsumed")) else _to_decimal(row.get("fuelConsumed"))
            declared_run = None if _is_not_measured(row.get("runTimeInSeconds")) else _to_decimal(row.get("runTimeInSeconds"))
        except ValueError:
            result.warnings.append(f"totals ({engine}): unreadable values ignored.")
            continue

        if engine.lower() == "total":
            if have_engine_rows and declared_fuel is not None and abs(declared_fuel - engine_sum) > FUEL_TOLERANCE_LITRES:
                result.warnings.append(
                    f"totals (Total): fuelConsumed {declared_fuel} does not equal the sum of the "
                    f"engine totals ({engine_sum})."
                )
            continue

        engine_runs = [r for r in result.runs if r.engine == engine]
        run_fuel = sum((r.fuel_litres for r in engine_runs if r.fuel_litres is not None), Decimal(0))
        run_seconds = sum((Decimal(str((r.stop - r.start).total_seconds())) for r in engine_runs), Decimal(0))
        if declared_fuel is not None:
            engine_sum += declared_fuel
            have_engine_rows = True
            if abs(declared_fuel - run_fuel) > FUEL_TOLERANCE_LITRES:
                result.warnings.append(
                    f"totals ({engine}): fuelConsumed {declared_fuel} does not match the sum of its "
                    f"runs ({run_fuel}); the individual runs were used."
                )
        if declared_run is not None:
            if window_seconds is not None and declared_run > window_seconds:
                result.warnings.append(
                    f"totals ({engine}): runTimeInSeconds {declared_run} is longer than the "
                    f"reporting window ({window_seconds}s)."
                )
            elif abs(declared_run - run_seconds) > DURATION_TOLERANCE_SECONDS:
                result.warnings.append(
                    f"totals ({engine}): runTimeInSeconds {declared_run} does not match its runs "
                    f"({run_seconds}s)."
                )
