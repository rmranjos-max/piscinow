"""partner profiles and matching decisions

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUMS = {
    "match_override": ("NENHUM", "INCLUIDA", "EXCLUIDA"),
    "partner_response": ("PENDENTE", "EM_ANALISE", "RECUSADA"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    for name, values in ENUMS.items():
        labels = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({labels})")

    op.create_table('partner_profiles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('member_id', sa.UUID(), nullable=False),
    sa.Column('service_areas', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('pool_types', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('budget_bands', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by', sa.String(length=200), nullable=True),
    sa.CheckConstraint('capacity >= 1', name='ck_partner_profiles_capacity_positive'),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('member_id')
    )
    op.create_table('matching_decisions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('partner_member_id', sa.UUID(), nullable=False),
    sa.Column('eligible', sa.Boolean(), nullable=False),
    sa.Column('criteria', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('override', _enum('match_override'), nullable=False),
    sa.Column('override_reason', sa.Text(), nullable=True),
    sa.Column('override_by', sa.String(length=200), nullable=True),
    sa.Column('override_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('shared_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('response', _enum('partner_response'), nullable=False),
    sa.Column('response_reason', sa.Text(), nullable=True),
    sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ),
    sa.ForeignKeyConstraint(['partner_member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('deal_id', 'partner_member_id', name='uq_matching_decisions_deal_partner')
    )


def downgrade() -> None:
    op.drop_table('matching_decisions')
    op.drop_table('partner_profiles')
    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE {name}")
