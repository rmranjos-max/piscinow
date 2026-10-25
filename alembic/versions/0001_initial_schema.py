"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Enum types are created once, up front: profile_type is shared by three tables.
    op.execute("CREATE TYPE profile_type AS ENUM ('COMPRADOR', 'LOJA', 'PRESTADOR', 'EMBAIXADOR')")
    op.execute("CREATE TYPE member_status AS ENUM ('PENDING', 'WAITLISTED', 'APPROVED', 'REJECTED')")
    op.execute("CREATE TYPE memory_kind AS ENUM ('FACT', 'RULE', 'FAQ', 'CORRECTION')")
    op.execute("CREATE TYPE memory_source AS ENUM ('AUTO', 'HUMAN')")
    op.execute("CREATE TYPE product_kind AS ENUM ('PISCINA', 'EQUIPAMENTO')")
    op.execute("CREATE TYPE service_kind AS ENUM ('INSTALACAO', 'MANUTENCAO', 'REPARO')")
    op.execute("CREATE TYPE message_role AS ENUM ('USER', 'AGENT')")
    op.execute("CREATE TYPE project_status AS ENUM ('RASCUNHO', 'CONFIRMADO')")
    op.execute("CREATE TYPE payment_status AS ENUM ('PENDENTE', 'PAGO')")
    op.execute("CREATE TYPE payment_stage AS ENUM ('TERRAPLANAGEM', 'ESTRUTURA', 'REVESTIMENTO', 'ACABAMENTO')")
    op.execute("CREATE TYPE allocation_status AS ENUM ('RETIDO', 'LIBERADO')")
    op.create_table('admin_users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('members',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('profile_type', postgresql.ENUM('COMPRADOR', 'LOJA', 'PRESTADOR', 'EMBAIXADOR', name='profile_type', create_type=False), nullable=False),
    sa.Column('status', postgresql.ENUM('PENDING', 'WAITLISTED', 'APPROVED', 'REJECTED', name='member_status', create_type=False), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('phone', sa.String(length=30), nullable=True),
    sa.Column('region', sa.String(length=100), nullable=True),
    sa.Column('profile_details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('referral_code', sa.String(length=20), nullable=True),
    sa.Column('referred_by_member_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_by', sa.String(length=200), nullable=True),
    sa.Column('password_hash', sa.String(length=200), nullable=True),
    sa.Column('set_password_token', sa.String(length=64), nullable=True),
    sa.Column('set_password_token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['referred_by_member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('referral_code'),
    sa.UniqueConstraint('set_password_token')
    )
    op.create_table('memory_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('kind', postgresql.ENUM('FACT', 'RULE', 'FAQ', 'CORRECTION', name='memory_kind', create_type=False), nullable=False),
    sa.Column('source', postgresql.ENUM('AUTO', 'HUMAN', name='memory_source', create_type=False), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.Vector(384), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('profile_type', postgresql.ENUM('COMPRADOR', 'LOJA', 'PRESTADOR', 'EMBAIXADOR', name='profile_type', create_type=False), nullable=True),
    sa.Column('created_by', sa.String(length=200), nullable=True),
    sa.Column('superseded_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['superseded_by'], ['memory_items.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('conversations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('member_id', sa.UUID(), nullable=True),
    sa.Column('profile_type_detected', postgresql.ENUM('COMPRADOR', 'LOJA', 'PRESTADOR', 'EMBAIXADOR', name='profile_type', create_type=False), nullable=True),
    sa.Column('collected_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('products',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('member_id', sa.UUID(), nullable=False),
    sa.Column('kind', postgresql.ENUM('PISCINA', 'EQUIPAMENTO', name='product_kind', create_type=False), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('size_label', sa.String(length=50), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('services',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('member_id', sa.UUID(), nullable=False),
    sa.Column('kind', postgresql.ENUM('INSTALACAO', 'MANUTENCAO', 'REPARO', name='service_kind', create_type=False), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('price_min', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('price_max', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('role', postgresql.ENUM('USER', 'AGENT', name='message_role', create_type=False), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('projects',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('member_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=True),
    sa.Column('status', postgresql.ENUM('RASCUNHO', 'CONFIRMADO', name='project_status', create_type=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('member_id')
    )
    op.create_table('payments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('status', postgresql.ENUM('PENDENTE', 'PAGO', name='payment_status', create_type=False), nullable=False),
    sa.Column('external_charge_id', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id')
    )
    op.create_table('project_services',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('service_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('payment_allocations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('payment_id', sa.UUID(), nullable=False),
    sa.Column('stage', postgresql.ENUM('TERRAPLANAGEM', 'ESTRUTURA', 'REVESTIMENTO', 'ACABAMENTO', name='payment_stage', create_type=False), nullable=False),
    sa.Column('recipient_member_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=True),
    sa.Column('service_id', sa.UUID(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('status', postgresql.ENUM('RETIDO', 'LIBERADO', name='allocation_status', create_type=False), nullable=False),
    sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('released_by', sa.String(length=200), nullable=True),
    sa.Column('external_transfer_id', sa.String(length=200), nullable=True),
    sa.CheckConstraint('(product_id IS NULL) <> (service_id IS NULL)', name='ck_payment_allocations_one_item'),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.ForeignKeyConstraint(['recipient_member_id'], ['members.id'], ),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('payment_allocations')
    op.drop_table('project_services')
    op.drop_table('payments')
    op.drop_table('projects')
    op.drop_table('messages')
    op.drop_table('services')
    op.drop_table('products')
    op.drop_table('conversations')
    op.drop_table('memory_items')
    op.drop_table('members')
    op.drop_table('admin_users')
    op.execute("DROP TYPE allocation_status")
    op.execute("DROP TYPE payment_stage")
    op.execute("DROP TYPE payment_status")
    op.execute("DROP TYPE project_status")
    op.execute("DROP TYPE message_role")
    op.execute("DROP TYPE service_kind")
    op.execute("DROP TYPE product_kind")
    op.execute("DROP TYPE memory_source")
    op.execute("DROP TYPE memory_kind")
    op.execute("DROP TYPE member_status")
    op.execute("DROP TYPE profile_type")
