"""make soundings shift specific

Revision ID: f88381657121
Revises: c839475d3f6c
Create Date: 2026-09-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f88381657121"
down_revision: Union[str, Sequence[str], None] = "c839475d3f6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the new shift relationship first.
    op.add_column(
        "soundings",
        sa.Column(
            "shift_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_soundings_shift_id",
        "soundings",
        ["shift_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_soundings_shift_id_shifts",
        "soundings",
        "shifts",
        ["shift_id"],
        ["id"],
    )

    # Remove the old one-sounding-per-vessel/day restriction.


    # Deterministically migrate old soundings where exactly ONE shift
    # exists for the same vessel/date.
    #
    # If both MORNING and EVENING exist, the sounding is left unmapped
    # because we cannot safely guess which shift it belongs to.
    op.execute(
        """
        UPDATE soundings AS s
        SET shift_id = matched.shift_id
        FROM (
            SELECT
                s2.id AS sounding_id,
                MIN(sh.id) AS shift_id
            FROM soundings AS s2
            JOIN shifts AS sh
              ON sh.vessel_id = s2.vessel_id
             AND sh.shift_date = s2.report_date
            GROUP BY s2.id
            HAVING COUNT(sh.id) = 1
        ) AS matched
        WHERE s.id = matched.sounding_id
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_soundings_shift_id_shifts",
        "soundings",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_soundings_shift_id",
        table_name="soundings",
    )

    op.drop_column(
        "soundings",
        "shift_id",
    )
