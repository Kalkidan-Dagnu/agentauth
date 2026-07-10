"""Tests for AgentAuth REST API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agentauth.core.models import (
    Agent,
    AgentScope,
    ConfidenceLevel,
    DecisionResult,
    Permission,
    PermissionDecision,
    Policy,
)


@pytest.fixture
def client():
    """Create a test client with mocked Gemini engine."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        with patch("agentauth.api.server.AgentAuthEngine") as mock_engine_class:
            mock_engine = MagicMock()
            mock_engine_class.return_value = mock_engine

            from agentauth.api import server

            # Reset stores between tests
            server._agent_store._agents.clear()
            server._policy_store._policies.clear()
            server._engine = mock_engine

            with TestClient(server.app, raise_server_exceptions=True) as c:
                yield c, mock_engine


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        c, _ = client
        response = c.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestPolicyEndpoints:
    def test_create_policy(self, client):
        c, _ = client
        response = c.post(
            "/policies",
            json={
                "name": "trading-policy",
                "rules": ["Only trade during market hours", "Max trade $5000"],
                "description": "Controls trading agent",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "trading-policy"
        assert len(data["rules"]) == 2
        assert "id" in data

    def test_get_policy(self, client):
        c, _ = client
        create_resp = c.post(
            "/policies",
            json={"name": "read-policy", "rules": ["Allow all reads"]},
        )
        policy_id = create_resp.json()["id"]

        get_resp = c.get(f"/policies/{policy_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == policy_id

    def test_get_nonexistent_policy_returns_404(self, client):
        c, _ = client
        response = c.get(f"/policies/{uuid4()}")
        assert response.status_code == 404

    def test_list_policies(self, client):
        c, _ = client
        c.post("/policies", json={"name": "policy-1", "rules": ["rule 1"]})
        c.post("/policies", json={"name": "policy-2", "rules": ["rule 2"]})
        response = c.get("/policies")
        assert response.status_code == 200
        assert len(response.json()) >= 2


class TestAgentEndpoints:
    def test_register_agent(self, client):
        c, _ = client
        # First create a policy
        policy_resp = c.post(
            "/policies",
            json={"name": "p1", "rules": ["rule 1"]},
        )
        policy_id = policy_resp.json()["id"]

        response = c.post(
            "/agents",
            json={
                "name": "my-agent",
                "owner_id": "user_123",
                "scopes": ["execute"],
                "policy_ids": [policy_id],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "my-agent"
        assert data["is_active"] is True

    def test_register_agent_with_nonexistent_policy_returns_404(self, client):
        c, _ = client
        response = c.post(
            "/agents",
            json={
                "name": "bad-agent",
                "owner_id": "user_1",
                "policy_ids": [str(uuid4())],
            },
        )
        assert response.status_code == 404

    def test_get_agent(self, client):
        c, _ = client
        create_resp = c.post(
            "/agents", json={"name": "get-test-agent", "owner_id": "user_abc"}
        )
        agent_id = create_resp.json()["id"]

        get_resp = c.get(f"/agents/{agent_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == agent_id

    def test_list_agents_by_owner(self, client):
        c, _ = client
        c.post("/agents", json={"name": "a1", "owner_id": "alice"})
        c.post("/agents", json={"name": "a2", "owner_id": "alice"})
        c.post("/agents", json={"name": "b1", "owner_id": "bob"})

        response = c.get("/agents", params={"owner_id": "alice"})
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_deactivate_agent(self, client):
        c, _ = client
        create_resp = c.post(
            "/agents", json={"name": "deact-test", "owner_id": "user_x"}
        )
        agent_id = create_resp.json()["id"]

        deact_resp = c.post(f"/agents/{agent_id}/deactivate")
        assert deact_resp.status_code == 200
        assert deact_resp.json()["success"] is True

        agent = c.get(f"/agents/{agent_id}").json()
        assert agent["is_active"] is False


class TestPermissionEvaluationEndpoint:
    def test_evaluate_permission_allow(self, client):
        c, mock_engine = client

        # Mock the engine to return ALLOW
        mock_decision = PermissionDecision(
            agent_id=uuid4(),
            permission=Permission(action="read", resource="db"),
            result=DecisionResult.ALLOW,
            reason="Action complies with policy",
            confidence=ConfidenceLevel.HIGH,
        )
        mock_engine.evaluate = AsyncMock(return_value=mock_decision)

        # Create policy and agent
        policy_resp = c.post("/policies", json={"name": "p", "rules": ["allow reads"]})
        policy_id = policy_resp.json()["id"]
        agent_resp = c.post(
            "/agents",
            json={"name": "eval-agent", "owner_id": "u1", "policy_ids": [policy_id]},
        )
        agent_id = agent_resp.json()["id"]

        response = c.post(
            f"/agents/{agent_id}/evaluate",
            json={"action": "read", "resource": "database"},
        )
        assert response.status_code == 200
        assert response.json()["result"] == "ALLOW"

    def test_evaluate_permission_for_nonexistent_agent(self, client):
        c, _ = client
        response = c.post(
            f"/agents/{uuid4()}/evaluate",
            json={"action": "read", "resource": "db"},
        )
        assert response.status_code == 404
