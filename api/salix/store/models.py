"""Storage tables.

A deliberate design choice: rich nested objects are persisted as JSON documents
validated by their Pydantic model, with only the columns we actually query
promoted to real columns and indexed. Salix's domain is deeply nested
(a call analysis is six levels deep) and mapping that onto relational tables
would create a second schema that drifts from the first. One contract is worth
more here than third normal form.

The `moments` table is the vector store: an embedding per retrievable
conversational moment. On SQLite the vector lives in a BLOB and similarity is
computed in numpy; on Postgres the same column becomes `vector(1024)` and the
search moves into pgvector. `store.vectors` is the seam.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class OrgRow(Base):
    __tablename__ = "orgs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class RepRow(Base):
    __tablename__ = "reps"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    is_top_performer: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class DealRow(Base):
    __tablename__ = "deals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    stage: Mapped[str] = mapped_column(String(32), default="discovery")
    outcome: Mapped[str] = mapped_column(String(16), default="open", index=True)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class CallRow(Base):
    __tablename__ = "calls"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    deal_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    rep_id: Mapped[str] = mapped_column(String(64), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(24), default="uploaded", index=True)
    outcome: Mapped[str] = mapped_column(String(16), default="open")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ArtifactRow(Base):
    """Per-call analysis outputs, one row per (call, kind).

    Keeping transcript / metrics / scorecard / analysis in one table means a
    new agent adds a `kind`, not a migration.
    """

    __tablename__ = "artifacts"
    call_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("calls.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PlayRow(Base):
    __tablename__ = "plays"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32), index=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class MomentRow(Base):
    """A retrievable slice of conversation -- the unit of RAG in Salix.

    Moments are what the Coach searches when it needs "how did somebody on this
    team handle a pricing objection well", so each carries enough denormalised
    context to be useful without a join.
    """

    __tablename__ = "moments"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    call_id: Mapped[str] = mapped_column(String(64), index=True)
    rep_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    outcome: Mapped[str] = mapped_column(String(16), default="open", index=True)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


Index("ix_moments_org_kind", MomentRow.org_id, MomentRow.kind)


class CoachingPlanRow(Base):
    __tablename__ = "coaching_plans"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    rep_id: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DojoSessionRow(Base):
    __tablename__ = "dojo_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    rep_id: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReportRow(Base):
    __tablename__ = "cycle_reports"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    cycle_label: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
