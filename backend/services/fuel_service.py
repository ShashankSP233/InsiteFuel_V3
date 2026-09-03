from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.fuel import FuelTransaction, FuelTransactionType
from backend.models.shift import Shift


class FuelService:

    @staticmethod
    def get_or_create_shift(
        db: Session,
        vessel_id: int,
        shift_date: date,
        shift_name: str,
    ) -> Shift:
        """
        Get an existing shift or create it.

        Shift sequence:
            MORNING -> EVENING -> next day's MORNING

        Opening fuel is always inherited from the immediately
        preceding shift.

        The first-ever MORNING shift requires an authorized
        opening fuel to be established separately.
        """

        shift_name = shift_name.upper()

        if shift_name not in ("MORNING", "EVENING"):
            raise ValueError(
                "shift_name must be either MORNING or EVENING."
            )

        # ---------------------------------------------------------
        # 1. Return existing shift
        # ---------------------------------------------------------

        shift = db.scalar(
            select(Shift).where(
                Shift.vessel_id == vessel_id,
                Shift.shift_date == shift_date,
                Shift.shift_name == shift_name,
            )
        )

        if shift:
            return shift

        # ---------------------------------------------------------
        # 2. Determine the immediately preceding shift
        # ---------------------------------------------------------

        if shift_name == "EVENING":
            # Evening shift must follow the same day's Morning shift.
            previous_shift = db.scalar(
                select(Shift).where(
                    Shift.vessel_id == vessel_id,
                    Shift.shift_date == shift_date,
                    Shift.shift_name == "MORNING",
                )
            )

            if previous_shift is None:
                raise ValueError(
                    f"Cannot create Evening shift for {shift_date}: "
                    "Morning shift does not exist."
                )

        else:
            # Morning shift must follow the previous day's Evening shift.
            previous_shift = db.scalar(
                select(Shift).where(
                    Shift.vessel_id == vessel_id,
                    Shift.shift_date < shift_date,
                    Shift.shift_name == "EVENING",
                )
                .order_by(Shift.shift_date.desc())
            )

            if previous_shift is None:
                raise ValueError(
                    f"Cannot create Morning shift for {shift_date}: "
                    "no previous Evening shift exists. "
                    "The first-ever opening fuel must be established "
                    "by an authorized Manager/Admin."
                )

        # ---------------------------------------------------------
        # 3. Previous shift must have a calculated closing fuel
        # ---------------------------------------------------------

        if previous_shift.calculated_closing_fuel is None:
            raise ValueError(
                f"Previous shift {previous_shift.id} does not have "
                "a calculated closing fuel."
            )

        # ---------------------------------------------------------
        # 4. Create the new shift using previous closing
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

        return shift

    @staticmethod
    def establish_initial_opening_fuel(
        db: Session,
        vessel_id: int,
        shift_date: date,
        opening_fuel: Decimal,
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

        return shift

    @staticmethod
    def calculate_shift_balance(db: Session, shift_id: int) -> dict[str, Decimal]:
        shift = db.get(Shift, shift_id)

        if shift is None:
            raise ValueError("Shift not found.")

        transactions = db.scalars(
            select(FuelTransaction).where(
                FuelTransaction.shift_id == shift_id
            )
        ).all()

        received_fuel = Decimal("0")
        transfer_in = Decimal("0")
        engine_consumption = Decimal("0")
        transfer_out = Decimal("0")
        adjustment_in = Decimal("0")
        adjustment_out = Decimal("0")

        for transaction in transactions:
            quantity = Decimal(str(transaction.quantity))

            if transaction.transaction_type == FuelTransactionType.RECEIPT.value:
                received_fuel += quantity

            elif transaction.transaction_type == FuelTransactionType.TRANSFER_IN.value:
                transfer_in += quantity

            elif transaction.transaction_type == FuelTransactionType.ENGINE_CONSUMPTION.value:
                engine_consumption += quantity

            elif transaction.transaction_type == FuelTransactionType.TRANSFER_OUT.value:
                transfer_out += quantity

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
            + transfer_in
            - engine_consumption
            - transfer_out
            + adjustment_in
            - adjustment_out
        )

        return {
            "opening_fuel": opening_fuel,
            "received_fuel": received_fuel,
            "transfer_in": transfer_in,
            "engine_consumption": engine_consumption,
            "transfer_out": transfer_out,
            "adjustment_in": adjustment_in,
            "adjustment_out": adjustment_out,
            "closing_fuel": closing_fuel,
        }

    @staticmethod
    def recalculate_shift(db: Session, shift_id: int) -> Shift:
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
    ) -> FuelTransaction:
        """
        Add a fuel ledger transaction to a vessel shift.

        Normal transaction quantities are always positive.
        The transaction type determines whether the quantity
        increases or decreases the fuel balance.
        """

        if quantity <= 0:
            raise ValueError("Transaction quantity must be greater than zero.")

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

        shift = FuelService.get_or_create_shift(
            db=db,
            vessel_id=vessel_id,
            shift_date=shift_date,
            shift_name=shift_name,
        )

        if shift.status != "OPEN":
            raise ValueError(
                "Fuel transactions cannot be added to a closed shift."
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
            created_by_user_id=created_by_user_id,
        )

        db.add(transaction)
        db.flush()

        FuelService.recalculate_shift(db, shift.id)

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
        )

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
    def close_shift(
        db: Session,
        shift_id: int,
    ) -> Shift:
        shift = db.get(Shift, shift_id)

        if shift is None:
            raise ValueError("Shift not found.")

        if shift.status == "CLOSED":
            return shift

        if shift.status != "OPEN":
            raise ValueError(
                f"Shift cannot be closed from status '{shift.status}'."
            )

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

        shift.status = "CLOSED"
        shift.closed_at = datetime.utcnow()

        db.flush()

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
    ) -> Shift:
        shift = db.get(Shift, shift_id)

        if shift is None:
            raise ValueError("Shift not found.")

        if new_opening_fuel < 0:
            raise ValueError(
                "Opening fuel cannot be negative."
            )

        old_opening_fuel = Decimal(str(shift.opening_fuel))

        if old_opening_fuel == new_opening_fuel:
            return shift

        shift.opening_fuel = new_opening_fuel

        FuelService.recalculate_shift(
            db,
            shift_id,
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
            .order_by(FuelTransaction.transaction_date, FuelTransaction.id)
        ).all()