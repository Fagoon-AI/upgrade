"""add agent_api table

Revision ID: 7a1e9c3d5f2b
Revises: 0c54bde65644
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a1e9c3d5f2b'
down_revision: Union[str, Sequence[str], None] = '0c54bde65644'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'agent_api',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('agent_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('api_key_hash', sa.String(128), nullable=False),
        sa.Column('api_key_prefix', sa.String(20), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('rate_limit_per_minute', sa.Integer(), server_default='60'),
        sa.Column('timeout_seconds', sa.Integer(), server_default='60'),
        sa.Column('total_calls', sa.Integer(), server_default='0'),
        sa.Column('last_called_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('agent_id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index('ix_agent_api_slug', 'agent_api', ['slug'])
    op.create_index('ix_agent_api_agent', 'agent_api', ['agent_id'])
    op.create_index('ix_agent_api_user', 'agent_api', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_agent_api_user', table_name='agent_api')
    op.drop_index('ix_agent_api_agent', table_name='agent_api')
    op.drop_index('ix_agent_api_slug', table_name='agent_api')
    op.drop_table('agent_api')
