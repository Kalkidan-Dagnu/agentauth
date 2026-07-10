"""Tests for AgentAuth in-memory stores."""

from uuid import uuid4

import pytest

from agentauth.core.models import Agent, AgentScope, Policy
from agentauth.core.store import AgentStore, PolicyStore


class TestAgentStore:
    def setup_method(self):
        self.store = AgentStore()

    def _make_agent(self, name: str = "test-agent", owner: str = "user_1") -> Agent:
        return Agent(name=name, owner_id=owner, scopes=[AgentScope.READ])

    def test_register_and_get(self):
        agent = self._make_agent()
        self.store.register(agent)
        fetched = self.store.get(agent.id)
        assert fetched is not None
        assert fetched.name == agent.name

    def test_get_nonexistent_returns_none(self):
        assert self.store.get(uuid4()) is None

    def test_get_by_name(self):
        agent = self._make_agent(name="unique-bot", owner="owner_xyz")
        self.store.register(agent)
        found = self.store.get_by_name("unique-bot", "owner_xyz")
        assert found is not None
        assert found.id == agent.id

    def test_get_by_name_wrong_owner(self):
        agent = self._make_agent(name="my-bot", owner="owner_1")
        self.store.register(agent)
        assert self.store.get_by_name("my-bot", "owner_2") is None

    def test_list_by_owner(self):
        agent1 = self._make_agent(name="bot-1", owner="alice")
        agent2 = self._make_agent(name="bot-2", owner="alice")
        agent3 = self._make_agent(name="bot-3", owner="bob")
        self.store.register(agent1)
        self.store.register(agent2)
        self.store.register(agent3)
        alice_agents = self.store.list_by_owner("alice")
        assert len(alice_agents) == 2

    def test_deactivate_agent(self):
        agent = self._make_agent()
        self.store.register(agent)
        self.store.deactivate(agent.id)
        fetched = self.store.get(agent.id)
        assert fetched.is_active is False

    def test_deactivate_nonexistent_returns_false(self):
        assert self.store.deactivate(uuid4()) is False

    def test_delete_agent(self):
        agent = self._make_agent()
        self.store.register(agent)
        self.store.delete(agent.id)
        assert self.store.get(agent.id) is None

    def test_count(self):
        assert self.store.count == 0
        self.store.register(self._make_agent("a"))
        self.store.register(self._make_agent("b"))
        assert self.store.count == 2


class TestPolicyStore:
    def setup_method(self):
        self.store = PolicyStore()

    def _make_policy(self, name: str = "test-policy") -> Policy:
        return Policy(name=name, rules=["Allow all read operations"])

    def test_create_and_get(self):
        policy = self._make_policy()
        self.store.create(policy)
        fetched = self.store.get(policy.id)
        assert fetched is not None
        assert fetched.name == policy.name

    def test_get_nonexistent_returns_none(self):
        assert self.store.get(uuid4()) is None

    def test_get_many(self):
        p1 = self._make_policy("p1")
        p2 = self._make_policy("p2")
        p3 = self._make_policy("p3")
        self.store.create(p1)
        self.store.create(p2)
        self.store.create(p3)
        fetched = self.store.get_many([p1.id, p3.id])
        assert len(fetched) == 2
        ids = [p.id for p in fetched]
        assert p1.id in ids
        assert p3.id in ids

    def test_list_all(self):
        self.store.create(self._make_policy("a"))
        self.store.create(self._make_policy("b"))
        assert len(self.store.list_all()) == 2

    def test_delete_policy(self):
        policy = self._make_policy()
        self.store.create(policy)
        self.store.delete(policy.id)
        assert self.store.get(policy.id) is None

    def test_count(self):
        assert self.store.count == 0
        self.store.create(self._make_policy())
        assert self.store.count == 1
