# AgentAuthEngine is imported lazily to avoid pulling in google.generativeai
# at import time — that would break environments where it's not installed
# (e.g. when running with REASONING_BACKEND=gemma).
from agentauth.core.models import (
    Agent,
    AgentIdentity,
    AgentScope,
    ConfidenceLevel,
    DecisionResult,
    Permission,
    PermissionDecision,
    Policy,
)

__all__ = [
    "AgentAuthEngine",
    "Agent",
    "AgentIdentity",
    "AgentScope",
    "ConfidenceLevel",
    "DecisionResult",
    "Permission",
    "PermissionDecision",
    "Policy",
]


def __getattr__(name: str):
    if name == "AgentAuthEngine":
        from agentauth.core.engine import AgentAuthEngine
        return AgentAuthEngine
    raise AttributeError(f"module 'agentauth.core' has no attribute {name!r}")
