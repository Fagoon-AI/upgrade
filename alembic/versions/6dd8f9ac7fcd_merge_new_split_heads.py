"""merge new split heads

Revision ID: 6dd8f9ac7fcd
Revises: 47a607006441, e5f6a7b8c9d0
Create Date: 2026-06-18 17:15:52.100891

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6dd8f9ac7fcd'
down_revision: Union[str, Sequence[str], None] = ('47a607006441', 'e5f6a7b8c9d0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
