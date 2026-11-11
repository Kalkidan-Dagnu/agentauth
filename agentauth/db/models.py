"""
SQLAlchemy ORM models for AgentAuth.

Seven tables:
  - organizations      — tenant organisations
  - org_api_keys       — hashed API keys scoped to an organisation
  - agents             — registered AI agents (org-scoped)
  - policies           — natural language policy definitions (org-scoped)
  - audit_log          — every PermissionDecision ever made (org-scoped)
  - webhooks           — per-agent webhook endpoint registrations (org-scoped)
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
    Org-scoped: every policy belongs to an organisation.
    """

    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
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
    Org-scoped: every agent belongs to an organisation.
    """

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
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
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
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
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
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


class OrganizationRow(Base):
    """
    A tenant organisation. All agents, policies, webhooks, and audit
    log entries are scoped to an organisation — this is the core of
    AgentAuth's multi-tenant data isolation.

    Organisations are created via POST /orgs and authenticate using
    API keys (OrgApiKeyRow) rather than JWT agent tokens.
    """

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True,
        comment="URL-friendly identifier, must be unique across all orgs.",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="ID of the user who created / owns this organisation.",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )

    def __repr__(self) -> str:
        return f"<OrganizationRow id={self.id!r} name={self.name!r} slug={self.slug!r}>"


class OrgApiKeyRow(Base):
    """
    A hashed API key scoped to an organisation.

    The plaintext key is returned only once at creation time (POST /orgs/{id}/api-keys).
    Only the SHA-256 hash is stored — identical to how passwords should be handled.

    Key format: aak_<32-char-random> (aak = AgentAuth Key)
    The full key is sent by clients as ``X-API-Key`` header.
    """

    __tablename__ = "org_api_keys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Human-readable label for this key, e.g. 'Production', 'Staging'.",
    )
    key_prefix: Mapped[str] = mapped_column(
        String(12), nullable=False, index=True,
        comment="First 8 chars of the plaintext key, used for lookup during auth.",
    )
    key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True,
        comment="SHA-256 hex digest of the full plaintext key.",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now
    )

    def __repr__(self) -> str:
        return (
            f"<OrgApiKeyRow id={self.id!r} org={self.org_id!r} "
            f"name={self.name!r} prefix={self.key_prefix!r}>"
        )
