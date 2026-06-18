"""add missing webhook columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-10 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing columns to webhook table."""
    # Description
    op.add_column('webhook', sa.Column('description', sa.Text(), nullable=True))

    # Secret rotation tracking
    op.add_column('webhook', sa.Column('secret_key_rotated_at', sa.DateTime(timezone=True), nullable=True))

    # Provider configuration
    op.add_column('webhook', sa.Column('provider', sa.String(50), nullable=False, server_default='generic'))

    # Status (active, paused, disabled, rate_limited)
    op.add_column('webhook', sa.Column('status', sa.String(20), nullable=False, server_default='active'))

    # Rate limiting
    op.add_column('webhook', sa.Column('rate_limit', sa.Integer(), nullable=False, server_default='100'))
    op.add_column('webhook', sa.Column('rate_limit_window', sa.DateTime(timezone=True), nullable=True))
    op.add_column('webhook', sa.Column('rate_limit_count', sa.Integer(), nullable=False, server_default='0'))

    # IP allowlist
    op.add_column('webhook', sa.Column('allowed_ips', sa.Text(), nullable=True))

    # Health tracking
    op.add_column('webhook', sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('webhook', sa.Column('total_triggers', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('webhook', sa.Column('failed_triggers', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('webhook', sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'))

    # Additional configuration
    op.add_column('webhook', sa.Column('config_json', sa.Text(), nullable=True))

    # Updated timestamp
    op.add_column('webhook', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))

    # Add indexes (workflow_id index already exists from original migration)
    op.create_index('ix_webhook_workflow_active', 'webhook', ['workflow_id', 'is_active'], unique=False)
    op.create_index('ix_webhook_status', 'webhook', ['status'], unique=False)


def downgrade() -> None:
    """Remove added columns from webhook table."""
    # Drop indexes (workflow_id index was not created by this migration)
    op.drop_index('ix_webhook_status', table_name='webhook')
    op.drop_index('ix_webhook_workflow_active', table_name='webhook')

    # Drop columns
    op.drop_column('webhook', 'updated_at')
    op.drop_column('webhook', 'config_json')
    op.drop_column('webhook', 'consecutive_failures')
    op.drop_column('webhook', 'failed_triggers')
    op.drop_column('webhook', 'total_triggers')
    op.drop_column('webhook', 'last_triggered_at')
    op.drop_column('webhook', 'allowed_ips')
    op.drop_column('webhook', 'rate_limit_count')
    op.drop_column('webhook', 'rate_limit_window')
    op.drop_column('webhook', 'rate_limit')
    op.drop_column('webhook', 'status')
    op.drop_column('webhook', 'provider')
    op.drop_column('webhook', 'secret_key_rotated_at')
    op.drop_column('webhook', 'description')
