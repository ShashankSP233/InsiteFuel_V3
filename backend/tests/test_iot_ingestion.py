"""
Scenario tests for IoT ingestion against a real in-memory SQLite database
(same approach as test_shift_creation_rules.py).
"""
import json
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import backend.models  # noqa: F401  (registers every table on Base.metadata)
from backend.config import settings
from backend.database import Base
from backend.models.engine import EngineEvent
from backend.models.equipment import Equipment
from backend.models.iot import IotPayload, IotPayloadStatus
from backend.models.fuel import FuelTransaction
from backend.models.shift import Shift
from backend.models.vessel import Vessel
from backend.services.fuel_service import FuelService
from backend.services.iot_service import AWAITING_MAPPING, DUPLICATE, PROCESSED, REJECTED, IotService
from backend.utils.time import now_ist

SAMPLE = Path(__file__).resolve().parents[2] / "smaplextrl.json"


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


def naive(value):
    return value.replace(tzinfo=None)


def payload(start="2026-10-05 00:00", end="2026-10-05 11:59", runs=None, stock=None, vessel_id=133719):
    return {
        "vesselId": vessel_id,
        "vesselName": "PRINCESA DE GOA",
        "startTime": start,
        "endTime": end,
        "fuelStock": stock if stock is not None else [
            {"engine": "Port", "rob": 0, "refill": 50, "drain": 0},
            {"engine": "Starboard", "rob": 0, "refill": 0, "drain": 0},
        ],
        "engineRunDetails": runs if runs is not None else [
            {"engine": "Port", "startTime": "01:00", "stopTime": "03:00", "fuelConsumed": 100},
            {"engine": "Starboard", "startTime": "04:00", "stopTime": "05:00", "fuelConsumed": 40},
            {"engine": "Port DG", "startTime": "06:00", "stopTime": "07:00", "fuelConsumed": "N/A"},
        ],
        "totals": [],
    }


class IotIngestionTest(unittest.TestCase):
    PRIOR_DAY = __import__("datetime").date(2026, 10, 4)

    def setUp(self):
        settings.iot_post_refills_to_ledger = True
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()

        vessel = Vessel(
            project_id=1, name="Princesa", code="PDG", vessel_type="Dredger",
            is_active=True, fuel_threshold_litres=Decimal("0"), iot_vessel_id="133719",
        )
        self.db.add(vessel)
        self.db.flush()
        self.vessel = vessel
        for name, iot_name in (("Port ME", "Port"), ("Starboard ME", "Starboard")):
            self.db.add(Equipment(vessel_id=vessel.id, name=name, equipment_type="ME", iot_engine_name=iot_name))

        # The vessel's first shifts are created manually (opening fuel 1000 L).
        # The chain ends on 04-Oct EVENING, so IoT creates 05-Oct MORNING next.
        morning = FuelService.establish_initial_opening_fuel(
            self.db, vessel.id, self.PRIOR_DAY, Decimal("1000"), created_by_user_id=1
        )
        FuelService.recalculate_shift(self.db, morning.id)
        morning.status = "CLOSED"
        self.db.flush()
        evening = FuelService.get_or_create_shift(self.db, vessel.id, self.PRIOR_DAY, "EVENING", 1)
        FuelService.recalculate_shift(self.db, evening.id)
        evening.status = "CLOSED"
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def shifts(self):
        return list(self.db.scalars(select(Shift).order_by(Shift.id)).all())

    # -- happy path --------------------------------------------------------
    def test_creates_and_populates_an_open_iot_shift(self):
        outcome = IotService.ingest(self.db, payload())
        self.assertEqual(outcome.status, PROCESSED, outcome.errors)

        shift = self.db.get(Shift, outcome.shift_id)
        self.assertEqual((shift.shift_name, shift.status, shift.source), ("MORNING", "OPEN", "IOT"))
        self.assertEqual(Decimal(str(shift.opening_fuel)), Decimal("1000"))
        self.assertEqual(Decimal(str(shift.advancement_m)), Decimal("0"))
        self.assertEqual(Decimal(str(shift.dredging_hours)), Decimal("0"))
        # 1000 + 50 refill - 100 - 40
        self.assertEqual(Decimal(str(shift.calculated_closing_fuel)), Decimal("910"))

        events = self.db.scalars(select(EngineEvent).where(EngineEvent.shift_id == shift.id)).all()
        self.assertEqual(len(events), 2)  # the N/A DG run is skipped
        self.assertEqual(
            sorted(Decimal(str(event.consumption)) for event in events),
            [Decimal("40.000"), Decimal("100.000")],
        )  # JSON fuelConsumed values are already litres; no ml conversion.
        transactions = self.db.scalars(
            select(FuelTransaction).where(
                FuelTransaction.shift_id == shift.id,
                FuelTransaction.transaction_type == "ENGINE_CONSUMPTION",
            )
        ).all()
        self.assertEqual(
            sorted(Decimal(str(transaction.quantity)) for transaction in transactions),
            [Decimal("40.000"), Decimal("100.000")],
        )
        self.assertEqual(outcome.result["runs_without_fuel_skipped"], 1)
        self.assertTrue(any("no measured fuel" in w for w in outcome.warnings))

        expected = now_ist() + timedelta(hours=settings.iot_shift_auto_close_hours)
        self.assertLess(abs(naive(shift.auto_close_at) - naive(expected)), timedelta(minutes=1))

    def test_engine_consumption_keeps_three_decimal_litre_precision(self):
        data = payload(runs=[
            {"engine": "Port", "startTime": "01:00", "stopTime": "02:00", "fuelConsumed": 7.123},
        ])
        outcome = IotService.ingest(self.db, data)
        self.assertEqual(outcome.status, PROCESSED, outcome.errors)

        event = self.db.scalar(select(EngineEvent).where(EngineEvent.shift_id == outcome.shift_id))
        transaction = self.db.scalar(
            select(FuelTransaction).where(
                FuelTransaction.shift_id == outcome.shift_id,
                FuelTransaction.transaction_type == "ENGINE_CONSUMPTION",
            )
        )
        self.assertEqual(Decimal(str(event.consumption)), Decimal("7.123"))
        self.assertEqual(Decimal(str(transaction.quantity)), Decimal("7.123"))

    # -- idempotency / conflicts ---------------------------------------------
    def test_resending_identical_payload_is_a_duplicate(self):
        original = IotService.ingest(self.db, payload())
        again = IotService.ingest(self.db, payload())
        self.assertEqual(again.status, DUPLICATE)
        self.assertNotEqual(again.payload_id, original.payload_id)
        self.assertEqual(self.db.get(IotPayload, again.payload_id).status, IotPayloadStatus.DUPLICATE)
        self.assertEqual(len(self.shifts()), 3)  # two manual + one IoT shift

    def test_same_window_with_different_content_is_rejected(self):
        IotService.ingest(self.db, payload())
        changed = payload(runs=[{"engine": "Port", "startTime": "01:00", "stopTime": "02:00", "fuelConsumed": 5}])
        outcome = IotService.ingest(self.db, changed)
        self.assertEqual(outcome.status, REJECTED)
        self.assertTrue(any("different content" in e for e in outcome.errors))

    def test_later_window_stops_if_previous_payload_was_applied_to_wrong_shift(self):
        first = IotService.ingest(self.db, payload())
        first_row = self.db.get(IotPayload, first.payload_id)
        first_row.shift_date = self.PRIOR_DAY
        first_row.shift_name = "EVENING"
        self.db.commit()

        later = IotService.ingest(self.db, payload(
            start="2026-10-05 12:00", end="2026-10-05 23:59", runs=[], stock=[]
        ))

        self.assertEqual(later.status, REJECTED)
        self.assertTrue(any("Correct that earlier shift" in error for error in later.errors))

    # -- rejections keep the payload and change nothing ------------------------
    def test_unknown_vessel_awaits_mapping_and_is_stored(self):
        outcome = IotService.ingest(self.db, payload(vessel_id=999))
        self.assertEqual(outcome.status, AWAITING_MAPPING)
        row = self.db.get(IotPayload, outcome.payload_id)
        self.assertEqual(row.status, AWAITING_MAPPING)
        self.assertEqual(row.raw_payload["vesselId"], 999)
        self.assertEqual(len(self.shifts()), 2)

    def test_unmapped_engine_awaits_mapping_without_creating_records(self):
        bad = payload(runs=[
            {"engine": "Port", "startTime": "01:00", "stopTime": "02:00", "fuelConsumed": 10},
            {"engine": "Mystery", "startTime": "03:00", "stopTime": "04:00", "fuelConsumed": 10},
        ])
        outcome = IotService.ingest(self.db, bad)
        self.assertEqual(outcome.status, AWAITING_MAPPING)
        self.assertTrue(any("Mystery" in e for e in outcome.errors))
        self.assertEqual(len(self.shifts()), 2)
        self.assertEqual(self.db.scalar(select(func.count(EngineEvent.id))), 0)

    def test_mapping_a_waiting_payload_applies_it_automatically(self):
        self.vessel.iot_vessel_id = None
        self.db.commit()
        first = IotService.ingest(self.db, payload())
        self.assertEqual(first.status, AWAITING_MAPPING)

        self.vessel.iot_vessel_id = "133719"
        self.db.commit()
        IotService.refresh_mapping_status(self.db)
        row = self.db.get(IotPayload, first.payload_id)
        self.assertEqual(row.status, PROCESSED)
        self.assertIsNotNone(row.shift_id)
        self.assertEqual(row.id, first.payload_id)

    def test_mapping_applies_queued_windows_in_chronological_order(self):
        self.vessel.iot_vessel_id = None
        self.db.commit()
        morning = IotService.ingest(self.db, payload())
        evening = IotService.ingest(self.db, payload(
            start="2026-10-05 12:00", end="2026-10-05 23:59", runs=[], stock=[]
        ))
        self.assertEqual((morning.status, evening.status), (AWAITING_MAPPING, AWAITING_MAPPING))

        self.vessel.iot_vessel_id = "133719"
        self.db.commit()
        IotService.refresh_mapping_status(self.db)

        morning_row = self.db.get(IotPayload, morning.payload_id)
        evening_row = self.db.get(IotPayload, evening.payload_id)
        self.assertEqual((morning_row.status, evening_row.status), (PROCESSED, PROCESSED))
        self.assertEqual(self.db.get(Shift, morning_row.shift_id).shift_name, "MORNING")
        self.assertEqual(self.db.get(Shift, evening_row.shift_id).shift_name, "EVENING")

    def test_reprocessing_pending_duplicate_does_not_create_an_extra_shift(self):
        self.vessel.iot_vessel_id = None
        self.db.commit()
        pending = IotService.ingest(self.db, payload())
        self.vessel.iot_vessel_id = "133719"
        self.db.commit()
        self.assertEqual(IotService.ingest(self.db, payload()).status, PROCESSED)
        row = self.db.get(IotPayload, pending.payload_id)
        duplicate = IotService.ingest(self.db, row.raw_payload, existing=row)
        self.assertEqual(duplicate.status, DUPLICATE)
        self.assertEqual(self.db.get(IotPayload, pending.payload_id).status, IotPayloadStatus.DUPLICATE)
        self.assertEqual(len(self.shifts()), 3)

    def test_vessel_without_any_shift_is_rejected(self):
        other = Vessel(
            project_id=1, name="Other", code="OTH", vessel_type="Dredger",
            is_active=True, fuel_threshold_litres=Decimal("0"), iot_vessel_id="777",
        )
        self.db.add(other)
        self.db.commit()
        outcome = IotService.ingest(self.db, payload(vessel_id=777, runs=[], stock=[]))
        self.assertEqual(outcome.status, REJECTED)
        self.assertTrue(any("first-ever" in e for e in outcome.errors))

    def test_older_window_after_a_newer_one_is_rejected(self):
        IotService.ingest(self.db, payload(start="2026-10-05 12:00", end="2026-10-05 23:59", runs=[], stock=[]))
        outcome = IotService.ingest(self.db, payload(runs=[], stock=[]))
        self.assertEqual(outcome.status, REJECTED)
        self.assertTrue(any("oldest first" in e for e in outcome.errors))

    def test_shift_uses_window_date_and_sequence_not_clock_cutoff(self):
        # Both windows start after noon; their order still determines the shift.
        a = IotService.ingest(self.db, payload(start="2026-10-05 12:10", end="2026-10-05 23:59", runs=[], stock=[]))
        b = IotService.ingest(self.db, payload(start="2026-10-05 23:50", end="2026-10-06 11:59", runs=[], stock=[]))
        c = IotService.ingest(self.db, payload(start="2026-10-06 06:00", end="2026-10-06 17:59", runs=[], stock=[]))
        names = [(self.db.get(Shift, o.shift_id).shift_date.isoformat(), self.db.get(Shift, o.shift_id).shift_name) for o in (a, b, c)]
        self.assertEqual(names, [("2026-10-05", "MORNING"), ("2026-10-05", "EVENING"), ("2026-10-06", "MORNING")])
        self.assertEqual([o.status for o in (a, b, c)], [PROCESSED] * 3)

    def test_third_window_for_same_date_is_rejected(self):
        IotService.ingest(self.db, payload(start="2026-10-05 06:00", end="2026-10-05 11:59", runs=[], stock=[]))
        IotService.ingest(self.db, payload(start="2026-10-05 12:00", end="2026-10-05 17:59", runs=[], stock=[]))
        third = IotService.ingest(self.db, payload(start="2026-10-05 18:00", end="2026-10-05 23:59", runs=[], stock=[]))
        self.assertEqual(third.status, REJECTED)
        self.assertTrue(any("Two reporting windows" in e for e in third.errors))

    def test_morning_window_uses_its_date_even_when_latest_shift_is_prior_morning(self):
        prior_evening = self.db.scalar(select(Shift).where(
            Shift.vessel_id == self.vessel.id,
            Shift.shift_date == self.PRIOR_DAY,
            Shift.shift_name == "EVENING",
        ))
        self.db.delete(prior_evening)
        self.db.commit()

        outcome = IotService.ingest(self.db, payload(runs=[], stock=[]))

        shift = self.db.get(Shift, outcome.shift_id)
        self.assertEqual((shift.shift_date.isoformat(), shift.shift_name), ("2026-10-05", "MORNING"))

    # -- shift chain ---------------------------------------------------------
    def test_next_window_closes_the_previous_open_iot_shift(self):
        morning = IotService.ingest(self.db, payload())
        evening = IotService.ingest(
            self.db,
            payload(start="2026-10-05 12:00", end="2026-10-05 23:59", runs=[
                {"engine": "Port", "startTime": "13:00", "stopTime": "14:00", "fuelConsumed": 20},
            ], stock=[]),
        )
        self.assertEqual(evening.status, PROCESSED, evening.errors)
        old = self.db.get(Shift, morning.shift_id)
        self.assertEqual((old.status, old.close_source), ("CLOSED", "AUTO_IOT"))
        new = self.db.get(Shift, evening.shift_id)
        self.assertEqual(new.shift_name, "EVENING")
        self.assertEqual(Decimal(str(new.opening_fuel)), Decimal("910"))
        self.assertEqual(Decimal(str(new.calculated_closing_fuel)), Decimal("890"))

    def test_earlier_manual_open_shift_blocks_ingestion(self):
        manual = FuelService.get_or_create_shift(
            self.db, self.vessel.id, __import__("datetime").date(2026, 10, 5), "MORNING", 1
        )
        self.db.commit()
        outcome = IotService.ingest(self.db, payload(runs=[], stock=[]))
        self.assertEqual(outcome.status, REJECTED)
        self.assertTrue(any("manually managed" in e for e in outcome.errors))
        self.assertEqual(self.db.get(Shift, manual.id).status, "OPEN")

    # -- auto close ----------------------------------------------------------
    def test_sweep_closes_only_due_iot_shifts_and_waives_manual_requirements(self):
        outcome = IotService.ingest(self.db, payload())
        shift = self.db.get(Shift, outcome.shift_id)

        # Not due yet -> untouched.
        self.assertEqual(IotService.close_due_shifts(self.db)["closed"], [])
        self.assertEqual(self.db.get(Shift, shift.id).status, "OPEN")

        # 11 hours later -> closed, although there is no sounding / dredging data.
        later = now_ist() + timedelta(hours=settings.iot_shift_auto_close_hours, minutes=1)
        result = IotService.close_due_shifts(self.db, now=later)
        self.assertEqual(result["closed"], [shift.id])
        self.db.expire_all()
        closed = self.db.get(Shift, shift.id)
        self.assertEqual((closed.status, closed.close_source), ("CLOSED", "AUTO_IOT"))
        self.assertIsNotNone(closed.closed_at)

    def test_manual_close_still_requires_sounding_and_dredger_data(self):
        outcome = IotService.ingest(self.db, payload())
        with self.assertRaises(ValueError):
            FuelService.close_shift(self.db, outcome.shift_id, closed_by_user_id=1)

    def test_reopened_iot_shift_is_not_auto_closed_again(self):
        outcome = IotService.ingest(self.db, payload())
        later = now_ist() + timedelta(hours=settings.iot_shift_auto_close_hours, minutes=1)
        IotService.close_due_shifts(self.db, now=later)
        FuelService.reopen_shift(self.db, outcome.shift_id, reopened_by_user_id=1, reason="correction")
        self.db.commit()
        self.assertEqual(IotService.close_due_shifts(self.db, now=later + timedelta(days=1))["closed"], [])
        self.assertEqual(self.db.get(Shift, outcome.shift_id).status, "OPEN")

    # -- vendor sample ---------------------------------------------------------
    def test_vendor_sample_first_window_rejected_second_processed(self):
        morning_raw, evening_raw = json.loads(SAMPLE.read_text())
        first = IotService.ingest(self.db, morning_raw)
        self.assertEqual(first.status, REJECTED)
        self.assertTrue(any("overlapping" in e for e in first.errors))

        second = IotService.ingest(self.db, evening_raw)
        self.assertEqual(second.status, PROCESSED, second.errors)
        self.assertEqual(second.result["shift_name"], "EVENING")
        self.assertEqual(second.result["shift_date"], "2026-10-05")
        self.assertEqual(second.result["engine_events_created"], 4)
        self.assertEqual(second.result["runs_without_fuel_skipped"], 4)


if __name__ == "__main__":
    unittest.main()
