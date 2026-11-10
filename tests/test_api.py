"""
Tests for AgentAuth REST API endpoints — v0.2.0.

Uses an in-memory SQLite database (via aiosqlite) so no Postgres is needed.
Gemini calls are mocked — only the DB and routing logic are exercised here.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentauth.core.models import (
    Agent,
    AgentScope,
    ConfidenceLevel,
    DecisionResult,
    Permission,
    PermissionDecision,
    Policy,
)
from agentauth.db.models import Base
from agentauth.db.session import get_db

# ── Test database setup ───────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_test_session_factory = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


async def _override_get_db():
    async with _test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    """Ensure required env vars are set for every test."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-that-is-long-enough-32ch")


@pytest_asyncio.fixture
async def db_session():
    """Create all tables and yield a clean session per test; drop all after."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _test_session_factory() as session:
        yield session
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def mock_engine():
    """Return a mock AgentAuthEngine."""
    with patch("agentauth.api.server.AgentAuthEngine") as mock_cls:
        mock = AsyncMock()
        mock_cls.return_value = mock
        yield mock


@pytest_asyncio.fixture
async def api_client(db_session, mock_engine):
    """
    Async HTTPX client wired to the FastAPI app with:
      - SQLite in-memory DB (via dependency override)
      - Mocked Gemini engine
      - Tables created fresh per test
    """
    from agentauth.api.server import app

    app.dependency_overrides[get_db] = _override_get_db

    # Patch init_db / close_db so lifespan doesn't try to connect to Postgres
    with patch("agentauth.api.server.init_db", new=AsyncMock()):
        with patch("agentauth.api.server.close_db", new=AsyncMock()):
            # Inject the mock engine
            import agentauth.api.server as srv
            srv._engine = mock_engine

            async with AsyncClient(app=app, base_url="http://test") as client:
                yield client, mock_engine

    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_policy(client: AsyncClient, name: str = "test-policy") -> dict:
    resp = await client.post(
        "/policies",
        json={"name": name, "rules": ["Allow reads", "Deny deletes"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_agent(
    client: AsyncClient,
    name: str = "test-agent",
    owner_id: str = "user_1",
    policy_ids: list[str] | None = None,
) -> dict:
    resp = await client.post(
        "/agents",
        json={
            "name": name,
            "owner_id": owner_id,
            "scopes": ["read"],
            "policy_ids": policy_ids or [],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_allow_decision(agent_id=None) -> PermissionDecision:
    return PermissionDecision(
        agent_id=agent_id or uuid4(),
        permission=Permission(action="read", resource="db"),
        result=DecisionResult.ALLOW,
        reason="Permitted by policy",
        confidence=ConfidenceLevel.HIGH,
    )


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, api_client):
        client, _ = api_client
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        assert resp.json()["version"] == "0.2.0"


# ── Policies ──────────────────────────────────────────────────────────────────

class TestPolicyCRUD:
    @pytest.mark.asyncio
    async def test_create_policy(self, api_client):
        client, _ = api_client
        policy = await _create_policy(client, "trading-policy")
        assert policy["name"] == "trading-policy"
        assert len(policy["rules"]) == 2
        assert "id" in policy

    @pytest.mark.asyncio
    async def test_get_policy(self, api_client):
        client, _ = api_client
        created = await _create_policy(client)
        resp = await client.get(f"/policies/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_policy_404(self, api_client):
        client, _ = api_client
        resp = await client.get(f"/policies/{uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_policies(self, api_client):
        client, _ = api_client
        await _create_policy(client, "p1")
        await _create_policy(client, "p2")
        resp = await client.get("/policies")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ── Agents ────────────────────────────────────────────────────────────────────

class TestAgentCRUD:
    @pytest.mark.asyncio
    async def test_register_agent(self, api_client):
        client, _ = api_client
        policy = await _create_policy(client)
        agent = await _create_agent(client, policy_ids=[policy["id"]])
        assert agent["name"] == "test-agent"
        assert agent["is_active"] is True

    @pytest.mark.asyncio
    async def test_register_agent_nonexistent_policy_404(self, api_client):
        client, _ = api_client
        resp = await client.post(
            "/agents",
            json={"name": "bad", "owner_id": "u1", "policy_ids": [str(uuid4())]},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_agent(self, api_client):
        client, _ = api_client
        agent = await _create_agent(client)
        resp = await client.get(f"/agents/{agent['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == agent["id"]

    @pytest.mark.asyncio
    async def test_list_agents_by_owner(self, api_client):
        client, _ = api_client
        await _create_agent(client, name="a1", owner_id="alice")
        await _create_agent(client, name="a2", owner_id="alice")
        await _create_agent(client, name="b1", owner_id="bob")

        resp = await client.get("/agents", params={"owner_id": "alice"})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_deactivate_agent(self, api_client):
        client, _ = api_client
        agent = await _create_agent(client)
        resp = await client.post(f"/agents/{agent['id']}/deactivate")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        # Verify agent is now inactive
        get_resp = await client.get(f"/agents/{agent['id']}")
        assert get_resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_deactivate_nonexistent_agent_404(self, api_client):
        client, _ = api_client
        resp = await client.post(f"/agents/{uuid4()}/deactivate")
        assert resp.status_code == 404


# ── Token issuance ────────────────────────────────────────────────────────────

class TestTokenIssuance:
    @pytest.mark.asyncio
    async def test_issue_token_returns_jwt(self, api_client):
        client, _ = api_client
        agent = await _create_agent(client)
        resp = await client.post(f"/agents/{agent['id']}/token")
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["token"].count(".") == 2  # valid JWT has 3 parts
        assert data["agent_id"] == agent["id"]

    @pytest.mark.asyncio
    async def test_issue_token_with_custom_expiry(self, api_client):
        client, _ = api_client
        agent = await _create_agent(client)
        resp = await client.post(
            f"/agents/{agent['id']}/token",
            json={"expires_in_hours": 48},
        )
        assert resp.status_code == 200
        assert "token" in resp.json()

    @pytest.mark.asyncio
    async def test_issue_token_nonexistent_agent_404(self, api_client):
        client, _ = api_client
        resp = await client.post(f"/agents/{uuid4()}/token")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_issue_token_deactivated_agent_403(self, api_client):
        client, _ = api_client
        agent = await _create_agent(client)
        await client.post(f"/agents/{agent['id']}/deactivate")
        resp = await client.post(f"/agents/{agent['id']}/token")
        assert resp.status_code == 403


# ── Permission Evaluation ─────────────────────────────────────────────────────

class TestPermissionEvaluation:
    @pytest.mark.asyncio
    async def test_evaluate_allow(self, api_client):
        client, mock_eng = api_client
        agent = await _create_agent(client)
        decision = _make_allow_decision()
        mock_eng.evaluate = AsyncMock(return_value=decision)

        resp = await client.post(
            f"/agents/{agent['id']}/evaluate",
            json={"action": "read", "resource": "database"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "ALLOW"

    @pytest.mark.asyncio
    async def test_evaluate_nonexistent_agent_404(self, api_client):
        client, _ = api_client
        resp = await client.post(
            f"/agents/{uuid4()}/evaluate",
            json={"action": "read", "resource": "db"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_evaluate_with_valid_bearer_token(self, api_client):
        """A valid JWT for the same agent should be accepted."""
        client, mock_eng = api_client
        agent = await _create_agent(client)
        decision = _make_allow_decision()
        mock_eng.evaluate = AsyncMock(return_value=decision)

        # Issue a token
        token_resp = await client.post(f"/agents/{agent['id']}/token")
        token = token_resp.json()["token"]

        resp = await client.post(
            f"/agents/{agent['id']}/evaluate",
            json={"action": "read", "resource": "db"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_evaluate_with_wrong_agent_token_403(self, api_client):
        """A JWT for a different agent should be rejected with 403."""
        client, mock_eng = api_client
        agent_a = await _create_agent(client, name="agent-a")
        agent_b = await _create_agent(client, name="agent-b")

        # Issue token for agent_a but use it on agent_b's endpoint
        token_resp = await client.post(f"/agents/{agent_a['id']}/token")
        token = token_resp.json()["token"]

        resp = await client.post(
            f"/agents/{agent_b['id']}/evaluate",
            json={"action": "read", "resource": "db"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_evaluate_with_invalid_token_401(self, api_client):
        """A malformed token should return 401."""
        client, _ = api_client
        agent = await _create_agent(client)
        resp = await client.post(
            f"/agents/{agent['id']}/evaluate",
            json={"action": "read", "resource": "db"},
            headers={"Authorization": "Bearer not.a.real.token"},
        )
        assert resp.status_code == 401


# ── Audit Log ─────────────────────────────────────────────────────────────────

class TestAuditLog:
    @pytest.mark.asyncio
    async def test_audit_log_records_decisions(self, api_client):
        """Decisions made via /evaluate should appear in /audit."""
        client, mock_eng = api_client
        agent = await _create_agent(client)
        decision = _make_allow_decision()
        mock_eng.evaluate = AsyncMock(return_value=decision)

        # Make two evaluate calls
        for _ in range(2):
            await client.post(
                f"/agents/{agent['id']}/evaluate",
                json={"action": "read", "resource": "db"},
            )

        resp = await client.get(f"/agents/{agent['id']}/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["decisions"]) == 2

    @pytest.mark.asyncio
    async def test_audit_log_pagination(self, api_client):
        """limit and offset params should control the returned slice."""
        client, mock_eng = api_client
        agent = await _create_agent(client)
        mock_eng.evaluate = AsyncMock(return_value=_make_allow_decision())

        for _ in range(5):
            await client.post(
                f"/agents/{agent['id']}/evaluate",
                json={"action": "read", "resource": "db"},
            )

        resp = await client.get(
            f"/agents/{agent['id']}/audit",
            params={"limit": 2, "offset": 0},
        )
        data = resp.json()
        assert data["total"] == 5
        assert len(data["decisions"]) == 2

    @pytest.mark.asyncio
    async def test_audit_log_nonexistent_agent_404(self, api_client):
        client, _ = api_client
        resp = await client.get(f"/agents/{uuid4()}/audit")
        assert resp.status_code == 404
