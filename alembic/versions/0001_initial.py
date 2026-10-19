"""Initial schema: append-only events and decision records, review tasks, DB-level guards.

Revision ID: 0001
Revises:
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVIDENCE_TABLES = ("events", "decision_records")

GUARD_FUNCTIONS = """
CREATE FUNCTION abhiyogah_evidence_is_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'evidence is append-only: % on % is not allowed', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE FUNCTION abhiyogah_review_task_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.status = 'OPEN' AND NEW.status = 'DONE'
       AND NEW.closed_by_event_id IS NOT NULL
       AND (NEW.task_id, NEW.complaint_id, NEW.kind, NEW.created_at, NEW.task)
           IS NOT DISTINCT FROM (OLD.task_id, OLD.complaint_id, OLD.kind, OLD.created_at, OLD.task)
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'review tasks are only closed by a business event; % is not allowed', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;
"""


def upgrade() -> None:
    """Create the tables and the triggers that forbid rewriting evidence."""
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Text(), nullable=False, unique=True),
        sa.Column("complaint_id", sa.Text(), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_events_complaint_id", "events", ["complaint_id"])

    op.create_table(
        "decision_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hash", sa.String(64), nullable=False, unique=True),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("complaint_id", sa.Text(), nullable=False),
        sa.Column("obligation_id", sa.Text(), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record", postgresql.JSONB(), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("complaint_id", "prev_hash", name="uq_decision_records_chain_link"),
    )
    op.create_index(
        "ix_decision_records_complaint_id_id", "decision_records", ["complaint_id", "id"]
    )

    op.create_table(
        "review_tasks",
        sa.Column("task_id", sa.Text(), primary_key=True),
        sa.Column("complaint_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task", postgresql.JSONB(), nullable=False),
        sa.Column(
            "closed_by_event_id",
            sa.Text(),
            sa.ForeignKey("events.event_id"),
            nullable=True,
        ),
    )
    op.create_index("ix_review_tasks_complaint_id", "review_tasks", ["complaint_id"])

    op.execute(GUARD_FUNCTIONS)
    for table in EVIDENCE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION abhiyogah_evidence_is_append_only()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION abhiyogah_evidence_is_append_only()"
        )
    op.execute(
        "CREATE TRIGGER review_tasks_guard BEFORE UPDATE OR DELETE ON review_tasks "
        "FOR EACH ROW EXECUTE FUNCTION abhiyogah_review_task_guard()"
    )
    op.execute(
        "CREATE TRIGGER review_tasks_no_truncate BEFORE TRUNCATE ON review_tasks "
        "FOR EACH STATEMENT EXECUTE FUNCTION abhiyogah_evidence_is_append_only()"
    )


def downgrade() -> None:
    """Refused: downgrading would drop evidence (CLAUDE.md hard rule 7)."""
    raise RuntimeError("the initial schema holds evidence and is never downgraded")
