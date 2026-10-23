"""add admin-approved fuel issues"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a4c91e65d2bf"
down_revision: Union[str, Sequence[str], None] = "bd761e949f2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fuel_issues",
        sa.CheckConstraint("quantity > 0", name="ck_fuel_issues_quantity_positive"),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vessel_id", sa.Integer(), sa.ForeignKey("vessels.id"), nullable=False),
        sa.Column("shift_id", sa.Integer(), sa.ForeignKey("shifts.id"), nullable=False),
        sa.Column("receiving_vessel", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("admin_remark", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_fuel_issues_vessel_id", "fuel_issues", ["vessel_id"])
    op.create_index("ix_fuel_issues_shift_id", "fuel_issues", ["shift_id"])
    op.create_index("ix_fuel_issues_status", "fuel_issues", ["status"])


def downgrade() -> None:
    op.drop_index("ix_fuel_issues_status", table_name="fuel_issues")
    op.drop_index("ix_fuel_issues_shift_id", table_name="fuel_issues")
    op.drop_index("ix_fuel_issues_vessel_id", table_name="fuel_issues")
    op.drop_table("fuel_issues")
