"""
JWT-based agent identity tokens for AgentAuth.

Agents are issued signed JWTs via POST /agents/{id}/token.
Those tokens can then be presented on the evaluate endpoint
(Authorization: Bearer <token>) as an alternative to passing agent_id
directly in the URL.

Token structure (claims):
    sub        — agent ID (UUID string)
    name       — agent name
    owner_id   — owner ID
    scopes     — list of scope strings
    policy_ids — list of policy ID strings
    iat        — issued-at (UTC epoch seconds)
    exp        — expiry (UTC epoch seconds)
    iss        — "agentauth"

Signing algorithm: HS256 (HMAC-SHA256) using JWT_SECRET from env.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agentauth.core.models import Agent, AgentIdentity, AgentScope

logger = structlog.get_logger(__name__)

_ALGORITHM = "HS256"
_ISSUER = "agentauth"
_bearer_scheme = HTTPBearer(auto_error=False)


def _get_secret() -> str:
    """Return JWT_SECRET from environment, raising if not set."""
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET environment variable is required for token issuance."
        )
    return secret


def issue_token(agent: Agent, expires_in_hours: int = 24) -> AgentIdentity:
    """
    Issue a signed JWT for an agent.

    Args:
        agent:            The agent to issue the token for.
        expires_in_hours: Token lifetime in hours (default 24).

    Returns:
        AgentIdentity with the signed JWT in the ``token`` field.
    """
    secret = _get_secret()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=expires_in_hours)

    claims: dict[str, Any] = {
        "iss": _ISSUER,
        "sub": str(agent.id),
        "name": agent.name,
        "owner_id": agent.owner_id,
        "scopes": [s.value for s in agent.scopes],
        "policy_ids": [str(pid) for pid in agent.policy_ids],
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    token = jwt.encode(claims, secret, algorithm=_ALGORITHM)

    logger.info(
        "JWT issued",
        agent_id=str(agent.id),
        agent_name=agent.name,
        expires_at=expires_at.isoformat(),
    )

    return AgentIdentity(
        agent_id=agent.id,
        agent_name=agent.name,
        owner_id=agent.owner_id,
        scopes=agent.scopes,
        policy_ids=agent.policy_ids,
        issued_at=now,
        expires_at=expires_at,
        token=token,
    )


def verify_token(token: str) -> dict[str, Any]:
    """
    Verify and decode a JWT.  Raises HTTPException 401 on any failure.

    Args:
        token: Raw JWT string (without "Bearer " prefix).

    Returns:
        Decoded claims dict.
    """
    secret = _get_secret()
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"verify_exp": True},
        )
    except jwt.PyJWTError as exc:
        logger.warning("JWT verification failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims


def agent_id_from_token(claims: dict[str, Any]) -> UUID:
    """Extract the agent UUID from verified claims."""
    return UUID(claims["sub"])


# ── FastAPI dependency ─────────────────────────────────────────────────────────


def get_token_agent_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> UUID | None:
    """
    Optional FastAPI dependency that extracts an agent ID from a Bearer token.

    Returns None if no Authorization header is present (endpoint still works
    with the agent_id path param).  Raises 401 if a token is present but invalid.

    Usage:
        @app.post("/agents/{agent_id}/evaluate")
        async def evaluate(
            agent_id: UUID,
            token_agent_id: UUID | None = Depends(get_token_agent_id),
        ):
            # If a token was supplied, it must match the path agent_id
            if token_agent_id and token_agent_id != agent_id:
                raise HTTPException(403, "Token does not match agent_id in path")
    """
    if credentials is None:
        return None
    claims = verify_token(credentials.credentials)
    return agent_id_from_token(claims)
