"""
Tests for AgentAuth v0.3.0 webhook functionality.

Covers:
  - Webhook CRUD endpoints (register, list, delete)
  - Delivery history endpoint
  - dispatch_webhooks() filtering and concurrent delivery
  - HMAC signature generation
  - Delivery log persistence
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentauth.core.models import (
    Agent,
    AgentScope,
    ConfidenceLevel,
    DecisionResult,
    Permission,
    PermissionDecision,
    Webhook,
    WebhookDelivery,
    WebhookEvent,
    WebhookPayload,
)
from agentauth.db.models import Base
from agentauth.db.session import get_db
from agentauth.webhooks.dispatcher import _build_signature, _should_deliver

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
    with patch("agentauth.api.server.AgentAuthEngine") as mock_cls:
        mock = AsyncMock()
        mock_cls.return_value = mock
        yield mock


@pytest_asyncio.fixture
async def api_client(db_session, mock_engine):
    from agentauth.api.server import app

    app.dependency_overrides[get_db] = _override_get_db

    with patch("agentauth.api.server.init_db", new=AsyncMock()):
        with patch("agentauth.api.server.close_db", new=AsyncMock()):
            import agentauth.api.server as srv
            srv._engine = mock_engine

            async with AsyncClient(app=app, base_url="http://test") as client:
                yield client, mock_engine

    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_agent(client: AsyncClient, name: str = "test-agent") -> dict:
    resp = await client.post(
        "/agents",
        json={"name": name, "owner_id": "user_1", "scopes": ["read"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _register_webhook(
    client: AsyncClient,
    agent_id: str,
    url: str = "https://example.com/hook",
    events: list[str] | None = None,
    secret: str | None = None,
) -> dict:
    body: dict = {"url": url, "events": events or ["ESCALATE"]}
    if secret:
        body["secret"] = secret
    resp = await client.post(f"/agents/{agent_id}/webhooks", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_decision(result: DecisionResult = DecisionResult.ESCALATE) -> PermissionDecision:
    return PermissionDecision(
        agent_id=uuid4(),
        permission=Permission(action="transfer", resource="wallet"),
        result=result,
        reason="Requires human review",
        confidence=ConfidenceLevel.MEDIUM,
    )


# ── Webhook CRUD ──────────────────────────────────────────────────────────────

class TestWebhookCRUD:
    @pytest.mark.asyncio
    async def test_register_webhook_defaults_to_escalate(self, api_client):
        client, _ = api_client
        agent = await _create_agent(client)
        resp = await client.post(
            f"/agents/{agent['id']}/webhooks",
            json={"url": "https://example.com/hook"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://example.com/hook"
        assert data["events"] == ["ESCALATE"]
        assert data["is_active"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_register_webhook_with_all_events(self, api_client):
        client, _ = api_client
        agent = await _create_agent(client)
        wh = await _register_webhook(
            client, agent["id"],
            events=["ALLOW", "DENY", "ESCALATE"],
        )
        assert set(wh["events"]) == {"ALLOW", "DENY", "ESCALATE"}

    @pytest.mark.asyncio
    async def test_register_webhook_with_secret(self, api_client):
        client, _ = api_client
        agent = await _create_agent(client)
        wh = await _register_webhook(client, agent["id"], secret="my-secret")
        # Secret is stored; we confirm the field exists in response
        assert "secret" in wh

    @pytest.mark.asyncio
    async def test_register_webhook_nonexistent_agent_404(self, api_client):
        client, _ = api_client
        resp = await client.post(
            f"/agents/{uuid4()}/webhooks",
            json={"url": "https://example.com/hook"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_webhooks(self, api_client):
        client, _ = api_client
        agent = await _create_agent(client)
        await _register_webhook(client, agent["id"], url="https://a.example.com/h1")
        await _register_webhook(client, agent["id"], url="https://b.example.com/h2")

        resp = await client.get(f"/agents/{agent['id']}/webhooks")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_list_webhooks_nonexistent_agent_404(self, api_client):
        client, _ = api_client
        resp = await client.get(f"/agents/{uuid4()}/webhooks")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_webhook(self, api_client):
        client, _ = api_client
        agent = await _create_agent(client)
        wh = await _register_webhook(client, agent["id"])

        del_resp = await client.delete(f"/webhooks/{wh['id']}")
        assert del_resp.status_code == 204

        # Should no longer appear in list
        list_resp = await client.get(f"/agents/{agent['id']}/webhooks")
        assert len(list_resp.json()) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_webhook_404(self, api_client):
        client, _ = api_client
        resp = await client.delete(f"/webhooks/{uuid4()}")
        assert resp.status_code == 404


# ── Delivery history ──────────────────────────────────────────────────────────

class TestDeliveryHistory:
    @pytest.mark.asyncio
    async def test_get_deliveries_empty(self, api_client):
        client, _ = api_client
        agent = await _create_agent(client)
        wh = await _register_webhook(client, agent["id"])

        resp = await client.get(f"/webhooks/{wh['id']}/deliveries")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["deliveries"] == []

    @pytest.mark.asyncio
    async def test_get_deliveries_nonexistent_webhook_404(self, api_client):
        client, _ = api_client
        resp = await client.get(f"/webhooks/{uuid4()}/deliveries")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_deliveries_recorded_after_evaluate(self, api_client):
        """
        After /evaluate with an ESCALATE result, delivery records should
        appear in GET /webhooks/{id}/deliveries once the background task runs.
        """
        client, mock_eng = api_client

        agent = await _create_agent(client)
        wh = await _register_webhook(client, agent["id"], url="https://example.com/hook")

        escalate_decision = _make_decision(DecisionResult.ESCALATE)
        mock_eng.evaluate = AsyncMock(return_value=escalate_decision)

        # Mock the HTTP call inside dispatcher to avoid real outbound requests
        with patch("agentauth.webhooks.dispatcher.httpx.AsyncClient") as mock_http_cls:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "ok"
            mock_http_instance = AsyncMock()
            mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
            mock_http_instance.__aexit__ = AsyncMock(return_value=False)
            mock_http_instance.post = AsyncMock(return_value=mock_response)
            mock_http_cls.return_value = mock_http_instance

            # Also patch get_session_factory so dispatcher uses our test DB
            with patch(
                "agentauth.webhooks.dispatcher.get_session_factory",
                return_value=_test_session_factory,
            ):
                await client.post(
                    f"/agents/{agent['id']}/evaluate",
                    json={"action": "transfer", "resource": "wallet"},
                )

        # Check delivery was recorded
        resp = await client.get(f"/webhooks/{wh['id']}/deliveries")
        data = resp.json()
        assert data["total"] >= 1
        assert data["deliveries"][0]["success"] is True
        assert data["deliveries"][0]["http_status"] == 200


# ── Dispatcher unit tests ─────────────────────────────────────────────────────

class TestDispatcherLogic:
    def _make_webhook(
        self,
        events: list[WebhookEvent] | None = None,
        is_active: bool = True,
    ) -> Webhook:
        return Webhook(
            agent_id=uuid4(),
            url="https://example.com/hook",
            events=events or [WebhookEvent.ESCALATE],
            is_active=is_active,
        )

    def test_should_deliver_escalate_to_escalate_webhook(self):
        wh = self._make_webhook(events=[WebhookEvent.ESCALATE])
        decision = _make_decision(DecisionResult.ESCALATE)
        assert _should_deliver(wh, decision) is True

    def test_should_not_deliver_allow_to_escalate_only_webhook(self):
        wh = self._make_webhook(events=[WebhookEvent.ESCALATE])
        decision = _make_decision(DecisionResult.ALLOW)
        assert _should_deliver(wh, decision) is False

    def test_should_deliver_all_results_to_all_events_webhook(self):
        wh = self._make_webhook(
            events=[WebhookEvent.ALLOW, WebhookEvent.DENY, WebhookEvent.ESCALATE]
        )
        for result in DecisionResult:
            decision = _make_decision(result)
            assert _should_deliver(wh, decision) is True

    def test_empty_events_matches_everything(self):
        """An empty events list means subscribe to all results."""
        wh = self._make_webhook(events=[])
        for result in DecisionResult:
            assert _should_deliver(wh, _make_decision(result)) is True

    def test_inactive_webhook_never_delivered(self):
        wh = self._make_webhook(
            events=[WebhookEvent.ALLOW, WebhookEvent.DENY, WebhookEvent.ESCALATE],
            is_active=False,
        )
        for result in DecisionResult:
            assert _should_deliver(wh, _make_decision(result)) is False

    def test_build_signature_format(self):
        secret = "my-secret"
        body = b'{"event": "ESCALATE"}'
        sig = _build_signature(secret, body)
        assert sig.startswith("sha256=")
        # Verify the hex is correct
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert sig == f"sha256={expected}"

    def test_build_signature_different_secrets_differ(self):
        body = b'{"event": "ESCALATE"}'
        sig1 = _build_signature("secret-a", body)
        sig2 = _build_signature("secret-b", body)
        assert sig1 != sig2

    @pytest.mark.asyncio
    async def test_dispatch_skips_non_matching_webhooks(self):
        """dispatch_webhooks should not call _deliver_with_retry for non-matching events."""
        decision = _make_decision(DecisionResult.ALLOW)

        # Webhook only listens for ESCALATE — should be skipped
        escalate_only_webhook = self._make_webhook(events=[WebhookEvent.ESCALATE])

        with patch("agentauth.webhooks.dispatcher.get_session_factory") as mock_sf:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = MagicMock(return_value=mock_session)

            with patch("agentauth.webhooks.dispatcher.webhook_store") as mock_store:
                mock_store.list_for_agent = AsyncMock(return_value=[escalate_only_webhook])

                with patch(
                    "agentauth.webhooks.dispatcher._deliver_with_retry",
                    new=AsyncMock(),
                ) as mock_deliver:
                    from agentauth.webhooks.dispatcher import dispatch_webhooks
                    await dispatch_webhooks(decision, decision.agent_id)
                    mock_deliver.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_calls_deliver_for_matching_webhook(self):
        """dispatch_webhooks should call _deliver_with_retry for matching events."""
        decision = _make_decision(DecisionResult.ESCALATE)
        webhook = self._make_webhook(events=[WebhookEvent.ESCALATE])

        with patch("agentauth.webhooks.dispatcher.get_session_factory") as mock_sf:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = MagicMock(return_value=mock_session)

            with patch("agentauth.webhooks.dispatcher.webhook_store") as mock_store:
                mock_store.list_for_agent = AsyncMock(return_value=[webhook])

                with patch(
                    "agentauth.webhooks.dispatcher._deliver_with_retry",
                    new=AsyncMock(),
                ) as mock_deliver:
                    from agentauth.webhooks.dispatcher import dispatch_webhooks
                    await dispatch_webhooks(decision, decision.agent_id)
                    mock_deliver.assert_called_once()
