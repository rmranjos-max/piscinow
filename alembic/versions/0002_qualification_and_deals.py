"""qualification and deals

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUMS = {
    "qualification_status": ("EM_ANDAMENTO", "QUALIFICADA"),
    "consent_state": ("NAO_RESPONDIDO", "CONCEDIDO", "RECUSADO"),
    "field_source": ("CLIENTE", "PARCEIRO", "ADMIN"),
    "verification_status": ("DECLARADO", "VERIFICADO", "PENDENTE"),
    "deal_status": (
        "NEW", "QUALIFIED", "MATCHED", "PARTNER_REVIEW", "PROPOSAL_SENT",
        "NEGOTIATING", "ACCEPTED", "LOST", "CANCELLED",
    ),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    for name, values in ENUMS.items():
        labels = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({labels})")

    op.add_column(
        "conversations",
        sa.Column("purpose", sa.String(length=20), server_default=sa.text("'landing'"), nullable=False),
    )

    op.create_table('lead_qualifications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('member_id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=True),
    sa.Column('status', _enum('qualification_status'), nullable=False),
    sa.Column('consent', _enum('consent_state'), nullable=False),
    sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('asks', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('attention_note', sa.Text(), nullable=True),
    sa.Column('attention_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('member_id')
    )
    op.create_table('qualification_fields',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('qualification_id', sa.UUID(), nullable=False),
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('value', sa.String(length=300), nullable=False),
    sa.Column('source', _enum('field_source'), nullable=False),
    sa.Column('verification', _enum('verification_status'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['qualification_id'], ['lead_qualifications.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('qualification_id', 'key', name='uq_qualification_fields_key')
    )
    op.create_table('deals',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('number', sa.Integer(), sa.Identity(always=False, start=1), nullable=False),
    sa.Column('member_id', sa.UUID(), nullable=False),
    sa.Column('qualification_id', sa.UUID(), nullable=False),
    sa.Column('status', _enum('deal_status'), nullable=False),
    sa.Column('assigned_member_id', sa.UUID(), nullable=True),
    sa.Column('lost_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['assigned_member_id'], ['members.id'], ),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.ForeignKeyConstraint(['qualification_id'], ['lead_qualifications.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('number')
    )
    op.create_index(
        'uq_deals_one_active_per_member', 'deals', ['member_id'], unique=True,
        postgresql_where=sa.text("status NOT IN ('LOST', 'CANCELLED')"),
    )
    op.create_table('deal_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('from_status', sa.String(length=20), nullable=True),
    sa.Column('to_status', sa.String(length=20), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('actor', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('deal_events')
    op.drop_index('uq_deals_one_active_per_member', table_name='deals', postgresql_where=sa.text("status NOT IN ('LOST', 'CANCELLED')"))
    op.drop_table('deals')
    op.drop_table('qualification_fields')
    op.drop_table('lead_qualifications')
    op.drop_column('conversations', 'purpose')
    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE {name}")
