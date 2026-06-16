"""merge split heads

Revision ID: 8c632576a23b
Revises: 2673b3ca8de9, 6aa267e9e4b1
Create Date: 2026-06-13 10:40:22.134540

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c632576a23b'
down_revision: Union[str, Sequence[str], None] = ('2673b3ca8de9', '6aa267e9e4b1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
