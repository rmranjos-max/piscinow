"""proposals, negotiation messages and feasibility

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUMS = {
    "proposal_status": ("ENVIADA", "SUBSTITUIDA", "RECUSADA", "ACEITA", "ENCERRADA"),
    "message_author": ("COMPRADOR", "LOJA"),
    "feasibility_status": ("PENDING", "CONDITIONALLY_APPROVED", "APPROVED", "REJECTED"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    for name, values in ENUMS.items():
        labels = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({labels})")

    op.create_table('proposals',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('partner_member_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('status', _enum('proposal_status'), nullable=False),
    sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('scope', sa.Text(), nullable=False),
    sa.Column('lead_time_days', sa.Integer(), nullable=False),
    sa.Column('valid_until', sa.Date(), nullable=False),
    sa.Column('exclusions', sa.Text(), nullable=True),
    sa.Column('decision_reason', sa.Text(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by', sa.String(length=200), nullable=False),
    sa.CheckConstraint('total > 0', name='ck_proposals_total_positive'),
    sa.CheckConstraint('lead_time_days > 0', name='ck_proposals_lead_time_positive'),
    sa.CheckConstraint('version > 0', name='ck_proposals_version_positive'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ),
    sa.ForeignKeyConstraint(['partner_member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('deal_id', 'partner_member_id', 'version', name='uq_proposals_version')
    )
    op.create_index(
        'uq_proposals_one_open_per_partner', 'proposals', ['deal_id', 'partner_member_id'], unique=True,
        postgresql_where=sa.text("status = 'ENVIADA'"),
    )
    op.create_index(
        'uq_proposals_one_accepted_per_deal', 'proposals', ['deal_id'], unique=True,
        postgresql_where=sa.text("status = 'ACEITA'"),
    )
    op.create_table('proposal_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('proposal_id', sa.UUID(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.CheckConstraint('amount > 0', name='ck_proposal_items_amount_positive'),
    sa.ForeignKeyConstraint(['proposal_id'], ['proposals.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('deal_messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('partner_member_id', sa.UUID(), nullable=False),
    sa.Column('author', _enum('message_author'), nullable=False),
    sa.Column('author_member_id', sa.UUID(), nullable=False),
    sa.Column('is_revision_request', sa.Boolean(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_member_id'], ['members.id'], ),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ),
    sa.ForeignKeyConstraint(['partner_member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('feasibility_checks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('status', _enum('feasibility_status'), nullable=False),
    sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('decided_by', sa.String(length=200), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('deal_id')
    )


def downgrade() -> None:
    op.drop_table('feasibility_checks')
    op.drop_table('deal_messages')
    op.drop_table('proposal_items')
    op.drop_index('uq_proposals_one_accepted_per_deal', table_name='proposals', postgresql_where=sa.text("status = 'ACEITA'"))
    op.drop_index('uq_proposals_one_open_per_partner', table_name='proposals', postgresql_where=sa.text("status = 'ENVIADA'"))
    op.drop_table('proposals')
    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE {name}")
