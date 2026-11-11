"""
Tests for AgentAuth v0.5.0 — Multi-tenant support.

Covers:
  - Organisation CRUD (create, get, slug conflict)
  - API key issuance and auth (X-API-Key header, invalid key, revoked key)
  - Org-scoped data isolation (agents, policies in one org are invisible to another)
  - All existing endpoints require X-API-Key
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentauth.db.models import Base
from agentauth.db.session import get_db

# ── Test database ──────────────────────────────────────────────────────────────

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
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-that-is-32-chars!!")


@pytest_asyncio.fixture
async def db_session():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _test_session_factory() as session:
        yield session
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def mock_engine():
    with patch("agentauth.api.server.AgentAuthEngine"):
        mock = AsyncMock()
        return mock


@pytest_asyncio.fixture
async def api_client(db_session, mock_engine):
    from agentauth.api.server import app
    app.dependency_overrides[get_db] = _override_get_db
    with patch("agentauth.api.server.init_db", new=AsyncMock()):
        with patch("agentauth.api.server.close_db", new=AsyncMock()):
            import agentauth.api.server as srv
            srv._engine = mock_engine
            async with AsyncClient(app=app, base_url="http://test") as client:
                yield client
    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_org(client: AsyncClient, name: str = "Test Org", slug: str = "test-org") -> dict:
    resp = await client.post("/orgs", json={
        "name": name,
        "slug": slug,
        "owner_id": "user_1",
        "description": "Test organisation",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _issue_api_key(client: AsyncClient, org_id: str, name: str = "test-key") -> str:
    resp = await client.post(f"/orgs/{org_id}/api-keys", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["key"]


async def _create_policy(client: AsyncClient, api_key: str, name: str = "p1") -> dict:
    resp = await client.post("/policies", json={
        "name": name,
        "rules": ["Allow all reads"],
    }, headers={"X-API-Key": api_key})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_agent(client: AsyncClient, api_key: str, name: str = "a1", policy_ids: list[str] | None = None) -> dict:
    body: dict = {"name": name, "owner_id": "user_1", "scopes": ["read"]}
    if policy_ids:
        body["policy_ids"] = policy_ids
    resp = await client.post("/agents", json=body, headers={"X-API-Key": api_key})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Organisation CRUD ─────────────────────────────────────────────────────────

class TestOrganisationCRUD:
    @pytest.mark.asyncio
    async def test_create_org(self, api_client):
        client, _ = api_client
        org = await _create_org(client)
        assert org["name"] == "Test Org"
        assert org["slug"] == "test-org"
        assert org["is_active"] is True
        assert "id" in org

    @pytest.mark.asyncio
    async def test_create_org_duplicate_slug_409(self, api_client):
        client, _ = api_client
        await _create_org(client, slug="my-slug")
        resp = await client.post("/orgs", json={
            "name": "Other Org",
            "slug": "my-slug",
            "owner_id": "user_2",
        })
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_get_org_with_api_key(self, api_client):
        client, _ = api_client
        org = await _create_org(client)
        api_key = await _issue_api_key(client, org["id"])
        resp = await client.get(f"/orgs/{org['id']}", headers={"X-API-Key": api_key})
        assert resp.status_code == 200
        assert resp.json()["id"] == org["id"]

    @pytest.mark.asyncio
    async def test_get_org_wrong_api_key_403(self, api_client):
        client, _ = api_client
        org_a = await _create_org(client, name="Org A", slug="org-a")
        org_b = await _create_org(client, name="Org B", slug="org-b")
        key_b = await _issue_api_key(client, org_b["id"])
        # Try to access org A with org B's key
        resp = await client.get(f"/orgs/{org_a['id']}", headers={"X-API-Key": key_b})
        assert resp.status_code == 403


# ── API key auth ──────────────────────────────────────────────────────────────

class TestAPIKeyAuth:
    @pytest.mark.asyncio
    async def test_endpoints_require_api_key(self, api_client):
        """All org-scoped endpoints should return 401 without X-API-Key."""
        client, _ = api_client
        for method, url, body in [
            ("GET", "/agents?owner_id=x", None),
            ("GET", "/policies", None),
            ("POST", "/policies", {"name": "p", "rules": ["r"]}),
            ("POST", "/agents", {"name": "a", "owner_id": "u"}),
        ]:
            resp = await client.request(method, url, json=body)
            assert resp.status_code == 401, f"{method} {url} returned {resp.status_code}, expected 401"

    @pytest.mark.asyncio
    async def test_invalid_api_key_401(self, api_client):
        client, _ = api_client
        resp = await client.get("/policies", headers={"X-API-Key": "aak_invalid"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_non_aak_prefix_401(self, api_client):
        client, _ = api_client
        resp = await client.get("/policies", headers={"X-API-Key": "not_a_valid_key"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_issue_and_use_api_key(self, api_client):
        client, _ = api_client
        org = await _create_org(client)
        key = await _issue_api_key(client, org["id"])
        assert key.startswith("aak_")
        # Use the key
        resp = await client.get("/policies", headers={"X-API-Key": key})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_api_keys(self, api_client):
        client, _ = api_client
        org = await _create_org(client)
        key1 = await _issue_api_key(client, org["id"], "key-1")
        await _issue_api_key(client, org["id"], "key-2")
        resp = await client.get(f"/orgs/{org['id']}/api-keys", headers={"X-API-Key": key1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Plaintext key must NOT be in the listing
        assert "key" not in data[0]
        assert data[0]["key_prefix"] != key1  # only prefix, not full key


# ── Org-scoped data isolation ─────────────────────────────────────────────────

class TestOrgDataIsolation:
    @pytest.mark.asyncio
    async def test_policies_are_isolated(self, api_client):
        """Org A's policies should not be visible to Org B."""
        client, _ = api_client

        org_a = await _create_org(client, name="Org A", slug="org-a")
        org_b = await _create_org(client, name="Org B", slug="org-b")

        key_a = await _issue_api_key(client, org_a["id"])
        key_b = await _issue_api_key(client, org_b["id"])

        # Create policy in org A
        policy_a = await _create_policy(client, key_a, "policy-in-a")

        # Org B should see 0 policies
        resp_b = await client.get("/policies", headers={"X-API-Key": key_b})
        assert resp_b.status_code == 200
        assert len(resp_b.json()) == 0

        # Org A should see 1 policy
        resp_a = await client.get("/policies", headers={"X-API-Key": key_a})
        assert len(resp_a.json()) == 1

    @pytest.mark.asyncio
    async def test_agents_are_isolated(self, api_client):
        """Org A's agents should not be visible to Org B."""
        client, _ = api_client

        org_a = await _create_org(client, name="Org A", slug="org-a")
        org_b = await _create_org(client, name="Org B", slug="org-b")

        key_a = await _issue_api_key(client, org_a["id"])
        key_b = await _issue_api_key(client, org_b["id"])

        # Create agent in org A
        agent_a = await _create_agent(client, key_a, "agent-in-a")

        # Org B should not see org A's agent
        resp = await client.get(f"/agents/{agent_a['id']}", headers={"X-API-Key": key_b})
        assert resp.status_code == 404

        # Org A should see it
        resp = await client.get(f"/agents/{agent_a['id']}", headers={"X-API-Key": key_a})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_agent_cannot_reference_other_org_policy(self, api_client):
        """An agent in org B cannot reference a policy from org A."""
        client, _ = api_client

        org_a = await _create_org(client, name="Org A", slug="org-a")
        org_b = await _create_org(client, name="Org B", slug="org-b")

        key_a = await _issue_api_key(client, org_a["id"])
        key_b = await _issue_api_key(client, org_b["id"])

        policy_a = await _create_policy(client, key_a, "policy-in-a")

        # Try to create agent in org B with org A's policy
        resp = await client.post("/agents", json={
            "name": "agent-b",
            "owner_id": "user_2",
            "policy_ids": [policy_a["id"]],
        }, headers={"X-API-Key": key_b})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_webhooks_are_isolated(self, api_client):
        """Org B cannot see org A's webhooks."""
        client, _ = api_client

        org_a = await _create_org(client, name="Org A", slug="org-a")
        org_b = await _create_org(client, name="Org B", slug="org-b")

        key_a = await _issue_api_key(client, org_a["id"])
        key_b = await _issue_api_key(client, org_b["id"])

        agent_a = await _create_agent(client, key_a, "agent-a")

        # Register webhook in org A
        resp = await client.post(
            f"/agents/{agent_a['id']}/webhooks",
            json={"url": "https://example.com/hook"},
            headers={"X-API-Key": key_a},
        )
        assert resp.status_code == 201
        webhook_id = resp.json()["id"]

        # Org B cannot delete org A's webhook
        resp = await client.delete(f"/webhooks/{webhook_id}", headers={"X-API-Key": key_b})
        assert resp.status_code == 404

        # Org A can delete it
        resp = await client.delete(f"/webhooks/{webhook_id}", headers={"X-API-Key": key_a})
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_create_policy_from_template_org_scoped(self, api_client):
        """Policies created from templates should be org-scoped."""
        client, _ = api_client

        org_a = await _create_org(client, name="Org A", slug="org-a")
        org_b = await _create_org(client, name="Org B", slug="org-b")

        key_a = await _issue_api_key(client, org_a["id"])
        key_b = await _issue_api_key(client, org_b["id"])

        # Create from template in org A
        resp = await client.post("/policies/from-template", json={
            "template_name": "nbe_payment_agent",
            "policy_name": "nbe-payment-a",
        }, headers={"X-API-Key": key_a})
        assert resp.status_code == 201

        # Org B should see 0 policies
        resp_b = await client.get("/policies", headers={"X-API-Key": key_b})
        assert len(resp_b.json()) == 0

        # Org A should see 1
        resp_a = await client.get("/policies", headers={"X-API-Key": key_a})
        assert len(resp_a.json()) == 1


# ── Templates still accessible without auth ──────────────────────────────────

class TestTemplatesNoAuth:
    @pytest.mark.asyncio
    async def test_list_templates_no_key_required(self, api_client):
        client, _ = api_client
        resp = await client.get("/templates")
        assert resp.status_code == 200
        assert len(resp.json()) == 7

    @pytest.mark.asyncio
    async def test_get_template_no_key_required(self, api_client):
        client, _ = api_client
        resp = await client.get("/templates/nbe_kyc_agent")
        assert resp.status_code == 200
