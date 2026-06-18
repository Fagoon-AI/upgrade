"""Add schedule and template tables

Revision ID: d4e5f6a7b8c9
Revises: 0b463d51fdf2
Create Date: 2026-01-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = '0b463d51fdf2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Create schedule type enum
    schedule_type_enum = postgresql.ENUM(
        'CRON', 'INTERVAL', 'ONCE',
        name='scheduletype',
        create_type=False
    )
    schedule_type_enum.create(op.get_bind(), checkfirst=True)

    # Create schedule status enum
    schedule_status_enum = postgresql.ENUM(
        'ACTIVE', 'PAUSED', 'DISABLED', 'COMPLETED',
        name='schedulestatus',
        create_type=False
    )
    schedule_status_enum.create(op.get_bind(), checkfirst=True)

    # Create template category enum
    template_category_enum = postgresql.ENUM(
        'AI Automation', 'Data Processing', 'Communication', 'Marketing',
        'Customer Support', 'Development', 'Productivity', 'Analytics', 'Getting Started',
        name='templatecategory',
        create_type=False
    )
    template_category_enum.create(op.get_bind(), checkfirst=True)

    # Create workflow_schedule table
    op.create_table(
        'workflow_schedule',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('workflow_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column(
            'schedule_type',
            postgresql.ENUM('CRON', 'INTERVAL', 'ONCE', name='scheduletype', create_type=False),
            nullable=False,
            server_default='CRON'
        ),
        sa.Column('cron_expression', sa.String(length=100), nullable=True),
        sa.Column('interval_seconds', sa.Integer(), nullable=True),
        sa.Column('run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('timezone', sa.String(length=50), nullable=False, server_default='UTC'),
        sa.Column(
            'status',
            postgresql.ENUM('ACTIVE', 'PAUSED', 'DISABLED', 'COMPLETED', name='schedulestatus', create_type=False),
            nullable=False,
            server_default='ACTIVE'
        ),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_execution_id', sa.Uuid(), nullable=True),
        sa.Column('run_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('consecutive_errors', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('input_data', sa.JSON(), nullable=True, server_default='{}'),
        sa.Column('max_consecutive_errors', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for workflow_schedule
    op.create_index('ix_schedule_user_id', 'workflow_schedule', ['user_id'], unique=False)
    op.create_index('ix_schedule_workflow_id', 'workflow_schedule', ['workflow_id'], unique=False)
    op.create_index('ix_schedule_status', 'workflow_schedule', ['status'], unique=False)
    op.create_index('ix_schedule_next_run_at', 'workflow_schedule', ['next_run_at'], unique=False)
    op.create_index('ix_schedule_user_status', 'workflow_schedule', ['user_id', 'status'], unique=False)
    op.create_index('ix_schedule_workflow_status', 'workflow_schedule', ['workflow_id', 'status'], unique=False)
    op.create_index('ix_schedule_next_run_active', 'workflow_schedule', ['next_run_at', 'status'], unique=False)

    # Create workflow_template table
    op.create_table(
        'workflow_template',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),  # NULL for system templates
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=2000), nullable=False),
        sa.Column('short_description', sa.String(length=255), nullable=False),
        sa.Column(
            'category',
            postgresql.ENUM(
                'AI Automation', 'Data Processing', 'Communication', 'Marketing',
                'Customer Support', 'Development', 'Productivity', 'Analytics', 'Getting Started',
                name='templatecategory', create_type=False
            ),
            nullable=False,
            server_default='Getting Started'
        ),
        sa.Column('tags', sa.JSON(), nullable=True, server_default='[]'),
        sa.Column('graph_definition', sa.JSON(), nullable=False),
        sa.Column('required_connections', sa.JSON(), nullable=True, server_default='[]'),
        sa.Column('icon', sa.String(length=50), nullable=False, server_default='Workflow'),
        sa.Column('difficulty', sa.String(length=20), nullable=False, server_default='beginner'),
        sa.Column('estimated_setup_minutes', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('is_featured', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('is_public', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('clone_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for workflow_template
    op.create_index('ix_template_user_id', 'workflow_template', ['user_id'], unique=False)
    op.create_index('ix_template_category', 'workflow_template', ['category'], unique=False)
    op.create_index('ix_template_is_featured', 'workflow_template', ['is_featured'], unique=False)
    op.create_index('ix_template_is_public', 'workflow_template', ['is_public'], unique=False)
    op.create_index('ix_template_clone_count', 'workflow_template', ['clone_count'], unique=False)
    op.create_index('ix_template_category_featured', 'workflow_template', ['category', 'is_featured'], unique=False)
    op.create_index('ix_template_public_featured', 'workflow_template', ['is_public', 'is_featured'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    # Drop workflow_template indexes
    op.drop_index('ix_template_public_featured', table_name='workflow_template')
    op.drop_index('ix_template_category_featured', table_name='workflow_template')
    op.drop_index('ix_template_clone_count', table_name='workflow_template')
    op.drop_index('ix_template_is_public', table_name='workflow_template')
    op.drop_index('ix_template_is_featured', table_name='workflow_template')
    op.drop_index('ix_template_category', table_name='workflow_template')
    op.drop_index('ix_template_user_id', table_name='workflow_template')

    # Drop workflow_template table
    op.drop_table('workflow_template')

    # Drop workflow_schedule indexes
    op.drop_index('ix_schedule_next_run_active', table_name='workflow_schedule')
    op.drop_index('ix_schedule_workflow_status', table_name='workflow_schedule')
    op.drop_index('ix_schedule_user_status', table_name='workflow_schedule')
    op.drop_index('ix_schedule_next_run_at', table_name='workflow_schedule')
    op.drop_index('ix_schedule_status', table_name='workflow_schedule')
    op.drop_index('ix_schedule_workflow_id', table_name='workflow_schedule')
    op.drop_index('ix_schedule_user_id', table_name='workflow_schedule')

    # Drop workflow_schedule table
    op.drop_table('workflow_schedule')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS templatecategory')
    op.execute('DROP TYPE IF EXISTS schedulestatus')
    op.execute('DROP TYPE IF EXISTS scheduletype')
