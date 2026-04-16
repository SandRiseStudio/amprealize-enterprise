"""Add dedicated action schema tables for ActionService.

Revision ID: 20260409_action_schema
Revises: 20260406_metrics_trace
Create Date: 2026-04-09

ActionService uses unqualified SQL against ``actions`` and ``replays`` with a
service-specific search_path. In the modular-monolith layout that cannot share
the ``execution`` schema because ``execution.actions`` and ``execution.replays``
already belong to the run/workflow model with different columns.

This migration creates a dedicated ``action`` schema that matches the
ActionService contract and legacy SQL migration.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260409_action_schema"
down_revision: Union[str, None] = "20260406_metrics_trace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS action"))

    op.create_table(
        "actions",
        sa.Column("action_id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("actor_role", sa.Text(), nullable=False),
        sa.Column("actor_surface", sa.Text(), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("behaviors_cited", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("related_run_id", sa.Text(), nullable=True),
        sa.Column("audit_log_event_id", sa.Text(), nullable=True),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("replay_status", sa.Text(), nullable=False, server_default=sa.text("'NOT_STARTED'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "actor_surface IN ('cli', 'api', 'mcp', 'web')",
            name="ck_action_actions_actor_surface",
        ),
        sa.CheckConstraint(
            "replay_status IN ('NOT_STARTED', 'IN_PROGRESS', 'SUCCEEDED', 'FAILED')",
            name="ck_action_actions_replay_status",
        ),
        sa.PrimaryKeyConstraint("action_id"),
        schema="action",
    )
    op.create_index("idx_action_actions_timestamp", "actions", [sa.text("timestamp DESC")], schema="action")
    op.create_index("idx_action_actions_actor_id", "actions", ["actor_id"], schema="action")
    op.create_index("idx_action_actions_related_run_id", "actions", ["related_run_id"], schema="action")
    op.create_index("idx_action_actions_replay_status", "actions", ["replay_status"], schema="action")
    op.create_index(
        "idx_action_actions_behaviors_cited",
        "actions",
        ["behaviors_cited"],
        unique=False,
        schema="action",
        postgresql_using="gin",
    )
    op.create_index(
        "idx_action_actions_metadata",
        "actions",
        ["metadata"],
        unique=False,
        schema="action",
        postgresql_using="gin",
    )

    op.create_table(
        "replays",
        sa.Column("replay_id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("logs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("failed_action_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("action_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("succeeded_action_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("audit_log_event_id", sa.Text(), nullable=True),
        sa.Column("strategy", sa.Text(), nullable=False, server_default=sa.text("'SEQUENTIAL'")),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("actor_role", sa.Text(), nullable=True),
        sa.Column("actor_surface", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('PENDING', 'IN_PROGRESS', 'SUCCEEDED', 'FAILED', 'PARTIAL')",
            name="ck_action_replays_status",
        ),
        sa.CheckConstraint(
            "progress >= 0.0 AND progress <= 1.0",
            name="ck_action_replays_progress",
        ),
        sa.PrimaryKeyConstraint("replay_id"),
        schema="action",
    )
    op.create_index("idx_action_replays_status", "replays", ["status"], schema="action")
    op.create_index("idx_action_replays_created_at", "replays", [sa.text("created_at DESC")], schema="action")


def downgrade() -> None:
    op.drop_index("idx_action_replays_created_at", table_name="replays", schema="action")
    op.drop_index("idx_action_replays_status", table_name="replays", schema="action")
    op.drop_table("replays", schema="action")

    op.drop_index("idx_action_actions_metadata", table_name="actions", schema="action")
    op.drop_index("idx_action_actions_behaviors_cited", table_name="actions", schema="action")
    op.drop_index("idx_action_actions_replay_status", table_name="actions", schema="action")
    op.drop_index("idx_action_actions_related_run_id", table_name="actions", schema="action")
    op.drop_index("idx_action_actions_actor_id", table_name="actions", schema="action")
    op.drop_index("idx_action_actions_timestamp", table_name="actions", schema="action")
    op.drop_table("actions", schema="action")

    op.execute(sa.text("DROP SCHEMA IF EXISTS action CASCADE"))