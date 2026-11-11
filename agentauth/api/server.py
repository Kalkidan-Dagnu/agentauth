"""
AgentAuth REST API Server — v0.5.0

Changes from v0.4.0:
  - POST /orgs                         — create an organisation
  - GET  /orgs/{id}                     — get org details
  - POST /orgs/{id}/api-keys            — issue an org API key
  - GET  /orgs/{id}/api-keys            — list org API keys
  - All existing endpoints (agents, policies, webhooks, audit, templates)
    are now scoped to the caller's organisation via X-API-Key header
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
from agentauth.api.tenancy import get_current_org, issue_api_key
from agentauth.core.engine import AgentAuthEngine
from agentauth.core.models import (
    Agent,
    AgentIdentity,
    AgentScope,
    Organization,
    OrgApiKey,
    OrgApiKeyIssuance,
    Permission,
    PermissionDecision,
    Policy,
    Webhook,
    WebhookDelivery,
    WebhookEvent,
)
from agentauth.db.session import close_db, get_db, init_db
from agentauth.db.stores import (
    agent_store,
    audit_log_store,
    org_api_key_store,
    organization_store,
    policy_store,
    webhook_store,
)
from agentauth.templates import registry
from agentauth.webhooks.dispatcher import dispatch_webhooks

logger = structlog.get_logger(__name__)

_engine: AgentAuthEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
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

    logger.info("AgentAuth server started", model=model, version="0.5.0")
    yield
    await close_db()
    logger.info("AgentAuth server shutting down")


app = FastAPI(
    title="AgentAuth",
    description=(
        "Open-source identity and authentication layer for AI agents. "
        "Powered by Google Gemini. Built by Kibrnet PLC, Addis Ababa, Ethiopia."
    ),
    version="0.5.0",
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

class CreateOrgRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100, description="URL-friendly unique identifier")
    description: str = ""
    owner_id: str = Field(..., description="ID of the user creating this org")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Label, e.g. 'Production'")


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
    expires_in_hours: int = Field(default=24, ge=1, le=8760)


class AuditLogResponse(BaseModel):
    total: int
    limit: int
    offset: int
    decisions: list[PermissionDecision]


class RegisterWebhookRequest(BaseModel):
    url: str = Field(..., description="HTTPS endpoint that will receive payloads")
    events: list[WebhookEvent] = Field(default_factory=lambda: [WebhookEvent.ESCALATE])
    secret: str | None = Field(default=None)


class WebhookDeliveryResponse(BaseModel):
    total: int
    limit: int
    offset: int
    deliveries: list[WebhookDelivery]


class CreatePolicyFromTemplateRequest(BaseModel):
    template_name: str = Field(...)
    policy_name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    overrides: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Health (no auth required) ─────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "version": "0.5.0"}


# ── Organisations (no auth — creation is open) ────────────────────────────────

@app.post(
    "/orgs",
    response_model=Organization,
    status_code=status.HTTP_201_CREATED,
    tags=["Organisations"],
    summary="Create a new organisation",
)
async def create_org(
    request: CreateOrgRequest,
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """
    Create a new tenant organisation.

    After creating an org, call POST /orgs/{id}/api-keys to get an API key.
    Use that key as the X-API-Key header for all subsequent requests.
    """
    if await organization_store.slug_exists(db, request.slug):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Organisation with slug '{request.slug}' already exists.",
        )
    org = Organization(
        name=request.name,
        slug=request.slug.lower(),
        description=request.description,
        owner_id=request.owner_id,
        metadata=request.metadata,
    )
    return await organization_store.create(db, org)


@app.get(
    "/orgs/{org_id}",
    response_model=Organization,
    tags=["Organisations"],
    summary="Get organisation details",
)
async def get_org(
    org_id: UUID,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Get details for an organisation. Requires the caller's own API key."""
    if org.id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key does not belong to this organisation.",
        )
    return org


# ── Org API Keys ──────────────────────────────────────────────────────────────

@app.post(
    "/orgs/{org_id}/api-keys",
    response_model=OrgApiKeyIssuance,
    status_code=status.HTTP_201_CREATED,
    tags=["Organisations"],
    summary="Issue a new API key for an organisation",
)
async def create_api_key(
    org_id: UUID,
    request: CreateApiKeyRequest,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> OrgApiKeyIssuance:
    """
    Generate a new API key for the organisation.

    The plaintext key is returned ONLY in this response — store it securely.
    It cannot be retrieved again. Use it as the X-API-Key header.
    """
    if org.id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key does not belong to this organisation.",
        )
    return await issue_api_key(db, org_id, request.name)


@app.get(
    "/orgs/{org_id}/api-keys",
    response_model=list[OrgApiKey],
    tags=["Organisations"],
    summary="List API keys for an organisation",
)
async def list_api_keys(
    org_id: UUID,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> list[OrgApiKey]:
    """List all API keys for the organisation (metadata only — no plaintext keys)."""
    if org.id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key does not belong to this organisation.",
        )
    return await org_api_key_store.list_for_org(db, org_id)


# ── Agents (org-scoped) ───────────────────────────────────────────────────────

@app.post("/agents", response_model=Agent, status_code=status.HTTP_201_CREATED, tags=["Agents"])
async def register_agent(
    request: RegisterAgentRequest,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """Register a new AI agent within the caller's organisation."""
    for pid in request.policy_ids:
        if not await policy_store.get(db, pid, org_id=org.id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Policy {pid} not found in this organisation.",
            )
    agent = Agent(
        name=request.name,
        owner_id=request.owner_id,
        scopes=request.scopes,
        policy_ids=request.policy_ids,
        description=request.description,
        metadata=request.metadata,
    )
    return await agent_store.register(db, agent, org.id)


@app.get("/agents", response_model=list[Agent], tags=["Agents"])
async def list_agents(
    owner_id: str,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> list[Agent]:
    """List all agents for an owner within the caller's organisation."""
    return await agent_store.list_by_owner(db, owner_id, org.id)


@app.get("/agents/{agent_id}", response_model=Agent, tags=["Agents"])
async def get_agent(
    agent_id: UUID,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """Fetch an agent by ID (must belong to the caller's org)."""
    agent = await agent_store.get(db, agent_id, org_id=org.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@app.post("/agents/{agent_id}/deactivate", tags=["Agents"])
async def deactivate_agent(
    agent_id: UUID,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Deactivate an agent (must belong to the caller's org)."""
    success = await agent_store.deactivate(db, agent_id, org_id=org.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return {"success": True}


# ── Token issuance (org-scoped) ───────────────────────────────────────────────

@app.post(
    "/agents/{agent_id}/token",
    response_model=AgentIdentity,
    tags=["Identity"],
    summary="Issue a signed JWT for an agent",
)
async def issue_agent_token(
    agent_id: UUID,
    request: IssueTokenRequest = IssueTokenRequest(),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> AgentIdentity:
    """Issue a signed JWT identity token for an agent."""
    agent = await agent_store.get(db, agent_id, org_id=org.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if not agent.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot issue token for a deactivated agent")
    return issue_token(agent, expires_in_hours=request.expires_in_hours)


# ── Policies (org-scoped) ────────────────────────────────────────────────────

@app.post("/policies", response_model=Policy, status_code=status.HTTP_201_CREATED, tags=["Policies"])
async def create_policy(
    request: CreatePolicyRequest,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> Policy:
    """Create a new policy within the caller's organisation."""
    policy = Policy(
        name=request.name,
        rules=request.rules,
        description=request.description,
        metadata=request.metadata,
    )
    return await policy_store.create(db, policy, org.id)


@app.get("/policies", response_model=list[Policy], tags=["Policies"])
async def list_policies(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> list[Policy]:
    """List all policies in the caller's organisation."""
    return await policy_store.list_all(db, org.id)


@app.get("/policies/{policy_id}", response_model=Policy, tags=["Policies"])
async def get_policy(
    policy_id: UUID,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> Policy:
    """Fetch a policy by ID (must belong to the caller's org)."""
    policy = await policy_store.get(db, policy_id, org_id=org.id)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy


# ── Permission Evaluation (org-scoped) ────────────────────────────────────────

@app.post(
    "/agents/{agent_id}/evaluate",
    response_model=PermissionDecision,
    tags=["Permissions"],
)
async def evaluate_permission(
    agent_id: UUID,
    request: EvaluatePermissionRequest,
    background_tasks: BackgroundTasks,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
    token_agent_id: UUID | None = Depends(get_token_agent_id),
) -> PermissionDecision:
    """Evaluate whether an agent is permitted to perform an action."""
    if _engine is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AgentAuth engine not initialised")

    if token_agent_id is not None and token_agent_id != agent_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bearer token does not match the agent_id in the request path")

    agent = await agent_store.get(db, agent_id, org_id=org.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    policies = await policy_store.get_many(db, agent.policy_ids, org_id=org.id)

    permission = Permission(
        action=request.action,
        resource=request.resource,
        context=request.context,
    )

    decision = await _engine.evaluate(agent, policies, permission)

    # Persist to audit log (org-scoped)
    await audit_log_store.record(db, decision, org.id)

    # Fire webhooks in the background
    background_tasks.add_task(dispatch_webhooks, decision, agent_id)

    return decision


# ── Audit Log (org-scoped) ────────────────────────────────────────────────────

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
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> AuditLogResponse:
    """Return the audit trail for an agent (must belong to the caller's org)."""
    agent = await agent_store.get(db, agent_id, org_id=org.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    total = await audit_log_store.count_for_agent(db, agent_id, org_id=org.id)
    decisions = await audit_log_store.list_for_agent(db, agent_id, org_id=org.id, limit=limit, offset=offset)

    return AuditLogResponse(total=total, limit=limit, offset=offset, decisions=decisions)


# ── Webhooks (org-scoped) ─────────────────────────────────────────────────────

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
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> Webhook:
    """Register a webhook URL for an agent (must belong to the caller's org)."""
    agent = await agent_store.get(db, agent_id, org_id=org.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    webhook = Webhook(
        agent_id=agent_id,
        url=request.url,
        events=request.events,
        secret=request.secret,
    )
    return await webhook_store.create(db, webhook, org.id)


@app.get(
    "/agents/{agent_id}/webhooks",
    response_model=list[Webhook],
    tags=["Webhooks"],
    summary="List webhooks for an agent",
)
async def list_webhooks(
    agent_id: UUID,
    active_only: bool = Query(default=False),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> list[Webhook]:
    """List all webhook registrations for an agent."""
    agent = await agent_store.get(db, agent_id, org_id=org.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    return await webhook_store.list_for_agent(db, agent_id, org_id=org.id, active_only=active_only)


@app.delete(
    "/webhooks/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Webhooks"],
    summary="Delete a webhook",
)
async def delete_webhook(
    webhook_id: UUID,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Permanently delete a webhook (must belong to the caller's org)."""
    deleted = await webhook_store.hard_delete(db, webhook_id, org_id=org.id)
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
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> WebhookDeliveryResponse:
    """Return delivery history for a webhook (must belong to the caller's org)."""
    webhook = await webhook_store.get(db, webhook_id, org_id=org.id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    total = await webhook_store.count_deliveries(db, webhook_id)
    deliveries = await webhook_store.list_deliveries(db, webhook_id, limit=limit, offset=offset)

    return WebhookDeliveryResponse(total=total, limit=limit, offset=offset, deliveries=deliveries)


# ── Policy Templates (no auth — browsing is open) ────────────────────────────

@app.get("/templates", tags=["Templates"], summary="List all available policy templates")
async def list_templates(
    regulator: str | None = Query(default=None),
    tag: str | None = Query(default=None),
) -> list[dict]:
    """Return all registered policy templates."""
    if regulator:
        templates = registry.list_by_regulator(regulator)
    elif tag:
        templates = registry.list_by_tag(tag)
    else:
        templates = registry.list_all()
    return [t.to_dict() for t in templates]


@app.get("/templates/{template_name}", tags=["Templates"], summary="Get a specific template")
async def get_template(template_name: str) -> dict:
    """Return a single template by name."""
    template = registry.get_by_name(template_name)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template '{template_name}' not found.")
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
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> Policy:
    """Create a policy from a pre-built NBE template (org-scoped)."""
    template = registry.get_by_name(request.template_name)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template '{request.template_name}' not found.")

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
    return await policy_store.create(db, policy, org.id)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
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
