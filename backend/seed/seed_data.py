from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models.user import User
from backend.models.project import Project
from backend.models.vessel import Vessel
from backend.models.equipment import Equipment
from backend.models.shift import Shift
from backend.models.transfer import TransferStatus

from backend.services.user_service import create_user
from backend.services.fuel_service import FuelService
from backend.services.engine_service import EngineService
from backend.services.transfer_service import TransferService


SEED_MARKER_USERNAME = "seed_manager"


def get_user(db, username: str):
    return db.scalar(
        select(User).where(User.username == username)
    )


def get_project(db, code: str):
    return db.scalar(
        select(Project).where(Project.code == code)
    )


def get_vessel(db, code: str):
    return db.scalar(
        select(Vessel).where(Vessel.code == code)
    )


def get_equipment(db, vessel_id: int, equipment_type: str):
    return db.scalar(
        select(Equipment).where(
            Equipment.vessel_id == vessel_id,
            Equipment.equipment_type == equipment_type,
        )
    )


def create_seed_users(db, admin):
    manager = get_user(db, "seed_manager")

    if manager is None:
        manager = create_user(
            db=db,
            username="seed_manager",
            password="Manager@2026!",
            role="MANAGER",
            full_name="Seed Manager",
            created_by_user_id=admin.id,
        )

    operator1 = get_user(db, "operator01")

    if operator1 is None:
        operator1 = create_user(
            db=db,
            username="operator01",
            password="Operator@2026!",
            role="OPERATOR",
            full_name="Demo Operator 01",
            created_by_user_id=admin.id,
        )

    operator2 = get_user(db, "operator02")

    if operator2 is None:
        operator2 = create_user(
            db=db,
            username="operator02",
            password="Operator@2026!",
            role="OPERATOR",
            full_name="Demo Operator 02",
            created_by_user_id=admin.id,
        )

    return manager, operator1, operator2


def get_master_data(db):
    project_alpha = get_project(db, "DEMO-A")
    project_beta = get_project(db, "DEMO-B")

    if not project_alpha or not project_beta:
        raise RuntimeError(
            "Demo projects are missing. Start the application once first "
            "so the initial bootstrap can create them."
        )

    vessels = [
        get_vessel(db, "DREDGER-01"),
        get_vessel(db, "DREDGER-02"),
        get_vessel(db, "BARGE-01"),
    ]

    if any(v is None for v in vessels):
        raise RuntimeError(
            "Demo vessels are missing. Start the application once first "
            "so the initial bootstrap can create them."
        )

    equipment = {}

    for vessel in vessels:
        equipment[vessel.code] = {
            "ME": get_equipment(db, vessel.id, "ME"),
            "AUX": get_equipment(db, vessel.id, "AUX"),
            "DG": get_equipment(db, vessel.id, "DG"),
        }

        if any(value is None for value in equipment[vessel.code].values()):
            raise RuntimeError(
                f"Equipment is incomplete for vessel {vessel.code}."
            )

    return vessels, equipment


def create_shift_data(
    db,
    vessels,
    equipment,
    operator1,
    start_date: date,
    days: int = 5,
):
    """
    Create five days of Morning/Evening operational data.

    The first Morning opening is established explicitly.
    All subsequent openings are inherited from the previous shift.
    """

    opening_values = {
        "DREDGER-01": Decimal("5000.000"),
        "DREDGER-02": Decimal("4200.000"),
        "BARGE-01": Decimal("3000.000"),
    }

    # ---------------------------------------------------------
    # First-ever Morning shift
    # ---------------------------------------------------------

    for vessel in vessels:
        existing = db.scalar(
            select(Shift).where(
                Shift.vessel_id == vessel.id,
                Shift.shift_name == "MORNING",
            )
            .order_by(Shift.shift_date.asc())
        )

        if existing is None:
            FuelService.establish_initial_opening_fuel(
                db=db,
                vessel_id=vessel.id,
                shift_date=start_date,
                opening_fuel=opening_values[vessel.code],
                created_by_user_id=operator1.id,
            )

    db.flush()

    # ---------------------------------------------------------
    # Create operational shifts
    # ---------------------------------------------------------

    for day_index in range(days):
        current_date = start_date + timedelta(days=day_index)

        for vessel in vessels:
            vessel_equipment = equipment[vessel.code]

            # Morning
            morning = FuelService.get_or_create_shift(
                db=db,
                vessel_id=vessel.id,
                shift_date=current_date,
                shift_name="MORNING",
                created_by_user_id=operator1.id,
            )

            # Add a fuel receipt on some shifts
            if day_index in (0, 2, 4):
                FuelService.record_receipt(
                    db=db,
                    vessel_id=vessel.id,
                    shift_date=current_date,
                    shift_name="MORNING",
                    quantity=Decimal("800.000"),
                    created_by_user_id=operator1.id,
                    fuel_source="Demo Fuel Bunker",
                    remarks="Seed fuel receipt",
                )

            # Main engine
            morning_start = datetime.combine(
                current_date,
                datetime.min.time(),
                tzinfo=timezone.utc,
            ).replace(hour=6)

            EngineService.create_engine_event(
                db=db,
                equipment_id=vessel_equipment["ME"].id,
                shift_id=morning.id,
                start_time=morning_start,
                stop_time=morning_start + timedelta(hours=5),
                lph_rate=Decimal("85.000"),
                created_by_user_id=operator1.id,
                remarks="Seed ME operating period",
            )

            # Auxiliary
            EngineService.create_engine_event(
                db=db,
                equipment_id=vessel_equipment["AUX"].id,
                shift_id=morning.id,
                start_time=morning_start + timedelta(minutes=30),
                stop_time=morning_start + timedelta(hours=4, minutes=30),
                lph_rate=Decimal("22.000"),
                created_by_user_id=operator1.id,
                remarks="Seed AUX operating period",
            )

            # Evening
            evening = FuelService.get_or_create_shift(
                db=db,
                vessel_id=vessel.id,
                shift_date=current_date,
                shift_name="EVENING",
                created_by_user_id=operator1.id,
            )

            evening_start = datetime.combine(
                current_date,
                datetime.min.time(),
                tzinfo=timezone.utc,
            ).replace(hour=18)

            # Main engine
            EngineService.create_engine_event(
                db=db,
                equipment_id=vessel_equipment["ME"].id,
                shift_id=evening.id,
                start_time=evening_start,
                stop_time=evening_start + timedelta(hours=4),
                lph_rate=Decimal("85.000"),
                created_by_user_id=operator1.id,
                remarks="Seed evening ME operating period",
            )

            # DG
            EngineService.create_engine_event(
                db=db,
                equipment_id=vessel_equipment["DG"].id,
                shift_id=evening.id,
                start_time=evening_start + timedelta(minutes=15),
                stop_time=evening_start + timedelta(hours=3),
                lph_rate=Decimal("18.000"),
                created_by_user_id=operator1.id,
                remarks="Seed DG operating period",
            )

            # Small adjustment on DREDGER-02
            if vessel.code == "DREDGER-02" and day_index == 2:
                from backend.models.fuel import AdjustmentDirection

                FuelService.record_adjustment(
                    db=db,
                    vessel_id=vessel.id,
                    shift_date=current_date,
                    shift_name="EVENING",
                    quantity=Decimal("25.000"),
                    direction=AdjustmentDirection.OUT,
                    created_by_user_id=operator1.id,
                    remarks="Seed calibration adjustment",
                )

            db.flush()

            # -------------------------------------------------
            # Close historical shifts.
            #
            # Keep the final day's Evening shift OPEN so
            # transfer workflow can still be demonstrated.
            # -------------------------------------------------

            if day_index < days - 1:
                FuelService.recalculate_shift(
                    db,
                    morning.id,
                )

                FuelService.close_shift(
                    db=db,
                    shift_id=morning.id,
                    closed_by_user_id=operator1.id,
                )

                FuelService.recalculate_shift(
                    db,
                    evening.id,
                )

                FuelService.close_shift(
                    db=db,
                    shift_id=evening.id,
                    closed_by_user_id=operator1.id,
                )

    db.flush()


def create_transfer_demo(
    db,
    vessels,
    manager,
    operator1,
    start_date: date,
    days: int,
):
    """
    Create one complete transfer workflow on the latest open shifts.
    """

    source = next(v for v in vessels if v.code == "DREDGER-01")
    destination = next(v for v in vessels if v.code == "DREDGER-02")

    latest_date = start_date + timedelta(days=days - 1)

    source_shift = db.scalar(
        select(Shift).where(
            Shift.vessel_id == source.id,
            Shift.shift_date == latest_date,
            Shift.shift_name == "EVENING",
        )
    )

    destination_shift = db.scalar(
        select(Shift).where(
            Shift.vessel_id == destination.id,
            Shift.shift_date == latest_date,
            Shift.shift_name == "EVENING",
        )
    )

    if not source_shift or not destination_shift:
        raise RuntimeError(
            "Could not find latest open shifts for transfer demo."
        )

    existing = db.scalar(
        select(
            __import__(
                "backend.models.transfer",
                fromlist=["FuelTransfer"],
            ).FuelTransfer.id
        ).where(
            __import__(
                "backend.models.transfer",
                fromlist=["FuelTransfer"],
            ).FuelTransfer.from_shift_id == source_shift.id,
            __import__(
                "backend.models.transfer",
                fromlist=["FuelTransfer"],
            ).FuelTransfer.to_shift_id == destination_shift.id,
        )
    )

    if existing:
        return

    transfer = TransferService.initiate_transfer(
        db=db,
        from_vessel_id=source.id,
        from_shift_id=source_shift.id,
        to_vessel_id=destination.id,
        to_shift_id=destination_shift.id,
        initiated_quantity=Decimal("300.000"),
        initiated_by_user_id=operator1.id,
        notes="Seed transfer demonstration",
    )

    TransferService.confirm_receiving(
        db=db,
        transfer_id=transfer.id,
        received_quantity=Decimal("285.000"),
        received_by_user_id=operator1.id,
        notes="15 litres seed transfer loss",
    )

    TransferService.submit_for_manager_review(
        db=db,
        transfer_id=transfer.id,
        submitted_by_user_id=operator1.id,
    )

    TransferService.approve_transfer(
        db=db,
        transfer_id=transfer.id,
        approved_by_user_id=manager.id,
        manager_remark="Seed transfer approved for testing.",
    )


def seed():
    db = SessionLocal()

    try:
        # -----------------------------------------------------
        # Require bootstrap/admin to exist
        # -----------------------------------------------------

        admin = db.scalar(
            select(User)
            .where(User.username == "admin")
        )

        if admin is None:
            raise RuntimeError(
                "Initial admin does not exist. "
                "Start the application once first."
            )

        # -----------------------------------------------------
        # Idempotency
        # -----------------------------------------------------

        if get_user(db, SEED_MARKER_USERNAME):
            print("Seed data already exists. Nothing to do.")
            return

        print("Creating seed users...")

        manager, operator1, operator2 = create_seed_users(
            db,
            admin,
        )

        print("Loading demo master data...")

        vessels, equipment = get_master_data(db)

        start_date = date.today() - timedelta(days=4)
        days = 5

        print(
            f"Creating {days} days of Morning/Evening "
            "fuel and engine data..."
        )

        create_shift_data(
            db=db,
            vessels=vessels,
            equipment=equipment,
            operator1=operator1,
            start_date=start_date,
            days=days,
        )

        print("Creating transfer workflow example...")

        create_transfer_demo(
            db=db,
            vessels=vessels,
            manager=manager,
            operator1=operator1,
            start_date=start_date,
            days=days,
        )

        db.commit()

        print()
        print("======================================")
        print("InsiteFuel V3 seed completed")
        print("======================================")
        print()
        print("Users:")
        print("  Manager : seed_manager / Manager@2026!")
        print("  Operator: operator01  / Operator@2026!")
        print("  Operator: operator02  / Operator@2026!")
        print()
        print(f"Operational dates: {start_date} -> {date.today()}")
        print("Vessels: 3")
        print("Shifts: Morning + Evening")
        print("Engine types: ME + AUX + DG")
        print("Fuel receipts: included")
        print("Fuel adjustments: included")
        print("Transfer workflow: included")
        print()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()