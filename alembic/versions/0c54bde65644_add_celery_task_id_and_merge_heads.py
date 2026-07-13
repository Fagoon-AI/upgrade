"""add celery_task_id to workflowexecution and merge heads

Revision ID: 0c54bde65644
Revises: 1b05306dc143, 548d7155be22
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c54bde65644'
down_revision: Union[str, Sequence[str], None] = ('1b05306dc143', '548d7155be22')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'workflowexecution',
        sa.Column('celery_task_id', sa.String(length=255), nullable=True)
    )
    op.create_index(
        op.f('ix_workflowexecution_celery_task_id'),
        'workflowexecution',
        ['celery_task_id'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_workflowexecution_celery_task_id'),
        table_name='workflowexecution'
    )
    op.drop_column('workflowexecution', 'celery_task_id')
