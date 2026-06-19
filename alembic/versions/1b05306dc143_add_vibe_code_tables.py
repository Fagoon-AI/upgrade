"""add_vibe_code_tables

Revision ID: 1b05306dc143
Revises: 6dd8f9ac7fcd
Create Date: 2026-06-19 10:42:49.781015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b05306dc143'
down_revision: Union[str, Sequence[str], None] = '6dd8f9ac7fcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('user_llm_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('provider', sa.String(), nullable=False),
    sa.Column('model', sa.String(), nullable=False),
    sa.Column('api_key', sa.String(), nullable=True),
    sa.Column('api_base', sa.String(), nullable=True),
    sa.Column('parameters', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_llm_configs_user_id'), 'user_llm_configs', ['user_id'], unique=True)
    op.create_table('vibe_code_executions',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=True),
    sa.Column('code', sa.String(), nullable=True),
    sa.Column('tool_graph', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('error', sa.String(), nullable=True),
    sa.Column('logs', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_vibe_code_executions_user_id'), 'vibe_code_executions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_vibe_code_executions_user_id'), table_name='vibe_code_executions')
    op.drop_table('vibe_code_executions')
    op.drop_index(op.f('ix_user_llm_configs_user_id'), table_name='user_llm_configs')
    op.drop_table('user_llm_configs')