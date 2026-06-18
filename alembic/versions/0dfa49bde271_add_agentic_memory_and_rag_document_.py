"""Add agentic memory, rag document models, and engine metadata

Revision ID: 0dfa49bde271
Revises: e338371b80aa
Create Date: 2025-12-23 14:35:51.971379

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel
import pgvector

# Revision identifiers, used by Alembic
revision: str = '0dfa49bde271'
down_revision: Union[str, Sequence[str], None] = 'e338371b80aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """
    World-Class Schema Synchronization.
    Safely creates new engine tables while acknowledging existing agentic data.
    """
    # 1. CORE EXTENSIONS
    # Ensure semantic search is enabled for the knowledgedocument table
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. CREATE NEW ENGINE TABLES

    # Webhook Ingestor for triggers
    op.create_table('webhook',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workflow_id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('slug', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('secret_key', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_webhook_slug'), 'webhook', ['slug'], unique=True)

    # Immutable Graph Versioning
    op.create_table('workflowversion',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workflow_id', sa.Uuid(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('graph_snapshot', sa.JSON(), nullable=True),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflow.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # High-Fidelity Execution Traces for Streaming
    op.create_table('nodeexecutiontrace',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('execution_id', sa.Uuid(), nullable=False),
        sa.Column('node_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('node_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('inputs', sa.JSON(), nullable=True),
        sa.Column('outputs', sa.JSON(), nullable=True),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['execution_id'], ['workflowexecution.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. ATOMIC STRUCTURAL UPDATES
    # Link workflows to their active versions
    op.add_column('workflow', sa.Column('active_version_id', sa.Uuid(), nullable=True))
    op.add_column('workflow', sa.Column('global_variables', sa.JSON(), nullable=True))

    # Add columns for Idempotency and Version Pinning to executions
    op.add_column('workflowexecution', sa.Column('external_event_id', sa.String(), nullable=True))
    op.add_column('workflowexecution', sa.Column('version_id', sa.Uuid(), nullable=True))

    # Premium: Unique index for Webhook Idempotency
    op.create_index(op.f('ix_workflowexecution_external_event_id'), 'workflowexecution', ['external_event_id'], unique=True)
    op.create_foreign_key(None, 'workflowexecution', 'workflowversion', ['version_id'], ['id'])

def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_constraint(None, 'workflowexecution', type_='foreignkey')
    op.drop_index(op.f('ix_workflowexecution_external_event_id'), table_name='workflowexecution')
    op.drop_column('workflowexecution', 'version_id')
    op.drop_column('workflowexecution', 'external_event_id')
    op.drop_column('workflow', 'global_variables')
    op.drop_column('workflow', 'active_version_id')
    op.drop_table('nodeexecutiontrace')
    op.drop_table('workflowversion')
    op.drop_table('webhook')