"""proposal items point to a catalog product and keep its photo

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('proposal_items', sa.Column('product_id', sa.UUID(), nullable=True))
    op.add_column('proposal_items', sa.Column('photo_key', sa.String(length=120), nullable=True))
    op.add_column('proposal_items', sa.Column('photo_thumb_key', sa.String(length=120), nullable=True))
    op.create_foreign_key(
        'proposal_items_product_id_fkey', 'proposal_items', 'products', ['product_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('proposal_items_product_id_fkey', 'proposal_items', type_='foreignkey')
    op.drop_column('proposal_items', 'photo_thumb_key')
    op.drop_column('proposal_items', 'photo_key')
    op.drop_column('proposal_items', 'product_id')
