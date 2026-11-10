"""
Database-backed store implementations for AgentAuth.

Replaces the in-memory AgentStore and PolicyStore from core/store.py with
async SQLAlchemy implementations backed by PostgreSQL (or SQLite in tests).

All public methods mirror the interface of the in-memory stores so the
server.py wiring changes are minimal.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentauth.core.models import (
    Agent,
    AgentScope,
    ConfidenceLevel,
    DecisionResult,
    Permission,
    PermissionDecision,
    Policy,
)
from agentauth.db.models import AgentRow, AuditLogRow, PolicyRow

logger = structlog.get_logger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _row_to_policy(row: PolicyRow) -> Policy:
    """Convert an ORM PolicyRow to a Pydantic Policy."""
    return Policy(
        id=UUID(row.id),
        name=row.name,
        description=row.description,
        rules=row.rules,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata=row.metadata_,
    )


def _policy_to_row(policy: Policy) -> PolicyRow:
    """Convert a Pydantic Policy to an ORM PolicyRow."""
    return PolicyRow(
        id=str(policy.id),
        name=policy.name,
        description=policy.description,
        rules=policy.rules,
        metadata_=policy.metadata,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def _row_to_agent(row: AgentRow) -> Agent:
    """Convert an ORM AgentRow to a Pydantic Agent."""
    return Agent(
        id=UUID(row.id),
        name=row.name,
        description=row.description,
        owner_id=row.owner_id,
        scopes=[AgentScope(s) for s in row.scopes],
        policy_ids=[UUID(pid) for pid in row.policy_ids],
        is_active=row.is_active,
        created_at=row.created_at,
        metadata=row.metadata_,
    )


def _agent_to_row(agent: Agent) -> AgentRow:
    """Convert a Pydantic Agent to an ORM AgentRow."""
    return AgentRow(
        id=str(agent.id),
        name=agent.name,
        description=agent.description,
        owner_id=agent.owner_id,
        scopes=[s.value for s in agent.scopes],
        policy_ids=[str(pid) for pid in agent.policy_ids],
        is_active=agent.is_active,
        created_at=agent.created_at,
        metadata_=agent.metadata,
    )


def _decision_to_row(decision: PermissionDecision) -> AuditLogRow:
    """Convert a Pydantic PermissionDecision to an ORM AuditLogRow."""
    return AuditLogRow(
        id=str(decision.request_id),  # reuse request_id as PK for idempotency
        request_id=str(decision.request_id),
        agent_id=str(decision.agent_id),
        action=decision.permission.action,
        resource=decision.permission.resource,
        context=decision.permission.context,
        result=decision.result.value,
        reason=decision.reason,
        confidence=decision.confidence.value,
        matched_rules=decision.matched_rules,
        latency_ms=decision.latency_ms,
        evaluated_at=decision.evaluated_at,
    )


def _row_to_decision(row: AuditLogRow) -> PermissionDecision:
    """Convert an ORM AuditLogRow back to a Pydantic PermissionDecision."""
    return PermissionDecision(
        request_id=UUID(row.request_id),
        agent_id=UUID(row.agent_id),
        permission=Permission(
            action=row.action,
            resource=row.resource,
            context=row.context,
        ),
        result=DecisionResult(row.result),
        reason=row.reason,
        confidence=ConfidenceLevel(row.confidence),
        matched_rules=row.matched_rules,
        latency_ms=row.latency_ms,
        evaluated_at=row.evaluated_at,
    )


# ── DB-backed PolicyStore ──────────────────────────────────────────────────────


class DBPolicyStore:
    """
    Async database-backed policy store.

    Each method accepts an AsyncSession injected via FastAPI's Depends(get_db).
    """

    async def create(self, db: AsyncSession, policy: Policy) -> Policy:
        """Persist a new policy and return it."""
        row = _policy_to_row(policy)
        db.add(row)
        await db.flush()  # assigns DB-generated defaults without full commit
        logger.info("Policy created", policy_id=str(policy.id), name=policy.name)
        return policy

    async def get(self, db: AsyncSession, policy_id: UUID) -> Policy | None:
        """Fetch a policy by ID, or None if not found."""
        result = await db.execute(
            select(PolicyRow).where(PolicyRow.id == str(policy_id))
        )
        row = result.scalar_one_or_none()
        return _row_to_policy(row) if row else None

    async def get_many(self, db: AsyncSession, policy_ids: list[UUID]) -> list[Policy]:
        """Fetch multiple policies by ID, skipping missing ones."""
        if not policy_ids:
            return []
        str_ids = [str(pid) for pid in policy_ids]
        result = await db.execute(
            select(PolicyRow).where(PolicyRow.id.in_(str_ids))
        )
        return [_row_to_policy(row) for row in result.scalars().all()]

    async def list_all(self, db: AsyncSession) -> list[Policy]:
        """Return all policies ordered by creation time."""
        result = await db.execute(
            select(PolicyRow).order_by(PolicyRow.created_at.asc())
        )
        return [_row_to_policy(row) for row in result.scalars().all()]

    async def delete(self, db: AsyncSession, policy_id: UUID) -> bool:
        """Delete a policy. Returns True if deleted, False if not found."""
        result = await db.execute(
            delete(PolicyRow).where(PolicyRow.id == str(policy_id))
        )
        deleted = result.rowcount > 0
        if deleted:
            logger.info("Policy deleted", policy_id=str(policy_id))
        return deleted


# ── DB-backed AgentStore ───────────────────────────────────────────────────────


class DBAgentStore:
    """
    Async database-backed agent store.
    """

    async def register(self, db: AsyncSession, agent: Agent) -> Agent:
        """Persist a new agent and return it."""
        row = _agent_to_row(agent)
        db.add(row)
        await db.flush()
        logger.info("Agent registered", agent_id=str(agent.id), name=agent.name)
        return agent

    async def get(self, db: AsyncSession, agent_id: UUID) -> Agent | None:
        """Fetch an agent by ID, or None if not found."""
        result = await db.execute(
            select(AgentRow).where(AgentRow.id == str(agent_id))
        )
        row = result.scalar_one_or_none()
        return _row_to_agent(row) if row else None

    async def get_by_name(
        self, db: AsyncSession, name: str, owner_id: str
    ) -> Agent | None:
        """Fetch an agent by name + owner, or None if not found."""
        result = await db.execute(
            select(AgentRow).where(
                AgentRow.name == name, AgentRow.owner_id == owner_id
            )
        )
        row = result.scalar_one_or_none()
        return _row_to_agent(row) if row else None

    async def list_by_owner(self, db: AsyncSession, owner_id: str) -> list[Agent]:
        """Return all agents for a given owner."""
        result = await db.execute(
            select(AgentRow)
            .where(AgentRow.owner_id == owner_id)
            .order_by(AgentRow.created_at.asc())
        )
        return [_row_to_agent(row) for row in result.scalars().all()]

    async def deactivate(self, db: AsyncSession, agent_id: UUID) -> bool:
        """Deactivate an agent. Returns True if found and updated."""
        result = await db.execute(
            update(AgentRow)
            .where(AgentRow.id == str(agent_id))
            .values(is_active=False)
        )
        updated = result.rowcount > 0
        if updated:
            logger.info("Agent deactivated", agent_id=str(agent_id))
        return updated

    async def delete(self, db: AsyncSession, agent_id: UUID) -> bool:
        """Delete an agent. Returns True if deleted, False if not found."""
        result = await db.execute(
            delete(AgentRow).where(AgentRow.id == str(agent_id))
        )
        deleted = result.rowcount > 0
        if deleted:
            logger.info("Agent deleted", agent_id=str(agent_id))
        return deleted


# ── DB-backed AuditLogStore ────────────────────────────────────────────────────


class DBAuditLogStore:
    """
    Async database-backed audit log store.
    Writes every PermissionDecision and supports querying by agent.
    """

    async def record(
        self, db: AsyncSession, decision: PermissionDecision
    ) -> None:
        """Persist a PermissionDecision to the audit log."""
        row = _decision_to_row(decision)
        db.add(row)
        await db.flush()
        logger.debug(
            "Audit log entry recorded",
            request_id=str(decision.request_id),
            agent_id=str(decision.agent_id),
            result=decision.result.value,
        )

    async def list_for_agent(
        self,
        db: AsyncSession,
        agent_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PermissionDecision]:
        """
        Return the most recent decisions for a given agent.

        Args:
            agent_id: Filter by agent.
            limit:    Maximum rows to return (default 100, max enforced by caller).
            offset:   Pagination offset.
        """
        result = await db.execute(
            select(AuditLogRow)
            .where(AuditLogRow.agent_id == str(agent_id))
            .order_by(AuditLogRow.evaluated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_row_to_decision(row) for row in result.scalars().all()]

    async def count_for_agent(self, db: AsyncSession, agent_id: UUID) -> int:
        """Return the total number of audit log entries for an agent."""
        from sqlalchemy import func
        result = await db.execute(
            select(func.count()).where(AuditLogRow.agent_id == str(agent_id))
        )
        return result.scalar_one()


# ── Module-level singletons ───────────────────────────────────────────────────
# Instantiated once; all state is in the DB, not in these objects.

agent_store = DBAgentStore()
policy_store = DBPolicyStore()
audit_log_store = DBAuditLogStore()
