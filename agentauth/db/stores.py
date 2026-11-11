"""
Database-backed store implementations for AgentAuth v0.5.0.

All data operations are org-scoped — writes accept org_id and reads filter
by it. This is the core of multi-tenant data isolation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentauth.core.models import (
    Agent,
    AgentScope,
    ConfidenceLevel,
    DecisionResult,
    Organization,
    OrgApiKey,
    Permission,
    PermissionDecision,
    Policy,
    Webhook,
    WebhookDelivery,
    WebhookEvent,
)
from agentauth.db.models import (
    AgentRow,
    AuditLogRow,
    OrganizationRow,
    OrgApiKeyRow,
    PolicyRow,
    WebhookDeliveryRow,
    WebhookRow,
)

logger = structlog.get_logger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _policy_to_row(policy: Policy, org_id: UUID) -> PolicyRow:
    return PolicyRow(
        id=str(policy.id),
        org_id=str(org_id),
        name=policy.name,
        description=policy.description,
        rules=policy.rules,
        metadata_=policy.metadata,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def _row_to_policy(row: PolicyRow) -> Policy:
    return Policy(
        id=UUID(row.id),
        name=row.name,
        description=row.description,
        rules=row.rules,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata=row.metadata_,
    )


def _agent_to_row(agent: Agent, org_id: UUID) -> AgentRow:
    return AgentRow(
        id=str(agent.id),
        org_id=str(org_id),
        name=agent.name,
        description=agent.description,
        owner_id=agent.owner_id,
        scopes=[s.value for s in agent.scopes],
        policy_ids=[str(pid) for pid in agent.policy_ids],
        is_active=agent.is_active,
        created_at=agent.created_at,
        metadata_=agent.metadata,
    )


def _row_to_agent(row: AgentRow) -> Agent:
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


def _decision_to_row(decision: PermissionDecision, org_id: UUID) -> AuditLogRow:
    return AuditLogRow(
        id=str(decision.request_id),
        request_id=str(decision.request_id),
        org_id=str(org_id),
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


# ── DBPolicyStore (org-scoped) ────────────────────────────────────────────────


class DBPolicyStore:
    async def create(self, db: AsyncSession, policy: Policy, org_id: UUID) -> Policy:
        row = _policy_to_row(policy, org_id)
        db.add(row)
        await db.flush()
        logger.info("Policy created", policy_id=str(policy.id), org_id=str(org_id), name=policy.name)
        return policy

    async def get(self, db: AsyncSession, policy_id: UUID, org_id: UUID | None = None) -> Policy | None:
        stmt = select(PolicyRow).where(PolicyRow.id == str(policy_id))
        if org_id is not None:
            stmt = stmt.where(PolicyRow.org_id == str(org_id))
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return _row_to_policy(row) if row else None

    async def get_many(self, db: AsyncSession, policy_ids: list[UUID], org_id: UUID | None = None) -> list[Policy]:
        if not policy_ids:
            return []
        str_ids = [str(pid) for pid in policy_ids]
        stmt = select(PolicyRow).where(PolicyRow.id.in_(str_ids))
        if org_id is not None:
            stmt = stmt.where(PolicyRow.org_id == str(org_id))
        result = await db.execute(stmt)
        return [_row_to_policy(row) for row in result.scalars().all()]

    async def list_all(self, db: AsyncSession, org_id: UUID) -> list[Policy]:
        result = await db.execute(
            select(PolicyRow)
            .where(PolicyRow.org_id == str(org_id))
            .order_by(PolicyRow.created_at.asc())
        )
        return [_row_to_policy(row) for row in result.scalars().all()]

    async def delete(self, db: AsyncSession, policy_id: UUID, org_id: UUID | None = None) -> bool:
        stmt = delete(PolicyRow).where(PolicyRow.id == str(policy_id))
        if org_id is not None:
            stmt = stmt.where(PolicyRow.org_id == str(org_id))
        result = await db.execute(stmt)
        return result.rowcount > 0


# ── DBAgentStore (org-scoped) ─────────────────────────────────────────────────


class DBAgentStore:
    async def register(self, db: AsyncSession, agent: Agent, org_id: UUID) -> Agent:
        row = _agent_to_row(agent, org_id)
        db.add(row)
        await db.flush()
        logger.info("Agent registered", agent_id=str(agent.id), org_id=str(org_id), name=agent.name)
        return agent

    async def get(self, db: AsyncSession, agent_id: UUID, org_id: UUID | None = None) -> Agent | None:
        stmt = select(AgentRow).where(AgentRow.id == str(agent_id))
        if org_id is not None:
            stmt = stmt.where(AgentRow.org_id == str(org_id))
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return _row_to_agent(row) if row else None

    async def list_by_owner(self, db: AsyncSession, owner_id: str, org_id: UUID) -> list[Agent]:
        result = await db.execute(
            select(AgentRow)
            .where(AgentRow.owner_id == owner_id, AgentRow.org_id == str(org_id))
            .order_by(AgentRow.created_at.asc())
        )
        return [_row_to_agent(row) for row in result.scalars().all()]

    async def deactivate(self, db: AsyncSession, agent_id: UUID, org_id: UUID | None = None) -> bool:
        stmt = update(AgentRow).where(AgentRow.id == str(agent_id)).values(is_active=False)
        if org_id is not None:
            stmt = stmt.where(AgentRow.org_id == str(org_id))
        result = await db.execute(stmt)
        return result.rowcount > 0

    async def delete(self, db: AsyncSession, agent_id: UUID, org_id: UUID | None = None) -> bool:
        stmt = delete(AgentRow).where(AgentRow.id == str(agent_id))
        if org_id is not None:
            stmt = stmt.where(AgentRow.org_id == str(org_id))
        result = await db.execute(stmt)
        return result.rowcount > 0


# ── DBAuditLogStore (org-scoped) ──────────────────────────────────────────────


class DBAuditLogStore:
    async def record(self, db: AsyncSession, decision: PermissionDecision, org_id: UUID) -> None:
        row = _decision_to_row(decision, org_id)
        db.add(row)
        await db.flush()
        logger.debug(
            "Audit log entry recorded",
            request_id=str(decision.request_id),
            org_id=str(org_id),
            agent_id=str(decision.agent_id),
            result=decision.result.value,
        )

    async def list_for_agent(
        self, db: AsyncSession, agent_id: UUID, org_id: UUID | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[PermissionDecision]:
        stmt = select(AuditLogRow).where(AuditLogRow.agent_id == str(agent_id))
        if org_id is not None:
            stmt = stmt.where(AuditLogRow.org_id == str(org_id))
        stmt = stmt.order_by(AuditLogRow.evaluated_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return [_row_to_decision(row) for row in result.scalars().all()]

    async def count_for_agent(self, db: AsyncSession, agent_id: UUID, org_id: UUID | None = None) -> int:
        stmt = select(func.count()).where(AuditLogRow.agent_id == str(agent_id))
        if org_id is not None:
            stmt = stmt.where(AuditLogRow.org_id == str(org_id))
        result = await db.execute(stmt)
        return result.scalar_one()


# ── DBWebhookStore (org-scoped) ───────────────────────────────────────────────


def _row_to_webhook(row: WebhookRow) -> Webhook:
    return Webhook(
        id=UUID(row.id),
        agent_id=UUID(row.agent_id),
        url=row.url,
        events=[WebhookEvent(e) for e in row.events],
        secret=row.secret,
        is_active=row.is_active,
        created_at=row.created_at,
    )


def _row_to_delivery(row: WebhookDeliveryRow) -> WebhookDelivery:
    return WebhookDelivery(
        id=UUID(row.id),
        webhook_id=UUID(row.webhook_id),
        request_id=UUID(row.request_id),
        attempt=row.attempt,
        success=row.success,
        http_status=row.http_status,
        response_body=row.response_body,
        error_message=row.error_message,
        delivered_at=row.delivered_at,
    )


class DBWebhookStore:
    async def create(self, db: AsyncSession, webhook: Webhook, org_id: UUID) -> Webhook:
        row = WebhookRow(
            id=str(webhook.id),
            org_id=str(org_id),
            agent_id=str(webhook.agent_id),
            url=webhook.url,
            events=[e.value for e in webhook.events],
            secret=webhook.secret,
            is_active=webhook.is_active,
            created_at=webhook.created_at,
        )
        db.add(row)
        await db.flush()
        logger.info(
            "Webhook registered",
            webhook_id=str(webhook.id),
            org_id=str(org_id),
            agent_id=str(webhook.agent_id),
            url=webhook.url,
        )
        return webhook

    async def get(self, db: AsyncSession, webhook_id: UUID, org_id: UUID | None = None) -> Webhook | None:
        stmt = select(WebhookRow).where(WebhookRow.id == str(webhook_id))
        if org_id is not None:
            stmt = stmt.where(WebhookRow.org_id == str(org_id))
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return _row_to_webhook(row) if row else None

    async def list_for_agent(
        self, db: AsyncSession, agent_id: UUID, org_id: UUID | None = None,
        active_only: bool = False,
    ) -> list[Webhook]:
        stmt = select(WebhookRow).where(WebhookRow.agent_id == str(agent_id))
        if org_id is not None:
            stmt = stmt.where(WebhookRow.org_id == str(org_id))
        if active_only:
            stmt = stmt.where(WebhookRow.is_active == True)  # noqa: E712
        stmt = stmt.order_by(WebhookRow.created_at.asc())
        result = await db.execute(stmt)
        return [_row_to_webhook(row) for row in result.scalars().all()]

    async def hard_delete(self, db: AsyncSession, webhook_id: UUID, org_id: UUID | None = None) -> bool:
        stmt = delete(WebhookRow).where(WebhookRow.id == str(webhook_id))
        if org_id is not None:
            stmt = stmt.where(WebhookRow.org_id == str(org_id))
        result = await db.execute(stmt)
        return result.rowcount > 0

    async def record_delivery(self, db: AsyncSession, delivery: WebhookDelivery) -> None:
        row = WebhookDeliveryRow(
            id=str(delivery.id),
            webhook_id=str(delivery.webhook_id),
            request_id=str(delivery.request_id),
            attempt=delivery.attempt,
            success=delivery.success,
            http_status=delivery.http_status,
            response_body=delivery.response_body,
            error_message=delivery.error_message,
            delivered_at=delivery.delivered_at,
        )
        db.add(row)
        await db.flush()

    async def list_deliveries(
        self, db: AsyncSession, webhook_id: UUID,
        limit: int = 50, offset: int = 0,
    ) -> list[WebhookDelivery]:
        result = await db.execute(
            select(WebhookDeliveryRow)
            .where(WebhookDeliveryRow.webhook_id == str(webhook_id))
            .order_by(WebhookDeliveryRow.delivered_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_row_to_delivery(row) for row in result.scalars().all()]

    async def count_deliveries(self, db: AsyncSession, webhook_id: UUID) -> int:
        result = await db.execute(
            select(func.count()).where(WebhookDeliveryRow.webhook_id == str(webhook_id))
        )
        return result.scalar_one()


# ── DBOrganizationStore ───────────────────────────────────────────────────────


def _row_to_org(row: OrganizationRow) -> Organization:
    return Organization(
        id=UUID(row.id),
        name=row.name,
        slug=row.slug,
        description=row.description,
        owner_id=row.owner_id,
        is_active=row.is_active,
        created_at=row.created_at,
        metadata=row.metadata_,
    )


class DBOrganizationStore:
    async def create(self, db: AsyncSession, org: Organization) -> Organization:
        row = OrganizationRow(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            description=org.description,
            owner_id=org.owner_id,
            is_active=org.is_active,
            created_at=org.created_at,
            metadata_=org.metadata,
        )
        db.add(row)
        await db.flush()
        logger.info("Organization created", org_id=str(org.id), name=org.name, slug=org.slug)
        return org

    async def get(self, db: AsyncSession, org_id: UUID) -> Organization | None:
        result = await db.execute(
            select(OrganizationRow).where(OrganizationRow.id == str(org_id))
        )
        row = result.scalar_one_or_none()
        return _row_to_org(row) if row else None

    async def get_by_slug(self, db: AsyncSession, slug: str) -> Organization | None:
        result = await db.execute(
            select(OrganizationRow).where(OrganizationRow.slug == slug.lower())
        )
        row = result.scalar_one_or_none()
        return _row_to_org(row) if row else None

    async def slug_exists(self, db: AsyncSession, slug: str) -> bool:
        result = await db.execute(
            select(OrganizationRow.id).where(OrganizationRow.slug == slug.lower())
        )
        return result.scalar_one_or_none() is not None

    async def list_by_owner(self, db: AsyncSession, owner_id: str) -> list[Organization]:
        result = await db.execute(
            select(OrganizationRow)
            .where(OrganizationRow.owner_id == owner_id)
            .order_by(OrganizationRow.created_at.asc())
        )
        return [_row_to_org(row) for row in result.scalars().all()]

    async def deactivate(self, db: AsyncSession, org_id: UUID) -> bool:
        result = await db.execute(
            update(OrganizationRow)
            .where(OrganizationRow.id == str(org_id))
            .values(is_active=False)
        )
        return result.rowcount > 0


# ── DBOrgApiKeyStore ──────────────────────────────────────────────────────────


def _row_to_api_key(row: OrgApiKeyRow) -> OrgApiKey:
    return OrgApiKey(
        id=UUID(row.id),
        org_id=UUID(row.org_id),
        name=row.name,
        key_prefix=row.key_prefix,
        is_active=row.is_active,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
    )


class DBOrgApiKeyStore:
    async def create(self, db: AsyncSession, api_key: OrgApiKey, key_hash: str) -> OrgApiKey:
        row = OrgApiKeyRow(
            id=str(api_key.id),
            org_id=str(api_key.org_id),
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            key_hash=key_hash,
            is_active=api_key.is_active,
            created_at=api_key.created_at,
        )
        db.add(row)
        await db.flush()
        logger.info(
            "Org API key created",
            key_id=str(api_key.id), org_id=str(api_key.org_id),
            name=api_key.name, prefix=api_key.key_prefix,
        )
        return api_key

    async def get_by_prefix_and_hash(
        self, db: AsyncSession, key_prefix: str, key_hash: str
    ) -> tuple[OrgApiKey, UUID] | None:
        result = await db.execute(
            select(OrgApiKeyRow).where(
                OrgApiKeyRow.key_prefix == key_prefix,
                OrgApiKeyRow.key_hash == key_hash,
                OrgApiKeyRow.is_active == True,  # noqa: E712
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return _row_to_api_key(row), UUID(row.org_id)

    async def list_for_org(self, db: AsyncSession, org_id: UUID) -> list[OrgApiKey]:
        result = await db.execute(
            select(OrgApiKeyRow)
            .where(OrgApiKeyRow.org_id == str(org_id))
            .order_by(OrgApiKeyRow.created_at.desc())
        )
        return [_row_to_api_key(row) for row in result.scalars().all()]

    async def deactivate(self, db: AsyncSession, key_id: UUID) -> bool:
        result = await db.execute(
            update(OrgApiKeyRow)
            .where(OrgApiKeyRow.id == str(key_id))
            .values(is_active=False)
        )
        return result.rowcount > 0

    async def update_last_used(self, db: AsyncSession, key_id: UUID) -> None:
        await db.execute(
            update(OrgApiKeyRow)
            .where(OrgApiKeyRow.id == str(key_id))
            .values(last_used_at=datetime.utcnow())
        )


# ── Module-level singletons ───────────────────────────────────────────────────

agent_store = DBAgentStore()
policy_store = DBPolicyStore()
audit_log_store = DBAuditLogStore()
webhook_store = DBWebhookStore()
organization_store = DBOrganizationStore()
org_api_key_store = DBOrgApiKeyStore()
