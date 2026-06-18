"""Add created_by to workflowversion

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-01-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add created_by column to workflowversion table."""
    op.add_column('workflowversion', sa.Column('created_by', sa.Uuid(), nullable=True))


def downgrade() -> None:
    """Remove created_by column from workflowversion table."""
    op.drop_column('workflowversion', 'created_by')
