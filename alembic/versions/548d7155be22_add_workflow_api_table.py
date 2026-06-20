"""add_workflow_api_table

Revision ID: 548d7155be22
Revises: 42a6dc963da9
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = '548d7155be22'
down_revision = '42a6dc963da9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('workflow_api',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workflow_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('api_key_hash', sa.String(128), nullable=False),
        sa.Column('api_key_prefix', sa.String(20), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('rate_limit_per_minute', sa.Integer(), server_default='60'),
        sa.Column('timeout_seconds', sa.Integer(), server_default='120'),
        sa.Column('total_calls', sa.Integer(), server_default='0'),
        sa.Column('last_called_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.UniqueConstraint('workflow_id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index('ix_workflow_api_slug', 'workflow_api', ['slug'])
    op.create_index('ix_workflow_api_workflow', 'workflow_api', ['workflow_id'])


def downgrade():
    op.drop_index('ix_workflow_api_workflow')
    op.drop_index('ix_workflow_api_slug')
    op.drop_table('workflow_api')
