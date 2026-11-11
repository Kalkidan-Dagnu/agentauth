"""
AgentAuth REST API Server — v0.4.0

Changes from v0.3.0:
  - GET  /templates                   — list all available policy templates
  - GET  /templates/{name}            — get a specific template by name
  - POST /policies/from-template      — create a policy from a template (with optional overrides)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import structlog
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agentauth.api.auth import get_token_agent_id, issue_token
from agentauth.core.engine import AgentAuthEngine
from agentauth.core.models import (
    Agent,
    AgentIdentity,
    AgentScope,
    Permission,
    PermissionDecision,
    Policy,
    Webhook,
    WebhookDelivery,
    WebhookEvent,
)
from agentauth.db.session import close_db, get_db, init_db
from agentauth.db.stores import agent_store, audit_log_store, policy_store, webhook_store
from agentauth.templates import PolicyTemplate, registry
from agentauth.webhooks.dispatcher import dispatch_webhooks

logger = structlog.get_logger(__name__)

# ── Global engine (stateless; no DB needed) ───────────────────────────────────

_engine: AgentAuthEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise resources on startup; clean up on shutdown."""
    global _engine

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is required")
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    _engine = AgentAuthEngine(api_key=api_key, model=model)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    await init_db(database_url)

    logger.info("AgentAuth server started", model=model, version="0.4.0")
    yield

    await close_db()
    logger.info("AgentAuth server shutting down")


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AgentAuth",
    description=(
        "Open-source identity and authentication layer for AI agents. "
        "Powered by Google Gemini. Built by Kibrnet PLC, Addis Ababa, Ethiopia."
    ),
    version="0.4.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response schemas ────────────────────────────────────────────────

class RegisterAgentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    owner_id: str
    scopes: list[AgentScope] = Field(default_factory=list)
    policy_ids: list[UUID] = Field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatePolicyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    rules: list[str] = Field(..., min_length=1)
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluatePermissionRequest(BaseModel):
    action: str = Field(..., description="What the agent wants to do")
    resource: str = Field(..., description="The resource being acted upon")
    context: dict[str, Any] = Field(default_factory=dict)


class IssueTokenRequest(BaseModel):
    expires_in_hours: int = Field(default=24, ge=1, le=8760, description="Token lifetime in hours")


class AuditLogResponse(BaseModel):
    total: int
    limit: int
    offset: int
    decisions: list[PermissionDecision]


class RegisterWebhookRequest(BaseModel):
    url: str = Field(..., description="HTTPS endpoint that will receive payloads")
    events: list[WebhookEvent] = Field(
        default_factory=lambda: [WebhookEvent.ESCALATE],
        description="Decision result types to subscribe to. Defaults to [ESCALATE].",
    )
    secret: str | None = Field(
        default=None,
        description="Optional HMAC secret for X-AgentAuth-Signature verification",
    )


class WebhookDeliveryResponse(BaseModel):
    total: int
    limit: int
    offset: int
    deliveries: list[WebhookDelivery]


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Check server health."""
    return {"status": "healthy", "version": "0.4.0"}


# ── Agents ────────────────────────────────────────────────────────────────────

@app.post("/agents", response_model=Agent, status_code=status.HTTP_201_CREATED, tags=["Agents"])
async def register_agent(
    request: RegisterAgentRequest,
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """Register a new AI agent with AgentAuth."""
    for pid in request.policy_ids:
        if not await policy_store.get(db, pid):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Policy {pid} not found",
            )

    agent = Agent(
        name=request.name,
        owner_id=request.owner_id,
        scopes=request.scopes,
        policy_ids=request.policy_ids,
        description=request.description,
        metadata=request.metadata,
    )
    return await agent_store.register(db, agent)


@app.get("/agents", response_model=list[Agent], tags=["Agents"])
async def list_agents(
    owner_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[Agent]:
    """List all agents for an owner."""
    return await agent_store.list_by_owner(db, owner_id)


@app.get("/agents/{agent_id}", response_model=Agent, tags=["Agents"])
async def get_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """Fetch an agent by ID."""
    agent = await agent_store.get(db, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@app.post("/agents/{agent_id}/deactivate", tags=["Agents"])
async def deactivate_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Deactivate an agent. Deactivated agents cannot request permissions."""
    success = await agent_store.deactivate(db, agent_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return {"success": True}


# ── Token issuance ────────────────────────────────────────────────────────────

@app.post(
    "/agents/{agent_id}/token",
    response_model=AgentIdentity,
    tags=["Identity"],
    summary="Issue a signed JWT for an agent",
)
async def issue_agent_token(
    agent_id: UUID,
    request: IssueTokenRequest = IssueTokenRequest(),
    db: AsyncSession = Depends(get_db),
) -> AgentIdentity:
    """
    Issue a signed JWT identity token for an agent.

    The token encodes the agent's ID, name, owner, scopes, and policies.
    Agents can present this token as a Bearer credential on the evaluate endpoint.
    """
    agent = await agent_store.get(db, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if not agent.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot issue token for a deactivated agent",
        )
    return issue_token(agent, expires_in_hours=request.expires_in_hours)


# ── Policies ──────────────────────────────────────────────────────────────────

@app.post(
    "/policies",
    response_model=Policy,
    status_code=status.HTTP_201_CREATED,
    tags=["Policies"],
)
async def create_policy(
    request: CreatePolicyRequest,
    db: AsyncSession = Depends(get_db),
) -> Policy:
    """Create a new policy with natural language rules."""
    policy = Policy(
        name=request.name,
        rules=request.rules,
        description=request.description,
        metadata=request.metadata,
    )
    return await policy_store.create(db, policy)


@app.get("/policies", response_model=list[Policy], tags=["Policies"])
async def list_policies(db: AsyncSession = Depends(get_db)) -> list[Policy]:
    """List all policies."""
    return await policy_store.list_all(db)


@app.get("/policies/{policy_id}", response_model=Policy, tags=["Policies"])
async def get_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Policy:
    """Fetch a policy by ID."""
    policy = await policy_store.get(db, policy_id)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy


# ── Permission Evaluation ─────────────────────────────────────────────────────

@app.post(
    "/agents/{agent_id}/evaluate",
    response_model=PermissionDecision,
    tags=["Permissions"],
)
async def evaluate_permission(
    agent_id: UUID,
    request: EvaluatePermissionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    token_agent_id: UUID | None = Depends(get_token_agent_id),
) -> PermissionDecision:
    """
    Evaluate whether an agent is permitted to perform an action.

    Uses Google Gemini to reason over the agent's natural language policies
    and returns ALLOW, DENY, or ESCALATE with a full explanation.

    If a Bearer JWT is supplied, it must belong to the same agent as the
    path parameter. Every decision is recorded in the audit log. Matching
    webhook subscriptions are fired asynchronously after the response.
    """
    if _engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AgentAuth engine not initialised",
        )

    if token_agent_id is not None and token_agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bearer token does not match the agent_id in the request path",
        )

    agent = await agent_store.get(db, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    policies = await policy_store.get_many(db, agent.policy_ids)

    permission = Permission(
        action=request.action,
        resource=request.resource,
        context=request.context,
    )

    decision = await _engine.evaluate(agent, policies, permission)

    # Persist to audit log
    await audit_log_store.record(db, decision)

    # Fire webhooks in the background — does not block the response
    background_tasks.add_task(dispatch_webhooks, decision, agent_id)

    return decision


# ── Audit Log ─────────────────────────────────────────────────────────────────

@app.get(
    "/agents/{agent_id}/audit",
    response_model=AuditLogResponse,
    tags=["Audit"],
    summary="Query decision history for an agent",
)
async def get_audit_log(
    agent_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AuditLogResponse:
    """Return the audit trail of PermissionDecisions for an agent (most recent first)."""
    agent = await agent_store.get(db, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    total = await audit_log_store.count_for_agent(db, agent_id)
    decisions = await audit_log_store.list_for_agent(db, agent_id, limit=limit, offset=offset)

    return AuditLogResponse(total=total, limit=limit, offset=offset, decisions=decisions)


# ── Webhooks ──────────────────────────────────────────────────────────────────

@app.post(
    "/agents/{agent_id}/webhooks",
    response_model=Webhook,
    status_code=status.HTTP_201_CREATED,
    tags=["Webhooks"],
    summary="Register a webhook for an agent",
)
async def register_webhook(
    agent_id: UUID,
    request: RegisterWebhookRequest,
    db: AsyncSession = Depends(get_db),
) -> Webhook:
    """
    Register a webhook URL to receive PermissionDecision notifications for an agent.

    ``events`` controls which result types trigger delivery (default: ESCALATE only).
    Set ``secret`` to enable HMAC-SHA256 request signing via X-AgentAuth-Signature.
    """
    agent = await agent_store.get(db, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    webhook = Webhook(
        agent_id=agent_id,
        url=request.url,
        events=request.events,
        secret=request.secret,
    )
    return await webhook_store.create(db, webhook)


@app.get(
    "/agents/{agent_id}/webhooks",
    response_model=list[Webhook],
    tags=["Webhooks"],
    summary="List webhooks for an agent",
)
async def list_webhooks(
    agent_id: UUID,
    active_only: bool = Query(default=False, description="Only return active webhooks"),
    db: AsyncSession = Depends(get_db),
) -> list[Webhook]:
    """List all webhook registrations for an agent."""
    agent = await agent_store.get(db, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    return await webhook_store.list_for_agent(db, agent_id, active_only=active_only)


@app.delete(
    "/webhooks/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Webhooks"],
    summary="Delete a webhook",
)
async def delete_webhook(
    webhook_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Permanently delete a webhook and its delivery history.
    Returns 204 No Content on success, 404 if not found.
    """
    deleted = await webhook_store.hard_delete(db, webhook_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")


@app.get(
    "/webhooks/{webhook_id}/deliveries",
    response_model=WebhookDeliveryResponse,
    tags=["Webhooks"],
    summary="Inspect delivery history for a webhook",
)
async def get_webhook_deliveries(
    webhook_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> WebhookDeliveryResponse:
    """
    Return the delivery attempt history for a webhook (most recent first).

    Use this to debug failed deliveries, check retry outcomes, and verify
    your endpoint is receiving payloads correctly.
    """
    webhook = await webhook_store.get(db, webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    total = await webhook_store.count_deliveries(db, webhook_id)
    deliveries = await webhook_store.list_deliveries(db, webhook_id, limit=limit, offset=offset)

    return WebhookDeliveryResponse(total=total, limit=limit, offset=offset, deliveries=deliveries)


# ── Policy Templates ──────────────────────────────────────────────────────────

class CreatePolicyFromTemplateRequest(BaseModel):
    template_name: str = Field(
        ...,
        description="Template name, e.g. 'nbe_payment_agent'. See GET /templates for the full list.",
    )
    policy_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name for the resulting policy.",
    )
    description: str = Field(
        default="",
        description="Optional description. Defaults to the template description.",
    )
    overrides: list[str] = Field(
        default_factory=list,
        description=(
            "Additional rules appended after the template's base rules. "
            "Use these to tighten constraints for your specific deployment."
        ),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.get(
    "/templates",
    tags=["Templates"],
    summary="List all available policy templates",
)
async def list_templates(
    regulator: str | None = Query(default=None, description="Filter by regulator, e.g. 'NBE'"),
    tag: str | None = Query(default=None, description="Filter by tag, e.g. 'payment'"),
) -> list[dict]:
    """
    Return all registered policy templates.

    Templates are pre-built natural language rule sets based on African
    regulatory frameworks. Currently includes 7 NBE Ethiopia templates.

    Use ``regulator`` or ``tag`` query params to filter results.
    """
    if regulator:
        templates = registry.list_by_regulator(regulator)
    elif tag:
        templates = registry.list_by_tag(tag)
    else:
        templates = registry.list_all()

    return [t.to_dict() for t in templates]


@app.get(
    "/templates/{template_name}",
    tags=["Templates"],
    summary="Get a specific policy template by name",
)
async def get_template(template_name: str) -> dict:
    """
    Return a single template by its name (e.g. ``nbe_payment_agent``).

    The response includes the full rule set, regulatory references,
    and metadata. Use ``POST /policies/from-template`` to create a
    policy from this template.
    """
    template = registry.get_by_name(template_name)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Template '{template_name}' not found. "
                f"Call GET /templates to see available templates."
            ),
        )
    return template.to_dict()


@app.post(
    "/policies/from-template",
    response_model=Policy,
    status_code=status.HTTP_201_CREATED,
    tags=["Templates"],
    summary="Create a policy from a template",
)
async def create_policy_from_template(
    request: CreatePolicyFromTemplateRequest,
    db: AsyncSession = Depends(get_db),
) -> Policy:
    """
    Create a new policy using a pre-built NBE policy template as the base.

    The resulting policy is stored exactly like any other policy and can be
    assigned to agents immediately. ``overrides`` are additional rules
    appended after the template's base rules — use them to tighten constraints
    for your specific deployment without losing the regulatory baseline.

    Example:
    ```json
    {
        "template_name": "nbe_payment_agent",
        "policy_name": "my-payment-policy",
        "overrides": [
            "Agent may not process payments above ETB 10,000 without supervisor approval"
        ]
    }
    ```
    """
    template = registry.get_by_name(request.template_name)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Template '{request.template_name}' not found. "
                f"Call GET /templates to see available templates."
            ),
        )

    rules = registry.build_rules(template.name, overrides=request.overrides or None)

    policy = Policy(
        name=request.policy_name,
        description=request.description or template.description,
        rules=rules,
        metadata={
            **request.metadata,
            "template": template.name.value,
            "template_version": template.version,
            "regulator": template.regulator,
            "jurisdiction": template.jurisdiction,
            "override_count": len(request.overrides),
        },
    )
    return await policy_store.create(db, policy)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    """Run the AgentAuth server."""
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()

    uvicorn.run(
        "agentauth.api.server:app",
        host=os.getenv("AGENTAUTH_HOST", "0.0.0.0"),
        port=int(os.getenv("AGENTAUTH_PORT", "8000")),
        reload=os.getenv("AGENTAUTH_DEBUG", "false").lower() == "true",
        log_level="info",
    )


if __name__ == "__main__":
    main()
