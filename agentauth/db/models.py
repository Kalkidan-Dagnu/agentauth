"""
SQLAlchemy ORM models for AgentAuth.

Five tables:
  - agents           — registered AI agents
  - policies         — natural language policy definitions
  - audit_log        — every PermissionDecision ever made
  - webhooks         — per-agent webhook endpoint registrations
  - webhook_deliveries — individual delivery attempts for each webhook

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
    Integer,
    String,
    Text,
)
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
    # Relationship to webhook registrations
    webhooks: Mapped[list[WebhookRow]] = relationship(
        "WebhookRow", back_populates="agent", lazy="select"
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


class WebhookRow(Base):
    """
    A webhook endpoint registered to receive PermissionDecision notifications
    for a specific agent.

    ``events`` is a JSON array of decision result strings the caller wants
    to receive, e.g. ["ESCALATE"] or ["ALLOW", "DENY", "ESCALATE"].
    An empty list means "all events".

    ``secret`` is an optional shared secret used to generate an
    X-AgentAuth-Signature header so the receiver can verify authenticity.
    """

    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list,
        comment="Decision results to notify on, e.g. ['ESCALATE']. Empty = all.",
    )
    secret: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)

    # Relationships
    agent: Mapped[AgentRow] = relationship("AgentRow", back_populates="webhooks")
    deliveries: Mapped[list[WebhookDeliveryRow]] = relationship(
        "WebhookDeliveryRow", back_populates="webhook", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<WebhookRow id={self.id!r} agent={self.agent_id!r} url={self.url!r}>"


class WebhookDeliveryRow(Base):
    """
    A single delivery attempt for a WebhookRow.

    One row is written per HTTP request made to the webhook URL.
    Retries produce additional rows so the full retry history is visible.
    """

    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    webhook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The audit_log request_id this delivery is for (correlation, not FK)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now, index=True
    )

    # Relationship back to webhook
    webhook: Mapped[WebhookRow] = relationship("WebhookRow", back_populates="deliveries")

    def __repr__(self) -> str:
        return (
            f"<WebhookDeliveryRow id={self.id!r} webhook={self.webhook_id!r} "
            f"attempt={self.attempt} success={self.success}>"
        )
