"""installer profiles and assignments

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUSES = ("PENDENTE", "ACEITA", "RECUSADA", "CANCELADA")


def upgrade() -> None:
    labels = ", ".join(f"'{value}'" for value in STATUSES)
    op.execute(f"CREATE TYPE assignment_status AS ENUM ({labels})")

    op.create_table('installer_profiles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('member_id', sa.UUID(), nullable=False),
    sa.Column('service_areas', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('service_kinds', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('member_id')
    )
    op.create_table('installer_assignments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('installer_member_id', sa.UUID(), nullable=False),
    sa.Column('status', postgresql.ENUM(*STATUSES, name='assignment_status', create_type=False), nullable=False),
    sa.Column('assigned_reason', sa.Text(), nullable=False),
    sa.Column('assigned_by', sa.String(length=200), nullable=False),
    sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('response_reason', sa.Text(), nullable=True),
    sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_reason', sa.Text(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ),
    sa.ForeignKeyConstraint(['installer_member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'uq_installer_assignments_one_live_per_deal', 'installer_assignments', ['deal_id'], unique=True,
        postgresql_where=sa.text("status IN ('PENDENTE', 'ACEITA')"),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_installer_assignments_one_live_per_deal', table_name='installer_assignments',
        postgresql_where=sa.text("status IN ('PENDENTE', 'ACEITA')"),
    )
    op.drop_table('installer_assignments')
    op.drop_table('installer_profiles')
    op.execute("DROP TYPE assignment_status")
