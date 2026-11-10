"""
Unit tests for agentauth.api.auth — JWT token issuance and verification.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from agentauth.api.auth import (
    _ALGORITHM,
    _ISSUER,
    agent_id_from_token,
    issue_token,
    verify_token,
)
from agentauth.core.models import Agent, AgentScope

_SECRET = "test-jwt-secret-that-is-32-chars!!"


@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", _SECRET)


def _make_agent(**kwargs) -> Agent:
    defaults = dict(
        name="test-bot",
        owner_id="user_1",
        scopes=[AgentScope.READ, AgentScope.EXECUTE],
        policy_ids=[uuid4(), uuid4()],
    )
    defaults.update(kwargs)
    return Agent(**defaults)


class TestIssueToken:
    def test_returns_agent_identity_with_token(self):
        agent = _make_agent()
        identity = issue_token(agent)
        assert identity.token
        assert identity.agent_id == agent.id
        assert identity.agent_name == agent.name
        assert identity.owner_id == agent.owner_id

    def test_token_is_valid_jwt(self):
        agent = _make_agent()
        identity = issue_token(agent)
        claims = jwt.decode(identity.token, _SECRET, algorithms=[_ALGORITHM])
        assert claims["sub"] == str(agent.id)
        assert claims["iss"] == _ISSUER
        assert claims["name"] == agent.name

    def test_token_contains_scopes_and_policy_ids(self):
        agent = _make_agent()
        identity = issue_token(agent)
        claims = jwt.decode(identity.token, _SECRET, algorithms=[_ALGORITHM])
        assert "read" in claims["scopes"]
        assert "execute" in claims["scopes"]
        assert len(claims["policy_ids"]) == 2

    def test_custom_expiry(self):
        agent = _make_agent()
        identity = issue_token(agent, expires_in_hours=48)
        delta = identity.expires_at - identity.issued_at
        # Allow ±5 seconds tolerance for test execution time
        assert abs(delta.total_seconds() - 48 * 3600) < 5

    def test_default_expiry_is_24h(self):
        agent = _make_agent()
        identity = issue_token(agent)
        delta = identity.expires_at - identity.issued_at
        assert abs(delta.total_seconds() - 24 * 3600) < 5


class TestVerifyToken:
    def test_valid_token_returns_claims(self):
        agent = _make_agent()
        identity = issue_token(agent)
        claims = verify_token(identity.token)
        assert claims["sub"] == str(agent.id)

    def test_expired_token_raises_401(self):
        agent = _make_agent()
        now = datetime.now(timezone.utc)
        claims = {
            "iss": _ISSUER,
            "sub": str(agent.id),
            "name": agent.name,
            "owner_id": agent.owner_id,
            "scopes": [],
            "policy_ids": [],
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),  # already expired
        }
        expired_token = jwt.encode(claims, _SECRET, algorithm=_ALGORITHM)
        with pytest.raises(HTTPException) as exc_info:
            verify_token(expired_token)
        assert exc_info.value.status_code == 401

    def test_wrong_secret_raises_401(self):
        agent = _make_agent()
        identity = issue_token(agent)
        # Token signed with correct secret — try verifying with a different one
        with pytest.raises(HTTPException) as exc_info:
            # Temporarily patch the secret
            import os
            original = os.environ.get("JWT_SECRET")
            os.environ["JWT_SECRET"] = "completely-different-secret-here!"
            try:
                verify_token(identity.token)
            finally:
                if original:
                    os.environ["JWT_SECRET"] = original
        assert exc_info.value.status_code == 401

    def test_malformed_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token("not.a.valid.jwt.token")
        assert exc_info.value.status_code == 401

    def test_garbage_string_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token("totallygarbage")
        assert exc_info.value.status_code == 401


class TestAgentIdFromToken:
    def test_returns_uuid(self):
        agent = _make_agent()
        identity = issue_token(agent)
        claims = verify_token(identity.token)
        extracted_id = agent_id_from_token(claims)
        assert extracted_id == agent.id
