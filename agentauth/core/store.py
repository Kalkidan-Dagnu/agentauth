"""
In-memory store for agents and policies.
In production, replace with a database-backed implementation.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from agentauth.core.models import Agent, Policy

logger = structlog.get_logger(__name__)


class AgentStore:
    """Thread-safe in-memory store for registered agents."""

    def __init__(self) -> None:
        self._agents: dict[UUID, Agent] = {}

    def register(self, agent: Agent) -> Agent:
        self._agents[agent.id] = agent
        logger.info("Agent registered", agent_id=str(agent.id), agent_name=agent.name)
        return agent

    def get(self, agent_id: UUID) -> Agent | None:
        return self._agents.get(agent_id)

    def get_by_name(self, name: str, owner_id: str) -> Agent | None:
        return next(
            (a for a in self._agents.values() if a.name == name and a.owner_id == owner_id),
            None,
        )

    def list_by_owner(self, owner_id: str) -> list[Agent]:
        return [a for a in self._agents.values() if a.owner_id == owner_id]

    def deactivate(self, agent_id: UUID) -> bool:
        agent = self._agents.get(agent_id)
        if agent:
            agent.is_active = False
            logger.info("Agent deactivated", agent_id=str(agent_id))
            return True
        return False

    def delete(self, agent_id: UUID) -> bool:
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info("Agent deleted", agent_id=str(agent_id))
            return True
        return False

    @property
    def count(self) -> int:
        return len(self._agents)


class PolicyStore:
    """Thread-safe in-memory store for policies."""

    def __init__(self) -> None:
        self._policies: dict[UUID, Policy] = {}

    def create(self, policy: Policy) -> Policy:
        self._policies[policy.id] = policy
        logger.info("Policy created", policy_id=str(policy.id), policy_name=policy.name)
        return policy

    def get(self, policy_id: UUID) -> Policy | None:
        return self._policies.get(policy_id)

    def get_many(self, policy_ids: list[UUID]) -> list[Policy]:
        return [self._policies[pid] for pid in policy_ids if pid in self._policies]

    def list_all(self) -> list[Policy]:
        return list(self._policies.values())

    def delete(self, policy_id: UUID) -> bool:
        if policy_id in self._policies:
            del self._policies[policy_id]
            return True
        return False

    @property
    def count(self) -> int:
        return len(self._policies)
