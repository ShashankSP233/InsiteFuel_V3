from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from backend.models.fuel import (
    AdjustmentDirection,
    FuelTransaction,
    FuelTransactionType,
)
from backend.models.shift import Shift
from backend.models.vessel import Vessel
from backend.models.transfer import FuelTransfer, TransferStatus
from backend.models.transfer_attachment import TransferAttachment
from backend.services.audit_service import AuditService
from backend.utils.time import now_ist
from backend.models.sounding import Sounding


class FuelService:

    @staticmethod
    def lock_vessels(db: Session, vessel_ids: list[int]) -> dict[int, Vessel]:
        ordered_ids = sorted(set(vessel_ids))
        if not ordered_ids:
            return {}
        vessels = list(
            db.scalars(
                select(Vessel)
                .where(Vessel.id.in_(ordered_ids))
                .order_by(Vessel.id)
                .with_for_update()
            ).all()
        )
        locked = {vessel.id: vessel for vessel in vessels}
        if len(locked) != len(ordered_ids):
            raise ValueError("One or more vessels were not found.")
        return locked

    @staticmethod
    def lock_shifts(db: Session, shift_ids: list[int]) -> dict[int, Shift]:
        ordered_ids = sorted(set(shift_ids))
        if not ordered_ids:
            return {}
        shifts = list(
            db.scalars(
                select(Shift)
                .where(Shift.id.in_(ordered_ids))
                .order_by(Shift.id)
                .with_for_update()
            ).all()
        )
        locked = {shift.id: shift for shift in shifts}
        if len(locked) != len(ordered_ids):
            raise ValueError("One or more shifts were not found.")
        return locked

    @staticmethod
    def lock_vessel_shifts(db: Session, vessel_id: int) -> list[Shift]:
        FuelService.lock_vessels(db, [vessel_id])
        return list(
            db.scalars(
                select(Shift)
                .where(Shift.vessel_id == vessel_id)
                .order_by(Shift.id)
                .with_for_update()
            ).all()
        )

    # ------------------------------------------------------------------
    # Shift-ordering helpers.
    #
    # A vessel's shifts form one chain: MORNING -> EVENING -> next day's
    # MORNING. These are the single definition of "later" used by every
    # guard, so the rule cannot drift between services.
    # ------------------------------------------------------------------
    @staticmethod
    def _shift_rank(shift_name) -> int:
        """MORNING sorts before EVENING within the same date."""
        return 1 if getattr(shift_name, "value", shift_name) == "EVENING" else 0

    @staticmethod
    def shift_order_key(shift) -> tuple:
        return (
            shift.shift_date,
            FuelService._shift_rank(getattr(shift, "shift_name", None)),
            shift.id,
        )

    @staticmethod
    def is_later_shift(candidate, shift) -> bool:
        """In-memory check: is ``candidate`` chronologically after ``shift``?"""
        return FuelService.shift_order_key(candidate) > FuelService.shift_order_key(
            shift
        )

    @staticmethod
    def has_later_shift(db: Session, shift: Shift) -> bool:
        """Does this vessel have any shift chronologically after ``shift``?"""
        later = [Shift.shift_date > shift.shift_date]
        if FuelService._shift_rank(getattr(shift, "shift_name", None)) == 0:
            later.append(
                and_(
                    Shift.shift_date == shift.shift_date,
                    Shift.shift_name == "EVENING",
                )
            )
        return (
            db.scalar(
                select(Shift.id)
                .where(Shift.vessel_id == shift.vessel_id, or_(*later))
                .limit(1)
            )
            is not None
        )

    @staticmethod
    def get_or_create_shift(
        db: Session,
        vessel_id: int,
        shift_date: date,
        shift_name: str,
        created_by_user_id: int | None = None,
    ) -> Shift:
        """
        Get an existing shift or create it.

        Shift sequence:
            MORNING -> EVENING -> next day's MORNING

        Opening fuel is always inherited from the immediately
        preceding shift.

        A new shift can only be created when every earlier shift of the
        vessel is CLOSED.

        The first-ever MORNING shift requires an authorized
        opening fuel to be established separately.
        """

        shift_name = shift_name.upper()
        if shift_name not in ("MORNING", "EVENING"):
            raise ValueError(
                "shift_name must be either MORNING or EVENING."
            )

        # Serialise shift creation per vessel *before* looking anything up,
        # so two requests cannot both decide that the shift is missing.
        FuelService.lock_vessels(db, [vessel_id])

        # ---------------------------------------------------------
        # 1. Return existing shift
        # ---------------------------------------------------------
        shift = db.scalar(
            select(Shift)
            .where(
                Shift.vessel_id == vessel_id,
                Shift.shift_date == shift_date,
                Shift.shift_name == shift_name,
            )
            .with_for_update()
        )
        if shift:
            return shift

        # ---------------------------------------------------------
        # 2. Shifts that come before the new one in the chain
        # ---------------------------------------------------------
        earlier = [Shift.shift_date < shift_date]
        if shift_name == "EVENING":
            earlier.append(
                and_(
                    Shift.shift_date == shift_date,
                    Shift.shift_name == "MORNING",
                )
            )
        latest_first = (
            Shift.shift_date.desc(),
            case((Shift.shift_name == "EVENING", 1), else_=0).desc(),
            Shift.id.desc(),
        )

        # ---------------------------------------------------------
        # 3. No new shift while ANY earlier shift is still open
        # ---------------------------------------------------------
        open_shift = db.scalar(
            select(Shift)
            .where(
                Shift.vessel_id == vessel_id,
                or_(*earlier),
                Shift.status == "OPEN",
            )
            .order_by(*latest_first)
            .limit(1)
        )
        if open_shift is not None:
            raise ValueError(
                f"Previous open shift on {open_shift.shift_date.isoformat()} "
                f"({open_shift.shift_name}) exists. "
                "Close it before creating a new shift."
            )

        # ---------------------------------------------------------
        # 4. The latest earlier shift supplies the opening fuel
        # ---------------------------------------------------------
        previous_shift = db.scalar(
            select(Shift)
            .where(Shift.vessel_id == vessel_id, or_(*earlier))
            .order_by(*latest_first)
            .limit(1)
        )
        if previous_shift is None:
            raise ValueError(
                f"Cannot create {shift_name} shift for {shift_date}: "
                "no previous shift exists. The first-ever opening fuel "
                "must be established through the authorized initial-opening-fuel workflow."
            )
        if (
            previous_shift.calculated_closing_fuel is None
            or Decimal(str(previous_shift.calculated_closing_fuel)) < 0
        ):
            raise ValueError(
                f"Previous shift {previous_shift.id} does not have "
                "a valid calculated closing fuel."
            )

        # ---------------------------------------------------------
        # 5. Create the new shift using previous closing
        # ---------------------------------------------------------

        shift = Shift(
            vessel_id=vessel_id,
            shift_date=shift_date,
            shift_name=shift_name,
            opening_fuel=previous_shift.calculated_closing_fuel,
            status="OPEN",
        )

        db.add(shift)
        db.flush()

        AuditService.log(
            db=db,
            user_id=created_by_user_id,
            action="CREATE_SHIFT",
            entity="shifts",
            entity_id=shift.id,
            old_values=None,
            new_values={
                "vessel_id": shift.vessel_id,
                "shift_date": shift.shift_date.isoformat(),
                "shift_name": shift.shift_name,
                "opening_fuel": str(shift.opening_fuel),
                "status": shift.status,
            },
            details="Shift created automatically as part of fuel ledger activity.",
        )

        return shift

    @staticmethod
    def establish_initial_opening_fuel(
        db: Session,
        vessel_id: int,
        shift_date: date,
        opening_fuel: Decimal,
        created_by_user_id: int | None = None,
    ) -> Shift:
        """
        Establish the opening fuel for the first-ever MORNING shift
        of a vessel.

        This method is intentionally separate from normal shift creation.
        Authorization will be enforced by the API/service layer once
        authentication and roles are implemented.
        """

        if opening_fuel < 0:
            raise ValueError("Opening fuel cannot be negative.")

        FuelService.lock_vessels(db, [vessel_id])

        existing_shift = db.scalar(
            select(Shift).where(
                Shift.vessel_id == vessel_id,
                Shift.shift_date == shift_date,
                Shift.shift_name == "MORNING",
            )
        )

        if existing_shift is not None:
            raise ValueError(
                f"Morning shift already exists for vessel {vessel_id} "
                f"on {shift_date}."
            )

        previous_shift = db.scalar(
            select(Shift).where(
                Shift.vessel_id == vessel_id,
            )
            .order_by(
                Shift.shift_date.desc(),
                Shift.id.desc(),
            )
        )

        if previous_shift is not None:
            raise ValueError(
                "This vessel already has previous shifts. "
                "Opening fuel must be inherited from the previous shift."
            )

        shift = Shift(
            vessel_id=vessel_id,
            shift_date=shift_date,
            shift_name="MORNING",
            opening_fuel=opening_fuel,
            status="OPEN",
        )

        db.add(shift)
        db.flush()

        AuditService.log(
            db=db,
            user_id=created_by_user_id,
            action="ESTABLISH_INITIAL_OPENING_FUEL",
            entity="shifts",
            entity_id=shift.id,
            old_values=None,
            new_values={
                "vessel_id": shift.vessel_id,
                "shift_date": shift.shift_date.isoformat(),
                "shift_name": (
                    shift.shift_name.value
                    if hasattr(shift.shift_name, "value")
                    else shift.shift_name
                ),
                "opening_fuel": str(shift.opening_fuel),
                "status": shift.status,
            },
            details="Initial opening fuel established for the vessel.",
        )

        return shift

    
    @staticmethod
    def calculate_shift_balance(
        db: Session,
        shift_id: int,
        *,
        lock: bool = True,
    ) -> dict[str, Decimal]:
        shift_hint = db.get(Shift, shift_id)
        if shift_hint is None:
            raise ValueError("Shift not found.")

        if lock:
            FuelService.lock_vessels(db, [shift_hint.vessel_id])
            shift = FuelService.lock_shifts(db, [shift_id])[shift_id]
        else:
            # Read-only calculations must not acquire write locks.
            shift = shift_hint

        transactions = db.scalars(
            select(FuelTransaction).where(
                FuelTransaction.shift_id == shift_id
            )
        ).all()


        received_fuel = Decimal("0")
        transfer_in = Decimal("0")
        balance_transfer_in = Decimal("0")
        engine_consumption = Decimal("0")
        transfer_out = Decimal("0")
        balance_transfer_out = Decimal("0")
        issue_out = Decimal("0")
        adjustment_in = Decimal("0")
        adjustment_out = Decimal("0")

        for transaction in transactions:
            quantity = Decimal(str(transaction.quantity))

            if transaction.transaction_type == FuelTransactionType.RECEIPT.value:
                received_fuel += quantity

            elif transaction.transaction_type == FuelTransactionType.TRANSFER_IN.value:
                transfer_in += quantity
                if transaction.affects_balance:
                    balance_transfer_in += quantity

            elif transaction.transaction_type == FuelTransactionType.ENGINE_CONSUMPTION.value:
                engine_consumption += quantity

            elif transaction.transaction_type == FuelTransactionType.TRANSFER_OUT.value:
                transfer_out += quantity
                if transaction.affects_balance:
                    balance_transfer_out += quantity

            elif transaction.transaction_type == FuelTransactionType.ISSUE_OUT.value:
                issue_out += quantity

            elif transaction.transaction_type == FuelTransactionType.ADJUSTMENT.value:
                if transaction.adjustment_direction == AdjustmentDirection.IN.value:
                    adjustment_in += quantity

                elif transaction.adjustment_direction == AdjustmentDirection.OUT.value:
                    adjustment_out += quantity

                else:
                    raise ValueError(
                        "ADJUSTMENT transaction has no valid direction."
                    )

            else:
                raise ValueError(
                    f"Unknown fuel transaction type: "
                    f"{transaction.transaction_type}"
                )

        opening_fuel = Decimal(str(shift.opening_fuel))

        closing_fuel = (
            opening_fuel
            + received_fuel
            + balance_transfer_in
            - engine_consumption
            - balance_transfer_out
            - issue_out
            + adjustment_in
            - adjustment_out
        )

        return {
            "opening_fuel": opening_fuel,
            "received_fuel": received_fuel,
            "transfer_in": transfer_in,
            "engine_consumption": engine_consumption,
            "transfer_out": transfer_out,
            "issue_out": issue_out,
            "adjustment_in": adjustment_in,
            "adjustment_out": adjustment_out,
            "closing_fuel": closing_fuel,
        }

    @staticmethod
    def recalculate_shift(
        db: Session,
        shift_id: int,
    ) -> Shift:
        shift = db.get(Shift, shift_id)

        if shift is None:
            raise ValueError("Shift not found.")

        balance = FuelService.calculate_shift_balance(
            db,
            shift_id,
        )

        shift.calculated_closing_fuel = balance["closing_fuel"]

        db.flush()

        return shift

    @staticmethod
    def reconcile_downstream_shifts(
        db: Session,
        *,
        shift_id: int,
        reconciled_by_user_id: int,
        reason: str,
    ) -> list[dict[str, str | int | None]]:
        """Recalculate later shifts from the selected shift's current ledger balance."""
        shift_hint = db.get(Shift, shift_id)
        if shift_hint is None:
            raise ValueError("Shift not found.")
        shifts = FuelService.lock_vessel_shifts(db, shift_hint.vessel_id)
        source = next((item for item in shifts if item.id == shift_id), None)
        if source is None:
            raise ValueError("Shift not found.")

        source_balance = FuelService.calculate_shift_balance(db, source.id)
        if source_balance["closing_fuel"] < 0:
            raise ValueError("Correction would make the source shift closing balance negative.")
        source.calculated_closing_fuel = source_balance["closing_fuel"]
        later_shifts = sorted(
            (item for item in shifts if FuelService.is_later_shift(item, source)),
            key=FuelService.shift_order_key,
        )
        changes: list[dict[str, str | int | None]] = []
        previous = source
        for later in later_shifts:
            old_opening = Decimal(str(later.opening_fuel))
            old_closing = (
                Decimal(str(later.calculated_closing_fuel))
                if later.calculated_closing_fuel is not None else None
            )
            later.opening_fuel = Decimal(str(previous.calculated_closing_fuel))
            balance = FuelService.calculate_shift_balance(db, later.id)
            if balance["closing_fuel"] < 0:
                raise ValueError(
                    f"Downstream Shift #{later.id} would have negative closing fuel. Reconcile its transactions first."
                )
            later.calculated_closing_fuel = balance["closing_fuel"]
            change = {
                "shift_id": later.id,
                "old_opening_fuel": str(old_opening),
                "new_opening_fuel": str(later.opening_fuel),
                "old_closing_fuel": str(old_closing) if old_closing is not None else None,
                "new_closing_fuel": str(later.calculated_closing_fuel),
            }
            changes.append(change)
            AuditService.log(
                db=db,
                user_id=reconciled_by_user_id,
                action="RECONCILE_DOWNSTREAM_SHIFT_FUEL",
                entity="shifts",
                entity_id=later.id,
                old_values={
                    "opening_fuel": change["old_opening_fuel"],
                    "calculated_closing_fuel": change["old_closing_fuel"],
                },
                new_values={
                    "opening_fuel": change["new_opening_fuel"],
                    "calculated_closing_fuel": change["new_closing_fuel"],
                    "source_shift_id": source.id,
                },
                reason=reason.strip(),
                details="Opening and closing fuel recalculated after a shift fuel correction.",
            )
            previous = later
        db.flush()
        return changes

    @staticmethod
    def add_transaction(
        db: Session,
        vessel_id: int,
        shift_date: date,
        shift_name: str,
        transaction_type: FuelTransactionType,
        quantity: Decimal,
        created_by_user_id: int,
        adjustment_direction: AdjustmentDirection | None = None,
        reference_type: str | None = None,
        reference_id: int | None = None,
        remarks: str | None = None,
        source_vessel_id: int | None = None,
        fuel_source: str | None = None,
        allow_downstream_reconciliation: bool = False,
    ) -> FuelTransaction:
        """
        Add a fuel ledger transaction to a vessel shift.

        Normal transaction quantities are always positive.
        The transaction type determines whether the quantity
        increases or decreases the fuel balance.
        """

        if quantity <= 0:
            raise ValueError(
                "Transaction quantity must be greater than zero."
            )

        if transaction_type == FuelTransactionType.ADJUSTMENT:
            if adjustment_direction is None:
                raise ValueError(
                    "Adjustment direction is required for ADJUSTMENT transactions."
                )
        else:
            if adjustment_direction is not None:
                raise ValueError(
                    "Adjustment direction is only allowed for ADJUSTMENT transactions."
                )

        # Fuel source information is only valid for fuel receipts.
        if transaction_type == FuelTransactionType.RECEIPT:
            if fuel_source is not None:
                fuel_source = fuel_source.strip() or None

            if source_vessel_id is not None:
                if source_vessel_id == vessel_id:
                    raise ValueError(
                        "Source vessel cannot be the same as the receiving vessel."
                    )

                from backend.models.vessel import Vessel

                source_vessel = db.get(Vessel, source_vessel_id)

                if source_vessel is None:
                    raise ValueError("Source vessel not found.")

                if not source_vessel.is_active:
                    raise ValueError("Source vessel is not active.")

        else:
            if source_vessel_id is not None or fuel_source is not None:
                raise ValueError(
                    "Fuel source information is only allowed for RECEIPT transactions."
                )

        shift = FuelService.get_or_create_shift(
            db=db,
            vessel_id=vessel_id,
            shift_date=shift_date,
            shift_name=shift_name,
            created_by_user_id=created_by_user_id,
        )

        if shift.status != "OPEN":
            raise ValueError(
                "Fuel transactions cannot be added to a closed shift."
            )
        if FuelService.has_later_shift(db, shift) and not allow_downstream_reconciliation:
            raise ValueError(
                "Fuel transactions cannot be added to a shift while later "
                "shifts exist; downstream reconciliation is required first."
            )

        transaction = FuelTransaction(
            shift_id=shift.id,
            vessel_id=vessel_id,
            transaction_type=transaction_type.value,
            quantity=quantity,
            adjustment_direction=(
                adjustment_direction.value
                if adjustment_direction is not None
                else None
            ),
            reference_type=reference_type,
            reference_id=reference_id,
            remarks=remarks,
            source_vessel_id=source_vessel_id,
            fuel_source=fuel_source,
            created_by_user_id=created_by_user_id,
        )

        db.add(transaction)
        db.flush()

        FuelService.recalculate_shift(
            db,
            shift.id,
        )

        AuditService.log(
            db=db,
            user_id=created_by_user_id,
            action="CREATE_FUEL_TRANSACTION",
            entity="fuel_transactions",
            entity_id=transaction.id,
            old_values=None,
            new_values={
                "shift_id": transaction.shift_id,
                "vessel_id": transaction.vessel_id,
                "transaction_type": transaction.transaction_type,
                "quantity": str(transaction.quantity),
                "adjustment_direction": transaction.adjustment_direction,
                "reference_type": transaction.reference_type,
                "reference_id": transaction.reference_id,
                "source_vessel_id": transaction.source_vessel_id,
                "fuel_source": transaction.fuel_source,
                "transaction_date": transaction.transaction_date.isoformat(),
                "remarks": transaction.remarks,
            },
            details="Fuel ledger transaction created.",
        )

        return transaction

    @staticmethod
    def record_receipt(
        db: Session,
        vessel_id: int,
        shift_date: date,
        shift_name: str,
        quantity: Decimal,
        created_by_user_id: int,
        remarks: str | None = None,
        source_vessel_id: int | None = None,
        fuel_source: str | None = None,
    ) -> FuelTransaction:
        return FuelService.add_transaction(
            db=db,
            vessel_id=vessel_id,
            shift_date=shift_date,
            shift_name=shift_name,
            transaction_type=FuelTransactionType.RECEIPT,
            quantity=quantity,
            created_by_user_id=created_by_user_id,
            remarks=remarks,
            source_vessel_id=source_vessel_id,
            fuel_source=fuel_source,
        )

    @staticmethod
    def correct_admin_receipt(
        db: Session,
        *,
        transaction_id: int,
        quantity: Decimal,
        source_vessel_id: int | None,
        fuel_source: str | None,
        remarks: str | None,
        corrected_by_user_id: int,
        reason: str,
        reconcile_downstream: bool = False,
    ) -> FuelTransaction:
        transaction_hint = db.get(FuelTransaction, transaction_id)
        if transaction_hint is None:
            raise ValueError("Fuel receipt not found.")
        FuelService.lock_vessels(db, [transaction_hint.vessel_id])
        shift = db.get(Shift, transaction_hint.shift_id)
        if shift is None:
            raise ValueError("Receipt shift not found.")
        shift = FuelService.lock_shifts(db, [shift.id])[shift.id]
        transaction = db.scalar(
            select(FuelTransaction)
            .where(FuelTransaction.id == transaction_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if transaction is None:
            raise ValueError("Fuel receipt not found.")
        if transaction.transaction_type != FuelTransactionType.RECEIPT.value:
            raise ValueError("Only RECEIPT transactions can use this correction.")
        if transaction.reference_type is not None or transaction.reference_id is not None:
            raise ValueError("Linked receipt transactions cannot be corrected directly.")
        if quantity <= 0:
            raise ValueError("Receipt quantity must be greater than zero.")

        reason = reason.strip() if reason else ""
        if not reason:
            raise ValueError("Correction reason is required.")

        if transaction.shift_id != shift.id or transaction.vessel_id != shift.vessel_id:
            raise ValueError("Receipt changed its shift or vessel while being corrected.")
        if shift.status != "OPEN":
            raise ValueError("Receipts can only be corrected on an OPEN shift.")
        if shift.vessel_id != transaction.vessel_id:
            raise ValueError("Receipt vessel does not match its shift.")

        normalized_fuel_source = fuel_source.strip() if fuel_source else None
        normalized_fuel_source = normalized_fuel_source or None
        normalized_remarks = remarks.strip() if remarks else None
        normalized_remarks = normalized_remarks or None

        if source_vessel_id is not None:
            if source_vessel_id == shift.vessel_id:
                raise ValueError(
                    "Source vessel cannot be the same as the receiving vessel."
                )
            source_vessel = db.get(Vessel, source_vessel_id)
            if source_vessel is None:
                raise ValueError("Source vessel not found.")
            if not source_vessel.is_active:
                raise ValueError("Source vessel is inactive.")

        old_values = {
            "shift_id": transaction.shift_id,
            "vessel_id": transaction.vessel_id,
            "transaction_type": transaction.transaction_type,
            "quantity": str(transaction.quantity),
            "source_vessel_id": transaction.source_vessel_id,
            "fuel_source": transaction.fuel_source,
            "transaction_date": transaction.transaction_date.isoformat(),
            "remarks": transaction.remarks,
        }
        new_quantity = Decimal(str(quantity))
        if (
            Decimal(str(transaction.quantity)) == new_quantity
            and transaction.source_vessel_id == source_vessel_id
            and transaction.fuel_source == normalized_fuel_source
            and transaction.remarks == normalized_remarks
        ):
            raise ValueError("Receipt correction does not change any values.")

        has_later_shift = FuelService.has_later_shift(db, shift)
        changed_quantity = Decimal(str(transaction.quantity)) != new_quantity
        if has_later_shift and changed_quantity and not reconcile_downstream:
            raise ValueError(
                "Receipt quantity cannot be changed while later shifts exist; "
                "downstream reconciliation is required first."
            )

        current_balance = FuelService.calculate_shift_balance(db, shift.id)
        projected_closing = (
            current_balance["closing_fuel"]
            - Decimal(str(transaction.quantity))
            + new_quantity
        )
        if projected_closing < 0:
            raise ValueError("Correction would make the shift closing balance negative.")

        transaction.quantity = new_quantity
        transaction.source_vessel_id = source_vessel_id
        transaction.fuel_source = normalized_fuel_source
        transaction.remarks = normalized_remarks
        FuelService.recalculate_shift(db, shift.id)
        if has_later_shift and changed_quantity:
            FuelService.reconcile_downstream_shifts(
                db, shift_id=shift.id, reconciled_by_user_id=corrected_by_user_id,
                reason=reason,
            )

        AuditService.log(
            db=db,
            user_id=corrected_by_user_id,
            action="CORRECT_FUEL_RECEIPT",
            entity="fuel_transactions",
            entity_id=transaction.id,
            old_values=old_values,
            new_values={
                "shift_id": transaction.shift_id,
                "vessel_id": transaction.vessel_id,
                "transaction_type": transaction.transaction_type,
                "quantity": str(transaction.quantity),
                "source_vessel_id": transaction.source_vessel_id,
                "fuel_source": transaction.fuel_source,
                "transaction_date": transaction.transaction_date.isoformat(),
                "remarks": transaction.remarks,
            },
            reason=reason,
            details="Standalone fuel receipt corrected; transaction date and shift identity were preserved.",
        )
        return transaction

    @staticmethod
    def record_transfer_in(
        db: Session,
        vessel_id: int,
        shift_date: date,
        shift_name: str,
        quantity: Decimal,
        transfer_id: int,
        created_by_user_id: int,
        remarks: str | None = None,
    ) -> FuelTransaction:
        return FuelService.add_transaction(
            db=db,
            vessel_id=vessel_id,
            shift_date=shift_date,
            shift_name=shift_name,
            transaction_type=FuelTransactionType.TRANSFER_IN,
            quantity=quantity,
            created_by_user_id=created_by_user_id,
            reference_type="TRANSFER",
            reference_id=transfer_id,
            remarks=remarks,
        )

    @staticmethod
    def record_transfer_out(
        db: Session,
        vessel_id: int,
        shift_date: date,
        shift_name: str,
        quantity: Decimal,
        transfer_id: int,
        created_by_user_id: int,
        remarks: str | None = None,
    ) -> FuelTransaction:
        return FuelService.add_transaction(
            db=db,
            vessel_id=vessel_id,
            shift_date=shift_date,
            shift_name=shift_name,
            transaction_type=FuelTransactionType.TRANSFER_OUT,
            quantity=quantity,
            created_by_user_id=created_by_user_id,
            reference_type="TRANSFER",
            reference_id=transfer_id,
            remarks=remarks,
        )

    @staticmethod
    def record_engine_consumption(
        db: Session,
        vessel_id: int,
        shift_date: date,
        shift_name: str,
        quantity: Decimal,
        engine_event_id: int,
        created_by_user_id: int,
        remarks: str | None = None,
        allow_downstream_reconciliation: bool = False,
    ) -> FuelTransaction:
        return FuelService.add_transaction(
            db=db,
            vessel_id=vessel_id,
            shift_date=shift_date,
            shift_name=shift_name,
            transaction_type=FuelTransactionType.ENGINE_CONSUMPTION,
            quantity=quantity,
            created_by_user_id=created_by_user_id,
            reference_type="ENGINE_EVENT",
            reference_id=engine_event_id,
            remarks=remarks,
            allow_downstream_reconciliation=allow_downstream_reconciliation,
        )

    @staticmethod
    def record_adjustment(
        db: Session,
        vessel_id: int,
        shift_date: date,
        shift_name: str,
        quantity: Decimal,
        direction: AdjustmentDirection,
        created_by_user_id: int,
        remarks: str | None = None,
    ) -> FuelTransaction:
        return FuelService.add_transaction(
            db=db,
            vessel_id=vessel_id,
            shift_date=shift_date,
            shift_name=shift_name,
            transaction_type=FuelTransactionType.ADJUSTMENT,
            quantity=quantity,
            created_by_user_id=created_by_user_id,
            adjustment_direction=direction,
            remarks=remarks,
        )

    @staticmethod
    def update_shift_production_data(
        db: Session,
        shift_id: int,
        advancement_m: Decimal | None,
        dredging_hours: Decimal | None,
        updated_by_user_id: int | None = None,
        correction_reason: str | None = None,
    ) -> Shift:
        shift_hint = db.get(Shift, shift_id)
        if shift_hint is None:
            raise ValueError("Shift not found.")

        FuelService.lock_vessels(db, [shift_hint.vessel_id])
        shift = FuelService.lock_shifts(db, [shift_id])[shift_id]

        if shift.status != "OPEN":
            raise ValueError(
                "Production data can only be updated for an OPEN shift."
            )

        if advancement_m is not None and advancement_m < 0:
            raise ValueError("Advancement cannot be negative.")

        if dredging_hours is not None and dredging_hours < 0:
            raise ValueError("Dredging hours cannot be negative.")

        if correction_reason is not None and not correction_reason.strip():
            raise ValueError("Correction reason is required.")

        old_values = {
            "advancement_m": (
                str(shift.advancement_m)
                if shift.advancement_m is not None
                else None
            ),
            "dredging_hours": (
                str(shift.dredging_hours)
                if shift.dredging_hours is not None
                else None
            ),
        }

        shift.advancement_m = advancement_m
        shift.dredging_hours = dredging_hours

        db.flush()

        AuditService.log(
            db=db,
            user_id=updated_by_user_id,
            action="UPDATE_SHIFT_PRODUCTION_DATA",
            entity="shifts",
            entity_id=shift.id,
            old_values=old_values,
            new_values={
                "advancement_m": (
                    str(shift.advancement_m)
                    if shift.advancement_m is not None
                    else None
                ),
                "dredging_hours": (
                    str(shift.dredging_hours)
                    if shift.dredging_hours is not None
                    else None
                ),
            },
            reason=(correction_reason.strip() if correction_reason else None),
            details="Shift operator production data updated.",
        )

        return shift

    @staticmethod
    def close_shift(
        db: Session,
        shift_id: int,
        closed_by_user_id: int | None = None,
        reason: str | None = None,
        *,
        system_close: bool = False,
    ) -> Shift:
        """
        Close a shift.

        ``system_close`` is used only by the IoT auto-close.  It waives the
        two requirements that need a person to enter data the IoT feed cannot
        supply (a sounding, and advancement / dredging hours for Dredgers).
        Everything else - non-negative closing fuel, transfer notes - is still
        enforced, and the waived items are written to the audit log.
        """
        shift_hint = db.get(Shift, shift_id)
        if shift_hint is None:
            raise ValueError("Shift not found.")

        FuelService.lock_vessels(db, [shift_hint.vessel_id])
        shift = FuelService.lock_shifts(db, [shift_id])[shift_id]

        if shift.status == "CLOSED":
            return shift

        waived: list[str] = []

        if shift.status != "OPEN":
            raise ValueError(
                f"Shift cannot be closed from status '{shift.status}'."
            )

        if reason is not None and not reason.strip():
            raise ValueError("Close reason is required.")

        vessel = db.get(Vessel, shift.vessel_id)
        if vessel is not None and vessel.vessel_type == "Dredger":
            if shift.advancement_m is None:
                if not system_close:
                    raise ValueError(
                        "Shift cannot be closed: advancement is required for Dredgers."
                    )
                waived.append("advancement")
            if shift.dredging_hours is None:
                if not system_close:
                    raise ValueError(
                        "Shift cannot be closed: dredging hours are required for Dredgers."
                    )
                waived.append("dredging_hours")

        # ---------------------------------------------------------
        # Phase 4: every shift requires at least one sounding.
        # ---------------------------------------------------------

        sounding_count = db.scalar(
            select(func.count(Sounding.id))
            .where(Sounding.shift_id == shift.id)
        ) or 0

        if sounding_count < 1:
            if not system_close:
                raise ValueError(
                    "Shift cannot be closed without at least one sounding."
                )
            waived.append("sounding")

        # Calculate the final balance from the ledger.
        FuelService.recalculate_shift(
            db,
            shift_id,
        )

        if shift.calculated_closing_fuel is None:
            raise ValueError(
                "Unable to calculate shift closing fuel."
            )

        if shift.calculated_closing_fuel < 0:
            raise ValueError(
                "Shift cannot be closed with negative closing fuel."
            )

        # ---------------------------------------------------------
        # Completed transfers require at least one transfer note.
        #
        # Transfer notes are NOT required for:
        #   INITIATED
        #   RECEIVING_CONFIRMED
        #   MANAGER_REVIEW
        #   APPROVED
        #
        # They are required only when a completed transfer
        # (BALANCES_UPDATED) is associated with this shift.
        # ---------------------------------------------------------

        completed_transfers = db.scalars(
            select(FuelTransfer).where(
                FuelTransfer.status == TransferStatus.BALANCES_UPDATED,
                or_(
                    FuelTransfer.from_shift_id == shift_id,
                    FuelTransfer.to_shift_id == shift_id,
                ),
            )
        ).all()

        for transfer in completed_transfers:
            transfer_note_count = db.scalar(
                select(func.count(TransferAttachment.id)).where(
                    TransferAttachment.transfer_id == transfer.id
                )
            ) or 0

            if transfer_note_count < 1:
                raise ValueError(
                    f"Shift cannot be closed because completed "
                    f"Transfer #{transfer.id} has no transfer note."
                )

        # ---------------------------------------------------------
        # Close the shift
        # ---------------------------------------------------------

        shift.status = "CLOSED"
        shift.closed_at = now_ist()
        shift.close_source = "AUTO_IOT" if system_close else "MANUAL"

        db.flush()

        AuditService.log(
            db=db,
            user_id=closed_by_user_id,
            action="CLOSE_SHIFT",
            entity="shifts",
            entity_id=shift.id,
            old_values={
                "status": "OPEN",
                "calculated_closing_fuel": (
                    str(shift.calculated_closing_fuel)
                    if shift.calculated_closing_fuel is not None
                    else None
                ),
            },
            new_values={
                "status": shift.status,
                "close_source": shift.close_source,
                "waived_requirements": waived,
                "calculated_closing_fuel": (
                    str(shift.calculated_closing_fuel)
                    if shift.calculated_closing_fuel is not None
                    else None
                ),
            },
            reason=reason.strip() if reason else None,
            details=(
                "Shift closed automatically by the IoT integration; "
                f"requirements waived: {', '.join(waived) or 'none'}."
                if system_close
                else "Shift closed and final fuel balance calculated."
            ),
        )

        return shift

    @staticmethod
    def reopen_shift(
        db: Session,
        shift_id: int,
        reopened_by_user_id: int,
        reason: str,
    ) -> Shift:
        shift_hint = db.get(Shift, shift_id)
        if shift_hint is None:
            raise ValueError("Shift not found.")

        FuelService.lock_vessels(db, [shift_hint.vessel_id])
        shift = FuelService.lock_shifts(db, [shift_id])[shift_id]

        if shift.status != "CLOSED":
            raise ValueError(
                f"Shift cannot be reopened from status '{shift.status}'."
            )

        reason = reason.strip() if reason else ""
        if not reason:
            raise ValueError("Correction reason is required.")

        old_values = {
            "status": shift.status,
            "closed_at": (
                shift.closed_at.isoformat()
                if shift.closed_at is not None
                else None
            ),
        }

        shift.status = "OPEN"
        shift.closed_at = None
        # Once a person has reopened the shift, the IoT auto-close must not
        # take it back; it is closed manually again.
        shift.auto_close_at = None
        shift.close_source = None

        db.flush()

        AuditService.log(
            db=db,
            user_id=reopened_by_user_id,
            action="REOPEN_SHIFT",
            entity="shifts",
            entity_id=shift.id,
            old_values=old_values,
            new_values={
                "status": shift.status,
                "closed_at": None,
            },
            reason=reason,
            details="Shift reopened by an administrator; ledger data was not changed.",
        )

        return shift

    @staticmethod
    def get_shift(
        db: Session,
        vessel_id: int,
        shift_date: date,
        shift_name: str,
    ) -> Shift | None:
        shift_name = shift_name.upper()

        return db.scalar(
            select(Shift).where(
                Shift.vessel_id == vessel_id,
                Shift.shift_date == shift_date,
                Shift.shift_name == shift_name,
            )
        )

    @staticmethod
    def correct_opening_fuel(
        db: Session,
        shift_id: int,
        new_opening_fuel: Decimal,
        corrected_by_user_id: int,
        reason: str,
    ) -> Shift:
        shift_hint = db.get(Shift, shift_id)
        if shift_hint is None:
            raise ValueError("Shift not found.")

        vessel_shifts = FuelService.lock_vessel_shifts(db, shift_hint.vessel_id)
        shift = next(
            (candidate for candidate in vessel_shifts if candidate.id == shift_id),
            None,
        )
        if shift is None:
            raise ValueError("Shift not found.")

        if new_opening_fuel < 0:
            raise ValueError("Opening fuel cannot be negative.")

        old_opening_fuel = Decimal(str(shift.opening_fuel))
        new_opening_fuel = Decimal(str(new_opening_fuel))

        if not reason or not reason.strip():
            raise ValueError("Correction reason is required.")

        subsequent_shifts = [
            candidate
            for candidate in vessel_shifts
            if FuelService.is_later_shift(candidate, shift)
        ]
        if subsequent_shifts:
            raise ValueError(
                "Opening fuel cannot be corrected while later shifts exist; "
                "downstream reconciliation is required first."
            )

        if old_opening_fuel == new_opening_fuel:
            return shift

        shift.opening_fuel = new_opening_fuel
        balance = FuelService.calculate_shift_balance(db, shift_id)
        if balance["closing_fuel"] < 0:
            raise ValueError("Correction would make the shift closing balance negative.")
        shift.calculated_closing_fuel = balance["closing_fuel"]
        db.flush()

        AuditService.log(
            db=db,
            user_id=corrected_by_user_id,
            action="CORRECT_OPENING_FUEL",
            entity="shifts",
            entity_id=shift.id,
            old_values={
                "opening_fuel": str(old_opening_fuel),
            },
            new_values={
                "opening_fuel": str(new_opening_fuel),
            },
            reason=reason.strip(),
            details=(
                f"Opening fuel corrected from {old_opening_fuel} to "
                f"{new_opening_fuel}. No later shifts existed or were changed."
            ),
        )

        return shift

    @staticmethod
    def correct_admin_opening_fuel(
        db: Session,
        *,
        shift_id: int,
        new_opening_fuel: Decimal,
        corrected_by_user_id: int,
        reason: str,
    ) -> Shift:
        shift_hint = db.get(Shift, shift_id)
        if shift_hint is None:
            raise ValueError("Shift not found.")
        vessel_shifts = FuelService.lock_vessel_shifts(db, shift_hint.vessel_id)
        shift = next(
            (candidate for candidate in vessel_shifts if candidate.id == shift_id),
            None,
        )
        if shift is None:
            raise ValueError("Shift not found.")
        if shift.status != "OPEN":
            raise ValueError("Opening fuel can only be corrected on an OPEN shift.")
        if new_opening_fuel < 0:
            raise ValueError("Opening fuel cannot be negative.")
        reason = reason.strip() if reason else ""
        if not reason:
            raise ValueError("Correction reason is required.")

        subsequent_shifts = sorted(
            (
                candidate
                for candidate in vessel_shifts
                if FuelService.is_later_shift(candidate, shift)
            ),
            key=FuelService.shift_order_key,
        )

        previous_shift = max(
            (
                candidate
                for candidate in vessel_shifts
                if FuelService.is_later_shift(shift, candidate)
            ),
            key=FuelService.shift_order_key,
            default=None,
        )
        proposed = Decimal(str(new_opening_fuel))
        if previous_shift is not None:
            if previous_shift.calculated_closing_fuel is None:
                raise ValueError(
                    "Previous shift has no calculated closing fuel."
                )
            if proposed != Decimal(str(previous_shift.calculated_closing_fuel)):
                raise ValueError(
                    "Opening fuel must match the previous shift's calculated closing fuel."
                )

        old_value = Decimal(str(shift.opening_fuel))
        old_closing_value = (
            Decimal(str(shift.calculated_closing_fuel))
            if shift.calculated_closing_fuel is not None
            else None
        )
        if old_value == proposed:
            raise ValueError("Corrected opening fuel is unchanged.")

        affected_shifts = [shift, *subsequent_shifts]
        old_balances = {
            candidate.id: (
                candidate.opening_fuel,
                candidate.calculated_closing_fuel,
            )
            for candidate in affected_shifts
        }
        downstream_changes: list[dict[str, str | int | None]] = []
        try:
            shift.opening_fuel = proposed
            balance = FuelService.calculate_shift_balance(db, shift.id)
            if balance["closing_fuel"] < 0:
                raise ValueError(
                    "Correction would make the shift closing balance negative."
                )
            shift.calculated_closing_fuel = balance["closing_fuel"]

            previous = shift
            for later in subsequent_shifts:
                old_opening, old_closing = old_balances[later.id]
                later.opening_fuel = previous.calculated_closing_fuel
                later_balance = FuelService.calculate_shift_balance(db, later.id)
                if later_balance["closing_fuel"] < 0:
                    raise ValueError(
                        "Correction would make downstream Shift "
                        f"#{later.id} closing fuel negative. No shifts were changed."
                    )
                later.calculated_closing_fuel = later_balance["closing_fuel"]
                downstream_changes.append(
                    {
                        "shift_id": later.id,
                        "old_opening_fuel": str(old_opening),
                        "new_opening_fuel": str(later.opening_fuel),
                        "old_closing_fuel": (
                            str(old_closing) if old_closing is not None else None
                        ),
                        "new_closing_fuel": str(later.calculated_closing_fuel),
                    }
                )
                previous = later
        except Exception:
            for candidate in affected_shifts:
                old_opening, old_closing = old_balances[candidate.id]
                candidate.opening_fuel = old_opening
                candidate.calculated_closing_fuel = old_closing
            raise

        db.flush()

        AuditService.log(
            db=db,
            user_id=corrected_by_user_id,
            action="CORRECT_SHIFT_OPENING_FUEL",
            entity="shifts",
            entity_id=shift.id,
            old_values={
                "opening_fuel": str(old_value),
                "calculated_closing_fuel": (
                    str(old_closing_value)
                    if old_closing_value is not None
                    else None
                ),
            },
            new_values={
                "opening_fuel": str(proposed),
                "calculated_closing_fuel": str(balance["closing_fuel"]),
                "downstream_reconciled": downstream_changes,
            },
            reason=reason,
            details=(
                f"Opening fuel corrected; {len(downstream_changes)} later shift(s) "
                "had opening and calculated closing fuel reconciled."
            ),
        )
        for change in downstream_changes:
            AuditService.log(
                db=db,
                user_id=corrected_by_user_id,
                action="RECONCILE_DOWNSTREAM_SHIFT_FUEL",
                entity="shifts",
                entity_id=change["shift_id"],
                old_values={
                    "opening_fuel": change["old_opening_fuel"],
                    "calculated_closing_fuel": change["old_closing_fuel"],
                },
                new_values={
                    "opening_fuel": change["new_opening_fuel"],
                    "calculated_closing_fuel": change["new_closing_fuel"],
                    "source_shift_id": shift.id,
                },
                reason=reason,
                details=(
                    "Opening fuel and calculated closing fuel recalculated after "
                    "an upstream opening-fuel correction."
                ),
            )
        return shift

    @staticmethod
    def get_shift_transactions(
        db: Session,
        shift_id: int,
    ) -> list[FuelTransaction]:
        shift = db.get(Shift, shift_id)

        if shift is None:
            raise ValueError("Shift not found.")

        return db.scalars(
            select(FuelTransaction)
            .where(FuelTransaction.shift_id == shift_id)
            .order_by(
                FuelTransaction.transaction_date,
                FuelTransaction.id,
            )
        ).all()

    @staticmethod
    def correct_adjustment(
        db: Session,
        adjustment_id: int,
        new_quantity: Decimal,
        new_direction: AdjustmentDirection,
        corrected_by_user_id: int,
        correction_remarks: str,
        reconcile_downstream: bool = False,
    ) -> FuelTransaction:
        """
        Correct an adjustment without modifying historical ledger entries.

        Each correction:
            1. Reverses the currently effective adjustment.
            2. Creates a new corrected adjustment.
            3. Records an audit entry.

        This allows an adjustment to be corrected multiple times while
        preserving the complete correction history.
        """

        if new_quantity <= 0:
            raise ValueError(
                "Corrected adjustment quantity must be greater than zero."
            )

        if not correction_remarks or not correction_remarks.strip():
            raise ValueError(
                "Correction remarks are required."
            )

        current_hint = db.get(FuelTransaction, adjustment_id)
        if current_hint is None:
            raise ValueError("Adjustment transaction not found.")

        shift_hint = db.get(Shift, current_hint.shift_id)
        if shift_hint is None:
            raise ValueError(
                "Shift associated with adjustment was not found."
            )
        FuelService.lock_vessels(db, [shift_hint.vessel_id])
        shift = FuelService.lock_shifts(db, [shift_hint.id])[shift_hint.id]
        current = db.scalar(
            select(FuelTransaction)
            .where(FuelTransaction.id == adjustment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if current is None:
            raise ValueError("Adjustment transaction not found.")
        if current.shift_id != shift.id or current.vessel_id != shift.vessel_id:
            raise ValueError("Adjustment changed its shift or vessel while being corrected.")

        if current.transaction_type != FuelTransactionType.ADJUSTMENT.value:
            raise ValueError(
                "The selected transaction is not an adjustment."
            )

        # Corrections must always start from the original adjustment.
        if current.reference_type in {
            "ADJUSTMENT_CORRECTION",
            "ADJUSTMENT_CORRECTION_REVERSAL",
        }:
            raise ValueError(
                "Select the original adjustment to correct its effective value."
            )

        if current.adjustment_direction not in (
            AdjustmentDirection.IN.value,
            AdjustmentDirection.OUT.value,
        ):
            raise ValueError(
                "Adjustment has an invalid direction."
            )

        if shift.status != "OPEN":
            raise ValueError(
                "Adjustments can only be corrected on an OPEN shift."
            )

        effective = db.scalars(
            select(FuelTransaction)
            .where(
                FuelTransaction.reference_type == "ADJUSTMENT_CORRECTION",
                FuelTransaction.reference_id == current.id,
            )
            .order_by(FuelTransaction.id.desc())
        ).first()
        effective = effective or current

        old_quantity = Decimal(str(effective.quantity))
        new_quantity = Decimal(str(new_quantity))

        # Do not create a correction if nothing actually changed.
        if (
            old_quantity == new_quantity
            and effective.adjustment_direction == new_direction.value
        ):
            raise ValueError(
                "Corrected adjustment is identical to the current adjustment."
            )

        has_later_shift = FuelService.has_later_shift(db, shift)
        if has_later_shift and not reconcile_downstream:
            raise ValueError(
                "This correction would change fuel available to subsequent shifts; "
                "downstream reconciliation is required first."
            )

        # Reverse the currently effective adjustment.
        reversal_direction = (
            AdjustmentDirection.OUT
            if effective.adjustment_direction == AdjustmentDirection.IN.value
            else AdjustmentDirection.IN
        )

        reversal = FuelTransaction(
            shift_id=effective.shift_id,
            vessel_id=effective.vessel_id,
            transaction_type=FuelTransactionType.ADJUSTMENT.value,
            quantity=old_quantity,
            adjustment_direction=reversal_direction.value,
            reference_type="ADJUSTMENT_CORRECTION_REVERSAL",
            reference_id=effective.id,
            remarks=f"Reversal of adjustment #{effective.id}",
            created_by_user_id=corrected_by_user_id,
        )

        db.add(reversal)
        db.flush()

        # Create the new effective adjustment.
        corrected = FuelTransaction(
            shift_id=current.shift_id,
            vessel_id=current.vessel_id,
            transaction_type=FuelTransactionType.ADJUSTMENT.value,
            quantity=new_quantity,
            adjustment_direction=new_direction.value,
            reference_type="ADJUSTMENT_CORRECTION",
            reference_id=current.id,
            remarks=correction_remarks.strip(),
            created_by_user_id=corrected_by_user_id,
        )

        db.add(corrected)
        db.flush()

        # Recalculate the affected shift.
        FuelService.recalculate_shift(
            db,
            current.shift_id,
        )
        if has_later_shift:
            FuelService.reconcile_downstream_shifts(
                db, shift_id=current.shift_id,
                reconciled_by_user_id=corrected_by_user_id,
                reason=correction_remarks,
            )

        # Record the correction in the audit log.
        AuditService.log(
            db=db,
            user_id=corrected_by_user_id,
            action="CORRECT_ADJUSTMENT",
            entity="fuel_transactions",
            entity_id=corrected.id,
            old_values={
                "transaction_id": current.id,
                "effective_transaction_id": effective.id,
                "quantity": str(old_quantity),
                "adjustment_direction": effective.adjustment_direction,
            },
            new_values={
                "transaction_id": current.id,
                "effective_transaction_id": corrected.id,
                "quantity": str(new_quantity),
                "adjustment_direction": new_direction.value,
            },
            reason=correction_remarks.strip(),
            details=(
                f"Adjustment #{current.id} corrected by creating "
                f"reversal #{reversal.id} and corrected transaction "
                f"#{corrected.id}."
            ),
        )

        return corrected
