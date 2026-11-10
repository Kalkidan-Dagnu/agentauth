"""
SQLAlchemy ORM models for AgentAuth.

Three tables:
  - agents      — registered AI agents
  - policies    — natural language policy definitions
  - audit_log   — every PermissionDecision ever made

These are the persistence layer. The Pydantic models in core/models.py
remain the domain models used by the engine and API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


class PolicyRow(Base):
    """
    Persisted policy.  Maps 1-to-1 with the Policy Pydantic model.
    Rules are stored as a JSON array.
    """

    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rules: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now, onupdate=_now
    )

    def __repr__(self) -> str:
        return f"<PolicyRow id={self.id!r} name={self.name!r}>"


class AgentRow(Base):
    """
    Persisted agent.  Maps 1-to-1 with the Agent Pydantic model.
    Scopes and policy_ids are stored as JSON arrays.
    """

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    policy_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now
    )

    # Relationship to audit log entries
    audit_entries: Mapped[list[AuditLogRow]] = relationship(
        "AuditLogRow", back_populates="agent", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<AgentRow id={self.id!r} name={self.name!r} owner={self.owner_id!r}>"


class AuditLogRow(Base):
    """
    Persisted PermissionDecision.

    Every call to /agents/{id}/evaluate writes one row here, giving a
    complete, queryable audit trail of every decision AgentAuth has made.
    """

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    # The request_id from PermissionDecision (for client-side correlation)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Permission fields
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    resource: Mapped[str] = mapped_column(String(255), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Decision fields
    result: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # ALLOW/DENY/ESCALATE
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)  # HIGH/MEDIUM/LOW
    matched_rules: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now, index=True
    )

    # Relationship back to agent
    agent: Mapped[AgentRow] = relationship("AgentRow", back_populates="audit_entries")

    def __repr__(self) -> str:
        return (
            f"<AuditLogRow id={self.id!r} agent={self.agent_id!r} "
            f"action={self.action!r} result={self.result!r}>"
        )
