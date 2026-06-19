"""merge remaining heads

Revision ID: 42a6dc963da9
Revises: 47a607006441, e5f6a7b8c9d0
Create Date: 2026-06-18 15:51:46.495815

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42a6dc963da9'
down_revision: Union[str, Sequence[str], None] = ('47a607006441', 'e5f6a7b8c9d0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
