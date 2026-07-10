"""Tests for AgentAuth core data models."""

from uuid import uuid4

import pytest

from agentauth.core.models import (
    Agent,
    AgentScope,
    ConfidenceLevel,
    DecisionResult,
    Permission,
    PermissionDecision,
    Policy,
)


class TestPolicy:
    def test_create_policy_with_rules(self):
        policy = Policy(
            name="trading-policy",
            rules=["Agent may only trade during market hours"],
        )
        assert policy.name == "trading-policy"
        assert len(policy.rules) == 1
        assert policy.id is not None

    def test_policy_requires_at_least_one_rule(self):
        with pytest.raises(Exception):
            Policy(name="empty-policy", rules=[])

    def test_policy_has_auto_timestamps(self):
        policy = Policy(name="test", rules=["rule 1"])
        assert policy.created_at is not None
        assert policy.updated_at is not None


class TestAgent:
    def test_create_agent(self):
        agent = Agent(
            name="trading-bot",
            owner_id="user_123",
            scopes=[AgentScope.EXECUTE],
        )
        assert agent.name == "trading-bot"
        assert agent.owner_id == "user_123"
        assert agent.is_active is True

    def test_agent_is_active_by_default(self):
        agent = Agent(name="bot", owner_id="user_1")
        assert agent.is_active is True

    def test_agent_with_multiple_scopes(self):
        agent = Agent(
            name="bot",
            owner_id="user_1",
            scopes=[AgentScope.READ, AgentScope.WRITE],
        )
        assert len(agent.scopes) == 2

    def test_agent_with_policy_ids(self):
        pid = uuid4()
        agent = Agent(name="bot", owner_id="user_1", policy_ids=[pid])
        assert pid in agent.policy_ids


class TestPermission:
    def test_permission_as_natural_language_with_context(self):
        perm = Permission(
            action="execute_trade",
            resource="binance_spot",
            context={"amount": 500, "symbol": "BTCUSDT"},
        )
        nl = perm.as_natural_language
        assert "execute_trade" in nl
        assert "binance_spot" in nl
        assert "amount=500" in nl

    def test_permission_as_natural_language_no_context(self):
        perm = Permission(action="read_data", resource="user_profile")
        nl = perm.as_natural_language
        assert "read_data" in nl
        assert "user_profile" in nl
        assert "context" not in nl


class TestPermissionDecision:
    def test_allow_decision(self):
        agent_id = uuid4()
        perm = Permission(action="read", resource="database")
        decision = PermissionDecision(
            agent_id=agent_id,
            permission=perm,
            result=DecisionResult.ALLOW,
            reason="Action complies with all policies",
            confidence=ConfidenceLevel.HIGH,
        )
        assert decision.result == DecisionResult.ALLOW
        assert decision.confidence == ConfidenceLevel.HIGH

    def test_deny_decision(self):
        agent_id = uuid4()
        perm = Permission(action="delete", resource="production_db")
        decision = PermissionDecision(
            agent_id=agent_id,
            permission=perm,
            result=DecisionResult.DENY,
            reason="Agent is not authorized to delete production resources",
            confidence=ConfidenceLevel.HIGH,
        )
        assert decision.result == DecisionResult.DENY

    def test_decision_has_request_id(self):
        agent_id = uuid4()
        perm = Permission(action="read", resource="logs")
        decision = PermissionDecision(
            agent_id=agent_id,
            permission=perm,
            result=DecisionResult.ALLOW,
            reason="Permitted",
            confidence=ConfidenceLevel.HIGH,
        )
        assert decision.request_id is not None
