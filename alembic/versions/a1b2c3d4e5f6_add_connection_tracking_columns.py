"""add connection tracking columns

Revision ID: a1b2c3d4e5f6
Revises: fdb4494e113e
Create Date: 2026-01-10 07:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'fdb4494e113e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tracking columns to connection table."""
    # Add is_active column with default True
    op.add_column('connection', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))

    # Add last_used_at column (nullable)
    op.add_column('connection', sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True))

    # Add use_count column with default 0
    op.add_column('connection', sa.Column('use_count', sa.Integer(), nullable=False, server_default='0'))

    # Add index on provider column
    op.create_index(op.f('ix_connection_provider'), 'connection', ['provider'], unique=False)

    # Add composite indexes
    op.create_index('ix_connection_user_provider', 'connection', ['user_id', 'provider'], unique=False)
    op.create_index('ix_connection_user_active', 'connection', ['user_id', 'is_active'], unique=False)


def downgrade() -> None:
    """Remove tracking columns from connection table."""
    # Drop indexes
    op.drop_index('ix_connection_user_active', table_name='connection')
    op.drop_index('ix_connection_user_provider', table_name='connection')
    op.drop_index(op.f('ix_connection_provider'), table_name='connection')

    # Drop columns
    op.drop_column('connection', 'use_count')
    op.drop_column('connection', 'last_used_at')
    op.drop_column('connection', 'is_active')
