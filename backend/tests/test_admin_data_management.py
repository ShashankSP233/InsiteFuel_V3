import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from inspect import signature
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from backend.models.audit_log import AuditLog
from backend.models.attachment import Attachment
from backend.models.fuel import AdjustmentDirection, FuelTransaction, FuelTransactionType
from backend.models.production import ProductionRecord
from backend.models.shift import Shift
from backend.models.shift_attachments import ShiftAttachment
from backend.models.sounding import Sounding
from backend.models.transfer import FuelTransfer, TransferStatus
from backend.models.user import UserRole
from backend.routes.fuel import (
    admin_correct_receipt,
    admin_close_shift,
    admin_correct_adjustment,
    admin_correct_opening,
    admin_correct_receipt,
    admin_update_shift_operational_data,
    list_admin_shifts,
)
from backend.routes.production import (
    admin_create_production,
    admin_delete_production,
    admin_update_production,
)
from backend.schemas.fuel import AdminReceiptCorrection
from backend.schemas.production import ProductionCreate
from backend.routes.shift_attachments import remove_shift_attachment
from backend.routes.soundings import (
    admin_create_sounding,
    admin_delete_sounding,
    admin_update_sounding,
)
from backend.routes.transfer import admin_correct_transfer
from backend.services.fuel_service import FuelService
from backend.services.production_service import ProductionService
from backend.services.shift_attachment_service import ShiftAttachmentService
from backend.services.sounding_service import SoundingService
from backend.services.transfer_service import TransferService


class FakeResult:
    def __init__(self, value=None):
        self.value = value

    def first(self):
        return self.value


class FakeSession:
    def __init__(self, records=None, scalar_results=None, scalar_value=None):
        self.records = records or {}
        self.scalar_results = list(scalar_results or [])
        self.scalar_value = scalar_value
        self.added = []
        self.deleted = []
        self.next_id = 100

    def get(self, model, entity_id):
        return self.records.get((model, entity_id))

    def add(self, entity):
        if getattr(entity, "id", None) is None:
            entity.id = self.next_id
            self.next_id += 1
        self.added.append(entity)

    def flush(self):
        pass

    def scalar(self, statement):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return self.scalar_value

    def scalars(self, statement):
        return FakeResult()

    def delete(self, entity):
        self.deleted.append(entity)


class TransferSession(FakeSession):
    def __init__(self, *args, query_first_results=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.query_first_results = list(query_first_results or [])

    def scalars(self, statement):
        value = self.query_first_results.pop(0) if self.query_first_results else None
        return FakeResult(value)


def stub_row_locks(testcase):
    """
    Fake sessions cannot run SELECT ... FOR UPDATE, so resolve the row-lock
    helpers through db.get() instead. Locking itself is covered by the
    real-database tests in test_shift_creation_rules.py.
    """
    def lock_vessels(db, vessel_ids):
        return {}

    def lock_shifts(db, shift_ids):
        return {shift_id: db.get(Shift, shift_id) for shift_id in shift_ids}

    for name, replacement in (("lock_vessels", lock_vessels), ("lock_shifts", lock_shifts)):
        patcher = patch.object(FuelService, name, side_effect=replacement)
        patcher.start()
        testcase.addCleanup(patcher.stop)


class ReceiptSession(FakeSession):
    def __init__(self, *args, scalar_results=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.scalar_results = list(scalar_results or [])

    def scalar(self, statement):
        return self.scalar_results.pop(0) if self.scalar_results else None


class AdminDataManagementTests(unittest.TestCase):
    def setUp(self):
        stub_row_locks(self)

    def test_new_admin_routes_reject_non_admin(self):
        endpoints = (
            list_admin_shifts,
            admin_close_shift,
            admin_update_shift_operational_data,
            admin_correct_adjustment,
            admin_correct_opening,
            admin_correct_receipt,
            admin_correct_transfer,
            admin_create_production,
            admin_update_production,
            admin_delete_production,
            admin_create_sounding,
            admin_update_sounding,
            admin_delete_sounding,
            remove_shift_attachment,
        )
        admin = SimpleNamespace(id=1, role=UserRole.ADMIN.value)
        operator = SimpleNamespace(id=2, role=UserRole.OPERATOR.value)
        for endpoint in endpoints:
            dependency = signature(endpoint).parameters["current_user"].default.dependency
            with self.subTest(endpoint=endpoint.__name__):
                with self.assertRaises(HTTPException) as error:
                    dependency(current_user=operator)
                self.assertEqual(error.exception.status_code, 403)
                self.assertIs(dependency(current_user=admin), admin)

    def test_production_update_and_delete_are_audited(self):
        production = SimpleNamespace(
            id=13,
            project_id=2,
            vessel_id=3,
            shift_id=4,
            production_date=date(2026, 10, 13),
            as_per_qty=Decimal("10.000"),
            true_qty=Decimal("9.000"),
            fuel_rate=Decimal("0.500"),
            remarks="before",
        )
        shift = SimpleNamespace(id=4, vessel_id=3, shift_date=date(2026, 10, 13))
        vessel = SimpleNamespace(id=3, project_id=2)
        project = SimpleNamespace(id=2)
        db = FakeSession(
            records={
                (ProductionRecord, 13): production,
                (Shift, 4): shift,
                (type("Vessel", (), {}), 3): vessel,
                (type("Project", (), {}), 2): project,
            }
        )
        from backend.models.project import Project
        from backend.models.vessel import Vessel

        db.records[(Vessel, 3)] = vessel
        db.records[(Project, 2)] = project
        updated = ProductionService.update_production(
            db,
            production_id=13,
            as_per_qty=Decimal("12"),
            true_qty=Decimal("11"),
            fuel_rate=Decimal("0.6"),
            remarks="corrected",
            corrected_by_user_id=1,
            reason="Corrected report",
        )
        audit = next(item for item in db.added if isinstance(item, AuditLog))
        self.assertIs(updated, production)
        self.assertEqual(audit.old_values["true_qty"], "9.000")
        self.assertEqual(audit.new_values["true_qty"], "11")
        self.assertEqual(audit.reason, "Corrected report")

        delete_db = FakeSession(records={(ProductionRecord, 13): production})
        ProductionService.delete_production(
            delete_db,
            production_id=13,
            deleted_by_user_id=1,
            reason="Duplicate row",
        )
        delete_audit = next(item for item in delete_db.added if isinstance(item, AuditLog))
        self.assertEqual(delete_audit.action, "DELETE_PRODUCTION_RECORD")
        self.assertEqual(delete_audit.old_values["shift_id"], 4)
        self.assertIsNone(delete_audit.new_values)
        self.assertEqual(delete_db.deleted, [production])

    def test_admin_production_create_rejects_duplicate_shift_record(self):
        data = ProductionCreate(
            project_id=2,
            vessel_id=3,
            shift_id=4,
            production_date=date(2026, 10, 13),
            as_per_qty=Decimal("10"),
            true_qty=Decimal("9"),
        )
        with patch.object(
            ProductionService,
            "list_production",
            return_value=[SimpleNamespace(id=13)],
        ), patch.object(ProductionService, "create_production") as create:
            with self.assertRaises(HTTPException) as error:
                admin_create_production(
                    data,
                    db=Mock(),
                    current_user=SimpleNamespace(id=1, role=UserRole.ADMIN.value),
                )
        self.assertEqual(error.exception.status_code, 400)
        create.assert_not_called()

    def test_production_update_rejects_invalid_associations_and_reason(self):
        production = SimpleNamespace(
            id=13,
            project_id=2,
            vessel_id=3,
            shift_id=4,
            production_date=date(2026, 10, 13),
            as_per_qty=Decimal("10"),
            true_qty=Decimal("9"),
            fuel_rate=None,
            remarks=None,
        )
        shift = SimpleNamespace(id=4, vessel_id=999, shift_date=date(2026, 10, 13))
        from backend.models.project import Project
        from backend.models.vessel import Vessel

        db = FakeSession(records={
            (ProductionRecord, 13): production,
            (Shift, 4): shift,
            (Vessel, 3): SimpleNamespace(id=3, project_id=2),
            (Project, 2): SimpleNamespace(id=2),
        })
        with self.assertRaisesRegex(ValueError, "does not match"):
            ProductionService.update_production(
                db,
                production_id=13,
                as_per_qty=Decimal("10"),
                true_qty=Decimal("9"),
                fuel_rate=None,
                remarks=None,
                corrected_by_user_id=1,
                reason="Correction",
            )
        shift.vessel_id = 3
        with self.assertRaisesRegex(ValueError, "reason is required"):
            ProductionService.update_production(
                db,
                production_id=13,
                as_per_qty=Decimal("10"),
                true_qty=Decimal("9"),
                fuel_rate=None,
                remarks=None,
                corrected_by_user_id=1,
                reason="  ",
            )

    def test_sounding_attachment_correction_and_delete_keep_shared_file(self):
        shift = SimpleNamespace(
            id=4,
            vessel_id=3,
            status="OPEN",
            shift_date=date(2026, 10, 13),
        )
        old_attachment = SimpleNamespace(id=21, content_type="image/jpeg")
        new_attachment = SimpleNamespace(id=22, content_type="image/png")
        sounding = SimpleNamespace(
            id=31,
            shift_id=4,
            vessel_id=3,
            report_date=date(2026, 10, 13),
            attachment_id=21,
            submitted_at=datetime(2026, 10, 13, tzinfo=timezone.utc),
            submitted_by_user_id=6,
        )
        db = FakeSession(
            records={
                (Shift, 4): shift,
                (Sounding, 31): sounding,
                (Attachment, 22): new_attachment,
            },
            scalar_results=[shift, shift, 2],
        )
        updated = SoundingService.update_sounding_attachment(
            db,
            sounding_id=31,
            shift_id=4,
            attachment_id=22,
            corrected_by_user_id=1,
            reason="Replace blurred image",
        )
        audit = next(item for item in db.added if isinstance(item, AuditLog))
        self.assertIs(updated, sounding)
        self.assertEqual(sounding.attachment_id, 22)
        self.assertEqual(audit.old_values["attachment_id"], 21)
        self.assertEqual(audit.new_values["attachment_id"], 22)
        self.assertEqual(audit.reason, "Replace blurred image")

        SoundingService.delete_sounding(
            db,
            sounding_id=31,
            shift_id=4,
            deleted_by_user_id=1,
            reason="Duplicate sounding",
        )
        self.assertIn(sounding, db.deleted)
        self.assertNotIn(old_attachment, db.deleted)
        delete_audit = [item for item in db.added if isinstance(item, AuditLog)][-1]
        self.assertEqual(delete_audit.old_values["attachment_id"], 22)
        self.assertIsNone(delete_audit.new_values)

    def test_sounding_last_record_and_wrong_shift_are_rejected(self):
        shift = SimpleNamespace(id=4, vessel_id=3, status="OPEN")
        sounding = SimpleNamespace(
            id=31,
            shift_id=4,
            vessel_id=3,
            report_date=date(2026, 10, 13),
            attachment_id=21,
            submitted_at=datetime(2026, 10, 13, tzinfo=timezone.utc),
            submitted_by_user_id=6,
        )
        db = FakeSession(records={(Shift, 4): shift, (Sounding, 31): sounding}, scalar_results=[shift, 1])
        with self.assertRaisesRegex(ValueError, "last sounding"):
            SoundingService.delete_sounding(
                db,
                sounding_id=31,
                shift_id=4,
                deleted_by_user_id=1,
                reason="Remove",
            )
        other_shift = SimpleNamespace(
            id=99,
            vessel_id=3,
            status="OPEN",
            shift_date=date(2026, 10, 14),
        )
        db.records[(Shift, 99)] = other_shift
        db.scalar_results = [other_shift]
        with self.assertRaisesRegex(ValueError, "does not belong"):
            SoundingService.delete_sounding(
                db,
                sounding_id=31,
                shift_id=99,
                deleted_by_user_id=1,
                reason="Remove",
            )
        self.assertEqual(db.deleted, [])

    def test_shift_attachment_unlink_retains_shared_file_and_audits(self):
        link = SimpleNamespace(
            id=5,
            shift_id=4,
            attachment_id=21,
            attachment_type="BILL",
        )
        db = FakeSession(records={(ShiftAttachment, 5): link})
        ShiftAttachmentService.remove_link(
            db,
            shift_id=4,
            link_id=5,
            removed_by_user_id=1,
            reason="Wrong shift document",
        )
        self.assertEqual(db.deleted, [link])
        audit = next(item for item in db.added if isinstance(item, AuditLog))
        self.assertEqual(audit.old_values["attachment_id"], 21)
        self.assertEqual(audit.reason, "Wrong shift document")

    def test_adjustment_correction_is_append_only_and_blocks_successors(self):
        original = SimpleNamespace(
            id=17,
            shift_id=4,
            vessel_id=3,
            transaction_type=FuelTransactionType.ADJUSTMENT.value,
            adjustment_direction=AdjustmentDirection.IN.value,
            reference_type=None,
            quantity=Decimal("8.000"),
        )
        shift = SimpleNamespace(
            id=4,
            vessel_id=3,
            status="OPEN",
            shift_date=date(2026, 10, 13),
        )
        db = FakeSession(
            records={(FuelTransaction, 17): original, (Shift, 4): shift},
            # 1st: locked re-query of the adjustment, 2nd: later-shift check (none)
            scalar_results=[original, None],
        )
        with patch.object(FuelService, "recalculate_shift"):
            FuelService.correct_adjustment(
                db,
                adjustment_id=17,
                new_quantity=Decimal("6"),
                new_direction=AdjustmentDirection.OUT,
                corrected_by_user_id=1,
                correction_remarks="Corrected direction",
            )
        transactions = [item for item in db.added if isinstance(item, FuelTransaction)]
        audit = next(item for item in db.added if isinstance(item, AuditLog))
        self.assertEqual(len(transactions), 2)
        self.assertEqual(original.quantity, Decimal("8.000"))
        self.assertEqual(audit.reason, "Corrected direction")
        self.assertEqual(audit.old_values["effective_transaction_id"], 17)

        blocked_db = FakeSession(
            records={(FuelTransaction, 17): original, (Shift, 4): shift},
            # 1st: locked re-query of the adjustment, 2nd: later-shift check (found)
            scalar_results=[original, 19],
        )
        with self.assertRaisesRegex(ValueError, "subsequent shifts"):
            FuelService.correct_adjustment(
                blocked_db,
                adjustment_id=17,
                new_quantity=Decimal("6"),
                new_direction=AdjustmentDirection.OUT,
                corrected_by_user_id=1,
                correction_remarks="Correction",
            )
        self.assertEqual(blocked_db.added, [])

    def test_opening_correction_is_local_audited_and_rejects_successors(self):
        shift = SimpleNamespace(
            id=4,
            vessel_id=3,
            status="OPEN",
            shift_date=date(2026, 10, 13),
            opening_fuel=Decimal("100"),
            calculated_closing_fuel=Decimal("90"),
        )
        db = FakeSession(records={(Shift, 4): shift})
        with patch.object(
            FuelService,
            "lock_vessel_shifts",
            return_value=[shift],
        ), patch.object(
            FuelService,
            "calculate_shift_balance",
            return_value={"closing_fuel": Decimal("95")},
        ):
            FuelService.correct_admin_opening_fuel(
                db,
                shift_id=4,
                new_opening_fuel=Decimal("105"),
                corrected_by_user_id=1,
                reason="Opening reading correction",
            )

        audit = next(item for item in db.added if isinstance(item, AuditLog))
        self.assertEqual(shift.opening_fuel, Decimal("105"))
        self.assertEqual(shift.calculated_closing_fuel, Decimal("95"))
        self.assertEqual(audit.old_values["opening_fuel"], "100")
        self.assertEqual(audit.old_values["calculated_closing_fuel"], "90")
        self.assertEqual(audit.new_values["opening_fuel"], "105")
        self.assertEqual(audit.reason, "Opening reading correction")

        blocked_shift = SimpleNamespace(**shift.__dict__)
        blocked_shift.opening_fuel = Decimal("105")
        later_shift = SimpleNamespace(
            id=5,
            vessel_id=3,
            status="OPEN",
            shift_date=date(2026, 10, 14),
            opening_fuel=Decimal("95"),
            calculated_closing_fuel=Decimal("90"),
        )
        blocked_db = FakeSession(records={(Shift, 4): blocked_shift})
        with patch.object(
            FuelService,
            "lock_vessel_shifts",
            return_value=[blocked_shift, later_shift],
        ):
            with self.assertRaisesRegex(ValueError, "later shifts"):
                FuelService.correct_admin_opening_fuel(
                    blocked_db,
                    shift_id=4,
                    new_opening_fuel=Decimal("106"),
                    corrected_by_user_id=1,
                    reason="Correction",
                )
        self.assertEqual(blocked_shift.opening_fuel, Decimal("105"))
        self.assertEqual(blocked_db.added, [])

    def test_existing_opening_correction_rejects_successors_without_cascade(self):
        shift = SimpleNamespace(
            id=4,
            vessel_id=3,
            shift_date=date(2026, 10, 13),
            opening_fuel=Decimal("100"),
            calculated_closing_fuel=Decimal("95"),
        )
        later = SimpleNamespace(
            id=5,
            vessel_id=3,
            shift_date=date(2026, 10, 14),
            opening_fuel=Decimal("95"),
            calculated_closing_fuel=Decimal("90"),
        )
        db = FakeSession(records={(Shift, 4): shift})
        with patch.object(FuelService, "lock_vessel_shifts", return_value=[shift, later]):
            with self.assertRaisesRegex(ValueError, "later shifts exist"):
                FuelService.correct_opening_fuel(
                    db,
                    shift_id=4,
                    new_opening_fuel=Decimal("105"),
                    corrected_by_user_id=1,
                    reason="Correction",
                )
        self.assertEqual(shift.opening_fuel, Decimal("100"))
        self.assertEqual(later.opening_fuel, Decimal("95"))
        self.assertEqual(db.added, [])

    def test_receipt_correction_updates_only_receipt_and_audits(self):
        from backend.models.fuel import FuelTransactionType
        from backend.models.vessel import Vessel

        transaction_date = datetime(2026, 10, 13, 9, tzinfo=timezone.utc)
        receipt = SimpleNamespace(
            id=61,
            shift_id=4,
            vessel_id=3,
            transaction_type=FuelTransactionType.RECEIPT.value,
            reference_type=None,
            reference_id=None,
            quantity=Decimal("25.000"),
            source_vessel_id=None,
            fuel_source="Supplier A",
            transaction_date=transaction_date,
            remarks="before",
        )
        shift = SimpleNamespace(
            id=4,
            vessel_id=3,
            status="OPEN",
            shift_date=date(2026, 10, 13),
            opening_fuel=Decimal("100"),
        )
        source_vessel = SimpleNamespace(id=8, is_active=True)
        unrelated = SimpleNamespace(quantity=Decimal("19"))
        db = ReceiptSession(
            records={
                (Vessel, 8): source_vessel,
                (FuelTransaction, 61): receipt,
                (Shift, 4): shift,
            },
            # 1st: locked re-query of the receipt, 2nd: later-shift check
            scalar_results=[receipt, None],
        )
        with patch.object(
            FuelService,
            "calculate_shift_balance",
            return_value={"closing_fuel": Decimal("125")},
        ), patch.object(FuelService, "recalculate_shift") as recalculate:
            result = FuelService.correct_admin_receipt(
                db,
                transaction_id=61,
                quantity=Decimal("30"),
                source_vessel_id=8,
                fuel_source=None,
                remarks="corrected",
                corrected_by_user_id=1,
                reason="Receipt quantity correction",
            )

        self.assertIs(result, receipt)
        self.assertEqual(receipt.quantity, Decimal("30"))
        self.assertEqual(receipt.source_vessel_id, 8)
        self.assertIsNone(receipt.fuel_source)
        self.assertEqual(receipt.transaction_date, transaction_date)
        self.assertEqual(unrelated.quantity, Decimal("19"))
        recalculate.assert_called_once_with(db, 4)
        audit = next(item for item in db.added if isinstance(item, AuditLog))
        self.assertEqual(audit.action, "CORRECT_FUEL_RECEIPT")
        self.assertEqual(audit.old_values["quantity"], "25.000")
        self.assertEqual(audit.new_values["quantity"], "30")
        self.assertEqual(audit.reason, "Receipt quantity correction")

    def test_receipt_correction_rejects_other_types_links_and_successors(self):
        from backend.models.fuel import FuelTransactionType

        shift = SimpleNamespace(
            id=4,
            vessel_id=3,
            status="OPEN",
            shift_date=date(2026, 10, 13),
        )
        invalid_type = SimpleNamespace(
            id=62,
            shift_id=4,
            vessel_id=3,
            transaction_type=FuelTransactionType.TRANSFER_IN.value,
        )
        invalid_db = ReceiptSession(
            records={(FuelTransaction, 62): invalid_type, (Shift, 4): shift},
            scalar_results=[invalid_type],
        )
        with self.assertRaisesRegex(ValueError, "Only RECEIPT"):
            FuelService.correct_admin_receipt(
                invalid_db,
                transaction_id=62,
                quantity=Decimal("1"),
                source_vessel_id=None,
                fuel_source=None,
                remarks=None,
                corrected_by_user_id=1,
                reason="Correction",
            )

        linked = SimpleNamespace(
            id=63,
            shift_id=4,
            vessel_id=3,
            transaction_type=FuelTransactionType.RECEIPT.value,
            reference_type="SOURCE_RECORD",
            reference_id=12,
        )
        linked_db = ReceiptSession(
            records={(FuelTransaction, 63): linked, (Shift, 4): shift},
            scalar_results=[linked],
        )
        with self.assertRaisesRegex(ValueError, "Linked receipt"):
            FuelService.correct_admin_receipt(
                linked_db,
                transaction_id=63,
                quantity=Decimal("2"),
                source_vessel_id=None,
                fuel_source=None,
                remarks=None,
                corrected_by_user_id=1,
                reason="Correction",
            )

        receipt = SimpleNamespace(
            id=64,
            shift_id=4,
            vessel_id=3,
            transaction_type=FuelTransactionType.RECEIPT.value,
            reference_type=None,
            reference_id=None,
            quantity=Decimal("2"),
            source_vessel_id=None,
            fuel_source=None,
            transaction_date=datetime(2026, 10, 13, tzinfo=timezone.utc),
            remarks=None,
        )
        successor_db = ReceiptSession(
            records={(FuelTransaction, 64): receipt, (Shift, 4): shift},
            # 1st: locked re-query of the receipt, 2nd: later-shift check (found)
            scalar_results=[receipt, 9],
        )
        with self.assertRaisesRegex(ValueError, "later shifts"):
            FuelService.correct_admin_receipt(
                successor_db,
                transaction_id=64,
                quantity=Decimal("3"),
                source_vessel_id=None,
                fuel_source=None,
                remarks=None,
                corrected_by_user_id=1,
                reason="Correction",
            )
        self.assertEqual(receipt.quantity, Decimal("2"))

    def test_rejected_receipt_route_rolls_back_without_commit(self):
        db = Mock()
        data = AdminReceiptCorrection(
            quantity=Decimal("10"),
            reason="Correct receipt",
        )
        with patch.object(
            FuelService,
            "correct_admin_receipt",
            side_effect=ValueError("later shifts exist"),
        ):
            with self.assertRaises(HTTPException) as error:
                admin_correct_receipt(
                    61,
                    data,
                    db=db,
                    current_user=SimpleNamespace(id=1, role=UserRole.ADMIN.value),
                )
        self.assertEqual(error.exception.status_code, 400)
        db.rollback.assert_called_once()
        db.commit.assert_not_called()

    def test_approved_transfer_correction_reverses_both_sides(self):
        from_shift = SimpleNamespace(
            id=4,
            vessel_id=3,
            shift_date=date(2026, 10, 13),
        )
        to_shift = SimpleNamespace(
            id=7,
            vessel_id=8,
            shift_date=date(2026, 10, 13),
        )
        transfer = SimpleNamespace(
            id=41,
            status=TransferStatus.BALANCES_UPDATED.value,
            from_shift_id=4,
            from_vessel_id=3,
            to_shift_id=7,
            to_vessel_id=8,
            initiated_quantity=Decimal("50"),
            received_quantity=Decimal("48"),
            loss_quantity=Decimal("2"),
            manager_remark="Reviewed earlier",
            notes="original",
        )
        source = SimpleNamespace(
            id=51,
            shift_id=4,
            vessel_id=3,
            transaction_type=FuelTransactionType.TRANSFER_OUT.value,
            quantity=Decimal("50"),
        )
        destination = SimpleNamespace(
            id=52,
            shift_id=7,
            vessel_id=8,
            transaction_type=FuelTransactionType.TRANSFER_IN.value,
            quantity=Decimal("48"),
        )
        db = TransferSession(
            records={
                (FuelTransfer, 41): transfer,
                (Shift, 4): from_shift,
                (Shift, 7): to_shift,
            },
            query_first_results=[source, None, destination, None],
        )

        with patch(
            "backend.services.transfer_service.FuelService.calculate_shift_balance",
            side_effect=[{"closing_fuel": Decimal("100")}, {"closing_fuel": Decimal("20")}],
        ), patch("backend.services.transfer_service.FuelService.recalculate_shift") as recalculate:
            corrected = TransferService.correct_approved_transfer(
                db,
                transfer_id=41,
                corrected_by_user_id=1,
                initiated_quantity=Decimal("60"),
                received_quantity=Decimal("52"),
                correction_reason="Correct quantity",
                notes="corrected",
            )

        entries = [item for item in db.added if isinstance(item, FuelTransaction)]
        self.assertIs(corrected, transfer)
        self.assertEqual(len(entries), 4)
        self.assertEqual([entry.shift_id for entry in entries], [4, 4, 7, 7])
        self.assertEqual(
            [entry.transaction_type for entry in entries],
            [
                FuelTransactionType.TRANSFER_IN.value,
                FuelTransactionType.TRANSFER_OUT.value,
                FuelTransactionType.TRANSFER_OUT.value,
                FuelTransactionType.TRANSFER_IN.value,
            ],
        )
        self.assertEqual([entry.quantity for entry in entries], [50, 60, 48, 52])
        self.assertEqual(source.quantity, Decimal("50"))
        self.assertEqual(destination.quantity, Decimal("48"))
        self.assertEqual(transfer.loss_quantity, Decimal("8.000"))
        self.assertEqual(transfer.manager_remark, "Reviewed earlier")
        self.assertEqual(recalculate.call_count, 2)
        audit = next(item for item in db.added if isinstance(item, AuditLog))
        self.assertEqual(audit.reason, "Correct quantity")
        self.assertEqual(audit.old_values["manager_remark"], "Reviewed earlier")
        self.assertEqual(audit.new_values["manager_remark"], "Reviewed earlier")
        self.assertEqual(audit.old_values["initiated_quantity"], "50")
        self.assertEqual(audit.new_values["received_quantity"], "52")

    def test_approved_transfer_correction_blocks_downstream_shifts(self):
        source_shift = SimpleNamespace(id=4, vessel_id=3, shift_date=date(2026, 10, 13))
        destination_shift = SimpleNamespace(id=7, vessel_id=8, shift_date=date(2026, 10, 13))
        transfer = SimpleNamespace(
            id=41,
            status=TransferStatus.BALANCES_UPDATED.value,
            from_shift_id=4,
            from_vessel_id=3,
            to_shift_id=7,
            to_vessel_id=8,
            initiated_quantity=Decimal("50"),
            received_quantity=Decimal("48"),
            manager_remark=None,
            notes=None,
        )
        db = TransferSession(
            records={
                (FuelTransfer, 41): transfer,
                (Shift, 4): source_shift,
                (Shift, 7): destination_shift,
            },
            scalar_value=99,
        )
        with self.assertRaisesRegex(ValueError, "subsequent shifts"):
            TransferService.correct_approved_transfer(
                db,
                transfer_id=41,
                corrected_by_user_id=1,
                initiated_quantity=Decimal("60"),
                received_quantity=Decimal("52"),
                manager_remark="Correction",
            )
        self.assertEqual(db.added, [])


if __name__ == "__main__":
    unittest.main()
