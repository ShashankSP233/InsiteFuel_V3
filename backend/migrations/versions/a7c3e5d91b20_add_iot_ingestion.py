"""add iot ingestion (payload inbox, vessel/equipment mapping, shift source and auto-close)

Revision ID: a7c3e5d91b20
Revises: f58108d080f5
Create Date: 2026-10-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a7c3e5d91b20'
down_revision: Union[str, Sequence[str], None] = 'f58108d080f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Shifts: where they came from, and when an IoT shift closes itself.
    op.add_column('shifts', sa.Column('source', sa.String(length=20), server_default='MANUAL', nullable=False))
    op.add_column('shifts', sa.Column('auto_close_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('shifts', sa.Column('close_source', sa.String(length=20), nullable=True))
    op.create_index(op.f('ix_shifts_auto_close_at'), 'shifts', ['auto_close_at'], unique=False)

    # Mapping to the IoT vendor's identifiers.
    op.add_column('vessels', sa.Column('iot_vessel_id', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_vessels_iot_vessel_id'), 'vessels', ['iot_vessel_id'], unique=True)
    op.add_column('equipment', sa.Column('iot_engine_name', sa.String(length=50), nullable=True))
    op.create_unique_constraint('uq_equipment_vessel_iot_engine_name', 'equipment', ['vessel_id', 'iot_engine_name'])

    # Inbox of everything the vendor sends.
    op.create_table(
        'iot_payloads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_vessel_id', sa.String(length=100), nullable=True),
        sa.Column('vessel_id', sa.Integer(), nullable=True),
        sa.Column('shift_id', sa.Integer(), nullable=True),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('window_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('shift_date', sa.Date(), nullable=True),
        sa.Column('shift_name', sa.String(length=50), nullable=True),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['shift_id'], ['shifts.id'], ),
        sa.ForeignKeyConstraint(['vessel_id'], ['vessels.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_iot_payloads_external_vessel_id'), 'iot_payloads', ['external_vessel_id'], unique=False)
    op.create_index(op.f('ix_iot_payloads_payload_hash'), 'iot_payloads', ['payload_hash'], unique=False)
    op.create_index(op.f('ix_iot_payloads_shift_id'), 'iot_payloads', ['shift_id'], unique=False)
    op.create_index(op.f('ix_iot_payloads_status'), 'iot_payloads', ['status'], unique=False)
    op.create_index(op.f('ix_iot_payloads_vessel_id'), 'iot_payloads', ['vessel_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_iot_payloads_vessel_id'), table_name='iot_payloads')
    op.drop_index(op.f('ix_iot_payloads_status'), table_name='iot_payloads')
    op.drop_index(op.f('ix_iot_payloads_shift_id'), table_name='iot_payloads')
    op.drop_index(op.f('ix_iot_payloads_payload_hash'), table_name='iot_payloads')
    op.drop_index(op.f('ix_iot_payloads_external_vessel_id'), table_name='iot_payloads')
    op.drop_table('iot_payloads')
    op.drop_constraint('uq_equipment_vessel_iot_engine_name', 'equipment', type_='unique')
    op.drop_column('equipment', 'iot_engine_name')
    op.drop_index(op.f('ix_vessels_iot_vessel_id'), table_name='vessels')
    op.drop_column('vessels', 'iot_vessel_id')
    op.drop_index(op.f('ix_shifts_auto_close_at'), table_name='shifts')
    op.drop_column('shifts', 'close_source')
    op.drop_column('shifts', 'auto_close_at')
    op.drop_column('shifts', 'source')
