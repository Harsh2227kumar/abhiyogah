"""SQLAlchemy 2 tables: append-only ``events`` and ``decision_records``, plus ``review_tasks``.

Evidence tables are guarded in the database itself (see the initial Alembic migration): triggers
reject every UPDATE, DELETE and TRUNCATE, so not even a buggy or malicious client can rewrite
history. ``review_tasks`` rejects DELETE and any UPDATE other than closing the task.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

__all__ = ["Base", "DecisionRow", "EventRow", "ReviewTaskRow"]


class Base(DeclarativeBase):
    """Declarative base for the store's tables."""


class EventRow(Base):
    """One business event; bitemporal (``occurred_at`` business time, ``recorded_at`` system)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(Text, unique=True)
    complaint_id: Mapped[str] = mapped_column(Text, index=True)
    type: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB)
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DecisionRow(Base):
    """One sealed decision record; ``id`` order is chain order within a complaint."""

    __tablename__ = "decision_records"
    __table_args__ = (
        UniqueConstraint("complaint_id", "prev_hash", name="uq_decision_records_chain_link"),
        Index("ix_decision_records_complaint_id_id", "complaint_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    complaint_id: Mapped[str] = mapped_column(Text)
    obligation_id: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(32))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    record: Mapped[dict[str, Any]] = mapped_column(JSONB)
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReviewTaskRow(Base):
    """A human-review task opened by the engine."""

    __tablename__ = "review_tasks"

    task_id: Mapped[str] = mapped_column(Text, primary_key=True)
    complaint_id: Mapped[str] = mapped_column(Text, index=True)
    kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    task: Mapped[dict[str, Any]] = mapped_column(JSONB)
    closed_by_event_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("events.event_id"), nullable=True
    )
