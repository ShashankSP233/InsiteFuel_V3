from datetime import date
from decimal import Decimal

from backend.database import SessionLocal
from backend.services.fuel_service import FuelService


def main():
    db = SessionLocal()

    try:
        # -----------------------------------------------------
        # TEST DATA
        # -----------------------------------------------------
        # Use an existing vessel ID from your database.
        vessel_id = 1

        morning_date = date(2026, 10, 2)
        next_morning_date = date(2026, 10, 3)

        # -----------------------------------------------------
        # 1. Establish initial opening fuel
        # -----------------------------------------------------
        morning = FuelService.establish_initial_opening_fuel(
            db=db,
            vessel_id=vessel_id,
            shift_date=morning_date,
            opening_fuel=Decimal("500.000"),
        )

        db.commit()

        print(
            f"Morning shift created: "
            f"id={morning.id}, "
            f"opening={morning.opening_fuel}"
        )

        # -----------------------------------------------------
        # 2. Calculate initial balance
        # -----------------------------------------------------
        FuelService.recalculate_shift(
            db,
            morning.id,
        )

        db.commit()

        print(
            f"Morning closing: "
            f"{morning.calculated_closing_fuel}"
        )

        # -----------------------------------------------------
        # 3. Create Evening shift
        # -----------------------------------------------------
        evening = FuelService.get_or_create_shift(
            db=db,
            vessel_id=vessel_id,
            shift_date=morning_date,
            shift_name="EVENING",
        )

        db.commit()

        print(
            f"Evening shift created: "
            f"id={evening.id}, "
            f"opening={evening.opening_fuel}"
        )

        # -----------------------------------------------------
        # 4. Recalculate Evening
        # -----------------------------------------------------
        FuelService.recalculate_shift(
            db,
            evening.id,
        )

        db.commit()

        print(
            f"Evening closing: "
            f"{evening.calculated_closing_fuel}"
        )

        # -----------------------------------------------------
        # 5. Create next day's Morning shift
        # -----------------------------------------------------
        next_morning = FuelService.get_or_create_shift(
            db=db,
            vessel_id=vessel_id,
            shift_date=next_morning_date,
            shift_name="MORNING",
        )

        db.commit()

        print(
            f"Next Morning shift created: "
            f"id={next_morning.id}, "
            f"opening={next_morning.opening_fuel}"
        )

        # -----------------------------------------------------
        # 6. Verify chain
        # -----------------------------------------------------
        assert (
            next_morning.opening_fuel
            == evening.calculated_closing_fuel
        )

        print()
        print("PASS: Continuous shift fuel chain works.")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()