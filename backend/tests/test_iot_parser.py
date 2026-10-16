"""Tests for the IoT payload parser (pure logic, no database)."""
import copy
import json
import unittest
from decimal import Decimal
from pathlib import Path

from backend.services.iot_parser import parse_payload

SAMPLE = Path(__file__).resolve().parents[2] / "smaplextrl.json"


def good_payload():
    return {
        "vesselId": 133719,
        "vesselName": "PRINCESA DE GOA",
        "startTime": "2026-10-05 00:00",
        "endTime": "2026-10-05 11:59",
        "fuelStock": [
            {"engine": "Port", "rob": 900, "refill": 10, "drain": 0},
        ],
        "engineRunDetails": [
            {"engine": "Port", "startTime": "01:00", "stopTime": "02:00",
             "durationInSeconds": 3600, "fuelConsumed": 12.5},
            {"engine": "Port DG", "startTime": "03:00", "stopTime": "04:00",
             "runTimeInSeconds": 3600, "fuelConsumed": "N/A"},
        ],
        "totals": [],
    }


class ParserTest(unittest.TestCase):
    def test_clean_payload_has_no_errors_or_warnings(self):
        parsed = parse_payload(good_payload())
        self.assertEqual(parsed.errors, [])
        self.assertEqual(parsed.warnings, [])
        self.assertEqual(parsed.external_vessel_id, "133719")
        self.assertEqual(len(parsed.runs), 2)
        self.assertEqual(parsed.runs[0].fuel_litres, Decimal("12.5"))
        self.assertEqual(parsed.runs[0].hours, Decimal(1))
        self.assertIsNone(parsed.runs[1].fuel_litres)  # "N/A" => not measured

    def test_window_crossing_midnight_places_runs_on_the_right_day(self):
        p = good_payload()
        p["startTime"], p["endTime"] = "2026-10-05 18:00", "2026-10-06 05:59"
        p["engineRunDetails"] = [
            {"engine": "Port", "startTime": "23:30", "stopTime": "00:30", "fuelConsumed": 4},
            {"engine": "Port", "startTime": "02:00", "stopTime": "03:00", "fuelConsumed": 4},
        ]
        parsed = parse_payload(p)
        self.assertEqual(parsed.errors, [])
        self.assertEqual(parsed.runs[0].start.day, 5)
        self.assertEqual(parsed.runs[0].stop.day, 6)
        self.assertEqual(parsed.runs[1].start.day, 6)

    def test_window_longer_than_a_day_is_rejected(self):
        p = good_payload()
        p["endTime"] = "2026-10-07 00:00"
        self.assertTrue(any("24 hours" in e for e in parse_payload(p).errors))

    def test_missing_vessel_id_and_bad_times(self):
        parsed = parse_payload({"startTime": "nonsense"})
        self.assertTrue(any("vesselId" in e for e in parsed.errors))
        self.assertTrue(any("startTime" in e for e in parsed.errors))
        self.assertTrue(any("endTime" in e for e in parsed.errors))

    def test_overlapping_runs_of_same_engine_are_rejected(self):
        p = good_payload()
        p["engineRunDetails"].append(
            {"engine": "Port", "startTime": "01:30", "stopTime": "02:30", "fuelConsumed": 1}
        )
        self.assertTrue(any("overlapping" in e for e in parse_payload(p).errors))

    def test_overlap_between_different_engines_is_fine(self):
        p = good_payload()
        p["engineRunDetails"].append(
            {"engine": "Starboard", "startTime": "01:30", "stopTime": "02:30", "fuelConsumed": 1}
        )
        self.assertEqual(parse_payload(p).errors, [])

    def test_run_outside_window_is_rejected(self):
        p = good_payload()
        p["engineRunDetails"][0].update(startTime="11:30", stopTime="12:30")
        self.assertTrue(any("outside the reporting window" in e for e in parse_payload(p).errors))

    def test_run_ending_at_window_end_label_is_inside(self):
        p = good_payload()
        p["engineRunDetails"][0].update(startTime="11:00", stopTime="11:59")
        self.assertEqual(parse_payload(p).errors, [])

    def test_stop_before_start_is_rejected(self):
        p = good_payload()
        p["engineRunDetails"][0].update(startTime="05:00", stopTime="04:00")
        self.assertTrue(any("not after" in e for e in parse_payload(p).errors))

    def test_negative_or_non_numeric_fuel_is_rejected(self):
        p = good_payload()
        p["engineRunDetails"][0]["fuelConsumed"] = -3
        self.assertTrue(any("negative" in e for e in parse_payload(p).errors))
        p = good_payload()
        p["engineRunDetails"][0]["fuelConsumed"] = "lots"
        self.assertTrue(any("not a number" in e for e in parse_payload(p).errors))

    def test_duration_mismatch_is_only_a_warning_and_times_win(self):
        p = good_payload()
        p["engineRunDetails"][0]["durationInSeconds"] = 999
        parsed = parse_payload(p)
        self.assertEqual(parsed.errors, [])
        self.assertTrue(any("vendor duration" in w for w in parsed.warnings))
        self.assertEqual(parsed.runs[0].hours, Decimal(1))

    def test_totals_mismatch_is_only_a_warning(self):
        p = good_payload()
        p["totals"] = [{"engine": "Port", "runTimeInSeconds": 3600, "fuelConsumed": 99}]
        parsed = parse_payload(p)
        self.assertEqual(parsed.errors, [])
        self.assertTrue(any("totals (Port)" in w for w in parsed.warnings))

    def test_duplicate_or_negative_stock_rows_are_rejected(self):
        p = good_payload()
        p["fuelStock"].append({"engine": "Port", "rob": 1, "refill": 0, "drain": 0})
        self.assertTrue(any("more than once" in e for e in parse_payload(p).errors))
        p = good_payload()
        p["fuelStock"][0]["refill"] = -1
        self.assertTrue(any("negative" in e for e in parse_payload(p).errors))

    def test_non_object_payload(self):
        self.assertTrue(parse_payload([1, 2]).errors)

    def test_vendor_sample_file(self):
        """The sample the vendor mailed: window 2 parses; window 1 has a duplicated Starboard run."""
        morning, evening = [parse_payload(p) for p in json.loads(SAMPLE.read_text())]
        self.assertEqual(evening.errors, [])
        self.assertEqual(len([r for r in evening.runs if r.fuel_litres]), 4)
        self.assertTrue(any("overlapping" in e and "Starboard" in e for e in morning.errors))
        # the sample's durations and totals are internally inconsistent -> warnings only
        self.assertTrue(evening.warnings)

    def test_input_is_not_mutated(self):
        p = good_payload()
        snapshot = copy.deepcopy(p)
        parse_payload(p)
        self.assertEqual(p, snapshot)


if __name__ == "__main__":
    unittest.main()
