"""create llm_model_configs

Revision ID: a96116f90767
Revises: None
Create Date: 2026-06-10 17:19:50.638817

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a96116f90767'
down_revision: Union[str, None] = '6aa267e9e4b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create llm_model_configs table
    op.create_table(
        'llm_model_configs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('provider', sa.String(length=100), nullable=False),
        sa.Column('model_id', sa.String(length=255), nullable=True),
        sa.Column('api_key', sa.Text(), nullable=True),
        sa.Column('features', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('agent_ids', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('workflow_ids', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_llm_model_configs_user_id'), 'llm_model_configs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_llm_model_configs_user_id'), table_name='llm_model_configs')
    op.drop_table('llm_model_configs')
