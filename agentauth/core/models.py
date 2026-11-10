"""
Core data models for AgentAuth.
Defines the building blocks: agents, policies, permissions, and decisions.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentScope(str, Enum):
    """Predefined scopes an agent can be granted."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"
    CUSTOM = "custom"


class DecisionResult(str, Enum):
    """The outcome of a permission evaluation."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"  # Requires human review


class ConfidenceLevel(str, Enum):
    """Gemini's confidence in its decision."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Policy(BaseModel):
    """
    A natural language policy that governs what an agent is allowed to do.

    Example:
        Policy(
            name="trading-policy",
            description="Controls what the trading agent can execute",
            rules=[
                "Agent may execute trades only during market hours (09:00-17:00 EAT)",
                "Agent may not execute single trades above $10,000",
                "Agent must verify KYC status before any transaction",
            ]
        )
    """
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="")
    rules: list[str] = Field(..., min_length=1, description="Natural language policy rules")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"json_encoders": {UUID: str, datetime: lambda v: v.isoformat()}}


class Agent(BaseModel):
    """
    Represents an AI agent registered in AgentAuth.
    An agent has a name, assigned scopes, and one or more policies.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="")
    owner_id: str = Field(..., description="ID of the user or service that owns this agent")
    scopes: list[AgentScope] = Field(default_factory=list)
    policy_ids: list[UUID] = Field(default_factory=list)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"json_encoders": {UUID: str, datetime: lambda v: v.isoformat()}}


class AgentIdentity(BaseModel):
    """
    A signed identity token issued to an agent.
    This is what the agent presents when requesting permissions.
    """
    agent_id: UUID
    agent_name: str
    owner_id: str
    scopes: list[AgentScope]
    policy_ids: list[UUID]
    issued_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    token: str = Field(description="Signed JWT token")

    model_config = {"json_encoders": {UUID: str, datetime: lambda v: v.isoformat()}}


class Permission(BaseModel):
    """
    A permission request made by an agent.
    Describes the action the agent wants to perform.
    """
    action: str = Field(..., description="What the agent wants to do")
    resource: str = Field(..., description="The resource being acted upon")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (e.g., user_id, amount, timestamp)",
    )

    @property
    def as_natural_language(self) -> str:
        """Format the permission request as natural language for Gemini."""
        context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
        return (
            f"Agent requests to perform action: '{self.action}' "
            f"on resource: '{self.resource}'"
            + (f" with context: {context_str}" if context_str else "")
        )


class PermissionDecision(BaseModel):
    """
    The result of evaluating a permission request against policies using Gemini.
    """
    request_id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    permission: Permission
    result: DecisionResult
    reason: str = Field(description="Gemini's explanation for the decision")
    confidence: ConfidenceLevel
    matched_rules: list[str] = Field(
        default_factory=list,
        description="Which policy rules were relevant to this decision",
    )
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: float = Field(default=0.0)

    model_config = {"json_encoders": {UUID: str, datetime: lambda v: v.isoformat()}}


# ── Webhook models ─────────────────────────────────────────────────────────────


class WebhookEvent(str, Enum):
    """
    Decision result values that a webhook can subscribe to.
    Maps directly to DecisionResult — kept separate so the API
    surface is explicit about what can be subscribed to.
    """
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


class Webhook(BaseModel):
    """
    A webhook endpoint registered to an agent.

    When a PermissionDecision is produced whose result is in ``events``,
    AgentAuth will POST the decision payload to ``url``.

    ``events`` defaults to [ESCALATE] — the most common case.
    Set to all three values to receive every decision.

    ``secret`` is an optional shared secret. When set, every delivery
    includes an X-AgentAuth-Signature header (HMAC-SHA256 of the payload)
    so the receiver can verify authenticity.
    """
    id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    url: str = Field(..., description="HTTPS endpoint to deliver payloads to")
    events: list[WebhookEvent] = Field(
        default_factory=lambda: [WebhookEvent.ESCALATE],
        description="Decision result types to deliver. Defaults to [ESCALATE].",
    )
    secret: str | None = Field(
        default=None,
        description="Optional HMAC secret for payload signature verification",
    )
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {UUID: str, datetime: lambda v: v.isoformat()}}


class WebhookDelivery(BaseModel):
    """
    A single HTTP delivery attempt for a webhook.

    One row per attempt — retries produce additional rows — so the
    full retry history is queryable via GET /webhooks/{id}/deliveries.
    """
    id: UUID = Field(default_factory=uuid4)
    webhook_id: UUID
    request_id: UUID = Field(description="The PermissionDecision request_id this delivery is for")
    attempt: int = Field(default=1, ge=1, description="Attempt number (1 = first try)")
    success: bool = Field(default=False)
    http_status: int | None = Field(default=None, description="HTTP response status code")
    response_body: str | None = Field(default=None, description="First 1 KB of response body")
    error_message: str | None = Field(default=None, description="Network/timeout error if any")
    delivered_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {UUID: str, datetime: lambda v: v.isoformat()}}


class WebhookPayload(BaseModel):
    """
    The JSON body POSTed to a registered webhook URL.

    Receivers should verify the X-AgentAuth-Signature header when a
    secret is configured (HMAC-SHA256 hex digest of the raw request body).
    """
    event: WebhookEvent
    agent_id: UUID
    decision: PermissionDecision
    delivered_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {UUID: str, datetime: lambda v: v.isoformat()}}
