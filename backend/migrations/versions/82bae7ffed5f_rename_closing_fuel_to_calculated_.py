"""rename closing fuel to calculated closing fuel

Revision ID: 82bae7ffed5f
Revises: 3a52d5effb6d
Create Date: 2026-09-03 16:49:09.146275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82bae7ffed5f'
down_revision: Union[str, Sequence[str], None] = '3a52d5effb6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "shifts",
        "closing_fuel",
        new_column_name="calculated_closing_fuel",
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "shifts",
        "calculated_closing_fuel",
        new_column_name="closing_fuel",
    )