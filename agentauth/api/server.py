"""
AgentAuth REST API Server.

FastAPI-based HTTP server exposing AgentAuth's capabilities.
Supports agent registration, policy management, and permission evaluation.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import structlog
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agentauth.core.engine import AgentAuthEngine
from agentauth.core.models import (
    Agent,
    AgentScope,
    Permission,
    PermissionDecision,
    Policy,
)
from agentauth.core.store import AgentStore, PolicyStore

logger = structlog.get_logger(__name__)

# ── Global state ────────────────────────────────────────────────────────────

_engine: AgentAuthEngine | None = None
_agent_store = AgentStore()
_policy_store = PolicyStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    global _engine

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is required")

    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    _engine = AgentAuthEngine(api_key=api_key, model=model)
    logger.info("AgentAuth server started", model=model)

    yield

    logger.info("AgentAuth server shutting down")


# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AgentAuth",
    description=(
        "Open-source identity and authentication layer for AI agents. "
        "Powered by Google Gemini. Built by Kibrnet PLC, Addis Ababa, Ethiopia."
    ),
    version="0.1.0",
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


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Check server health."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "agents": str(_agent_store.count),
        "policies": str(_policy_store.count),
    }


# ── Agents ────────────────────────────────────────────────────────────────────

@app.post("/agents", response_model=Agent, status_code=status.HTTP_201_CREATED, tags=["Agents"])
async def register_agent(request: RegisterAgentRequest) -> Agent:
    """Register a new AI agent with AgentAuth."""
    # Validate that all policy_ids exist
    for pid in request.policy_ids:
        if not _policy_store.get(pid):
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
    return _agent_store.register(agent)


@app.get("/agents", response_model=list[Agent], tags=["Agents"])
async def list_agents(owner_id: str) -> list[Agent]:
    """List all agents for an owner."""
    return _agent_store.list_by_owner(owner_id)


@app.get("/agents/{agent_id}", response_model=Agent, tags=["Agents"])
async def get_agent(agent_id: UUID) -> Agent:
    """Fetch an agent by ID."""
    agent = _agent_store.get(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@app.post("/agents/{agent_id}/deactivate", tags=["Agents"])
async def deactivate_agent(agent_id: UUID) -> dict[str, bool]:
    """Deactivate an agent. Deactivated agents cannot request permissions."""
    success = _agent_store.deactivate(agent_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return {"success": True}


# ── Policies ──────────────────────────────────────────────────────────────────

@app.post("/policies", response_model=Policy, status_code=status.HTTP_201_CREATED, tags=["Policies"])
async def create_policy(request: CreatePolicyRequest) -> Policy:
    """Create a new policy with natural language rules."""
    policy = Policy(
        name=request.name,
        rules=request.rules,
        description=request.description,
        metadata=request.metadata,
    )
    return _policy_store.create(policy)


@app.get("/policies", response_model=list[Policy], tags=["Policies"])
async def list_policies() -> list[Policy]:
    """List all policies."""
    return _policy_store.list_all()


@app.get("/policies/{policy_id}", response_model=Policy, tags=["Policies"])
async def get_policy(policy_id: UUID) -> Policy:
    """Fetch a policy by ID."""
    policy = _policy_store.get(policy_id)
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
) -> PermissionDecision:
    """
    Evaluate whether an agent is permitted to perform an action.

    This is the core endpoint of AgentAuth. The agent's requested action
    is evaluated against its assigned policies using Google Gemini.

    Returns a decision of ALLOW, DENY, or ESCALATE with full reasoning.
    """
    if _engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AgentAuth engine not initialized",
        )

    agent = _agent_store.get(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    policies = _policy_store.get_many(agent.policy_ids)

    permission = Permission(
        action=request.action,
        resource=request.resource,
        context=request.context,
    )

    return await _engine.evaluate(agent, policies, permission)


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
