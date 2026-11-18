"""projects and payment allocations can come from an accepted proposal

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('proposal_id', sa.UUID(), nullable=True))
    op.create_foreign_key('projects_proposal_id_fkey', 'projects', 'proposals', ['proposal_id'], ['id'])
    op.add_column('payment_allocations', sa.Column('proposal_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'payment_allocations_proposal_id_fkey', 'payment_allocations', 'proposals', ['proposal_id'], ['id']
    )
    op.drop_constraint('ck_payment_allocations_one_item', 'payment_allocations', type_='check')
    op.create_check_constraint(
        'ck_payment_allocations_one_item', 'payment_allocations',
        'num_nonnulls(product_id, service_id, proposal_id) = 1',
    )


def downgrade() -> None:
    op.drop_constraint('ck_payment_allocations_one_item', 'payment_allocations', type_='check')
    op.create_check_constraint(
        'ck_payment_allocations_one_item', 'payment_allocations', '(product_id IS NULL) <> (service_id IS NULL)'
    )
    op.drop_constraint('payment_allocations_proposal_id_fkey', 'payment_allocations', type_='foreignkey')
    op.drop_column('payment_allocations', 'proposal_id')
    op.drop_constraint('projects_proposal_id_fkey', 'projects', type_='foreignkey')
    op.drop_column('projects', 'proposal_id')
