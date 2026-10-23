"""track whether a fuel transaction changes shift balances"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d2a184e95f"
down_revision: Union[str, Sequence[str], None] = "a4c91e65d2bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "fuel_transactions",
        sa.Column("affects_balance", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("fuel_transactions", "affects_balance", server_default=None)


def downgrade() -> None:
    op.drop_column("fuel_transactions", "affects_balance")
