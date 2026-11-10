"""
AgentAuth REST API Server — v0.2.0

Changes from v0.1.0:
  - All agent/policy state is now persisted to PostgreSQL via SQLAlchemy.
  - POST /agents/{id}/token  — issue a signed JWT for an agent.
  - Evaluate endpoint verifies JWT when a Bearer token is supplied.
  - Every PermissionDecision is written to the audit_log table.
  - GET  /agents/{id}/audit  — query decision history for an agent.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, status
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
)
from agentauth.db.session import close_db, get_db, init_db
from agentauth.db.stores import agent_store, audit_log_store, policy_store

logger = structlog.get_logger(__name__)

# ── Global engine (stateless; no DB needed) ───────────────────────────────────

_engine: AgentAuthEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise resources on startup; clean up on shutdown."""
    global _engine

    # Gemini engine
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is required")
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    _engine = AgentAuthEngine(api_key=api_key, model=model)

    # Database
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    await init_db(database_url)

    logger.info("AgentAuth server started", model=model)
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
    version="0.2.0",
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


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Check server health."""
    return {"status": "healthy", "version": "0.2.0"}


# ── Agents ────────────────────────────────────────────────────────────────────

@app.post("/agents", response_model=Agent, status_code=status.HTTP_201_CREATED, tags=["Agents"])
async def register_agent(
    request: RegisterAgentRequest,
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """Register a new AI agent with AgentAuth."""
    # Validate that all referenced policies exist
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

    The token expires after `expires_in_hours` hours (default 24).
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
    db: AsyncSession = Depends(get_db),
    token_agent_id: UUID | None = Depends(get_token_agent_id),
) -> PermissionDecision:
    """
    Evaluate whether an agent is permitted to perform an action.

    Uses Google Gemini to reason over the agent's natural language policies
    and returns ALLOW, DENY, or ESCALATE with a full explanation.

    If a Bearer JWT is supplied, it must belong to the same agent as the
    path parameter (prevents one agent evaluating on behalf of another).

    Every decision is recorded in the audit log.
    """
    if _engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AgentAuth engine not initialised",
        )

    # If a JWT was presented, verify it matches the path agent_id
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

    # Persist to audit log (task 8)
    await audit_log_store.record(db, decision)

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
    limit: int = Query(default=50, ge=1, le=500, description="Max entries to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
) -> AuditLogResponse:
    """
    Return the audit trail of PermissionDecisions made for an agent.

    Results are ordered by most recent first.  Use `limit` and `offset`
    for pagination.
    """
    agent = await agent_store.get(db, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    total = await audit_log_store.count_for_agent(db, agent_id)
    decisions = await audit_log_store.list_for_agent(db, agent_id, limit=limit, offset=offset)

    return AuditLogResponse(
        total=total,
        limit=limit,
        offset=offset,
        decisions=decisions,
    )


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
