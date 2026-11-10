"""
Webhook dispatcher for AgentAuth.

Delivers PermissionDecision payloads to registered webhook URLs.

Delivery contract:
  - Called as a FastAPI BackgroundTask after every /evaluate response
  - Filters webhooks by their subscribed events (e.g. only ESCALATE)
  - Makes up to MAX_ATTEMPTS HTTP POST requests per webhook
  - Backoff between retries: 5s → 25s → 125s (base 5, exponential)
  - Each attempt is logged to the webhook_deliveries table
  - A 2xx response is considered success; anything else triggers a retry
  - Network/timeout errors also trigger a retry
  - Deactivated webhooks are skipped silently

Payload format (WebhookPayload):
    {
        "event": "ESCALATE",
        "agent_id": "<uuid>",
        "decision": { ...full PermissionDecision... },
        "delivered_at": "2026-11-10T16:30:00Z"
    }

Signature (when webhook.secret is set):
    X-AgentAuth-Signature: sha256=<hex>
    where <hex> is HMAC-SHA256(secret, raw_body_bytes)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import structlog

from agentauth.core.models import (
    PermissionDecision,
    Webhook,
    WebhookDelivery,
    WebhookEvent,
    WebhookPayload,
)
from agentauth.db.session import get_session_factory

logger = structlog.get_logger(__name__)

MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 5          # delays: 5s, 25s, 125s
_REQUEST_TIMEOUT_SECONDS = 10.0
_MAX_RESPONSE_BODY_BYTES = 1024    # store first 1 KB of response


def _should_deliver(webhook: Webhook, decision: PermissionDecision) -> bool:
    """
    Return True if this webhook should receive this decision.

    An empty events list means "subscribe to everything".
    Otherwise the decision result must be in the subscribed events.
    """
    if not webhook.is_active:
        return False
    if not webhook.events:
        return True
    return WebhookEvent(decision.result.value) in webhook.events


def _build_signature(secret: str, body: bytes) -> str:
    """Return sha256=<hex> HMAC signature of ``body`` using ``secret``."""
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


async def _attempt_delivery(
    client: httpx.AsyncClient,
    webhook: Webhook,
    payload: WebhookPayload,
    attempt: int,
) -> WebhookDelivery:
    """
    Make a single HTTP POST to the webhook URL.

    Returns a WebhookDelivery recording the outcome (success or failure).
    Does NOT raise — all errors are captured into the delivery record.
    """
    body = payload.model_dump_json().encode("utf-8")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "AgentAuth-Webhook/0.3.0",
        "X-AgentAuth-Event": payload.event.value,
        "X-AgentAuth-Request-Id": str(payload.decision.request_id),
    }
    if webhook.secret:
        headers["X-AgentAuth-Signature"] = _build_signature(webhook.secret, body)

    delivery = WebhookDelivery(
        id=uuid4(),
        webhook_id=webhook.id,
        request_id=payload.decision.request_id,
        attempt=attempt,
        delivered_at=datetime.now(timezone.utc),
    )

    try:
        response = await client.post(
            webhook.url,
            content=body,
            headers=headers,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        delivery.http_status = response.status_code
        delivery.response_body = response.text[:_MAX_RESPONSE_BODY_BYTES]
        delivery.success = 200 <= response.status_code < 300

        log = logger.bind(
            webhook_id=str(webhook.id),
            url=webhook.url,
            attempt=attempt,
            status=response.status_code,
            success=delivery.success,
        )
        if delivery.success:
            log.info("Webhook delivered successfully")
        else:
            log.warning("Webhook delivery failed — non-2xx response")

    except httpx.TimeoutException as exc:
        delivery.error_message = f"Timeout: {exc}"
        logger.warning(
            "Webhook delivery timed out",
            webhook_id=str(webhook.id),
            attempt=attempt,
            error=str(exc),
        )
    except httpx.RequestError as exc:
        delivery.error_message = f"Request error: {exc}"
        logger.warning(
            "Webhook delivery request error",
            webhook_id=str(webhook.id),
            attempt=attempt,
            error=str(exc),
        )

    return delivery


async def _deliver_with_retry(
    webhook: Webhook,
    payload: WebhookPayload,
) -> None:
    """
    Deliver ``payload`` to ``webhook.url`` with up to MAX_ATTEMPTS attempts.

    Opens its own DB session (independent of the request session) so it can
    run safely inside a BackgroundTask after the request session is closed.

    Backoff: attempt 1 fires immediately; delays before attempts 2 and 3
    are ``_BACKOFF_BASE_SECONDS ** attempt`` seconds (5s, 25s).
    """
    from agentauth.db.stores import webhook_store

    session_factory = get_session_factory()

    async with httpx.AsyncClient() as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if attempt > 1:
                delay = _BACKOFF_BASE_SECONDS ** (attempt - 1)
                logger.info(
                    "Retrying webhook delivery",
                    webhook_id=str(webhook.id),
                    attempt=attempt,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)

            delivery = await _attempt_delivery(client, webhook, payload, attempt)

            # Persist the delivery record in its own session
            async with session_factory() as db:
                try:
                    await webhook_store.record_delivery(db, delivery)
                    await db.commit()
                except Exception as exc:
                    await db.rollback()
                    logger.error(
                        "Failed to persist webhook delivery record",
                        webhook_id=str(webhook.id),
                        error=str(exc),
                    )

            if delivery.success:
                return  # Done — no more retries needed

    logger.error(
        "Webhook delivery exhausted all attempts",
        webhook_id=str(webhook.id),
        url=webhook.url,
        max_attempts=MAX_ATTEMPTS,
    )


async def dispatch_webhooks(
    decision: PermissionDecision,
    agent_id: UUID,
) -> None:
    """
    Entry point called as a FastAPI BackgroundTask after every /evaluate.

    Fetches active webhooks for the agent, filters by subscribed events,
    and fires concurrent deliveries for each matching webhook.

    Args:
        decision:  The PermissionDecision that was just produced.
        agent_id:  The agent's UUID (redundant with decision.agent_id,
                   passed explicitly for clarity at the call site).
    """
    from agentauth.db.stores import webhook_store

    session_factory = get_session_factory()

    # Fetch active webhooks in a fresh session
    async with session_factory() as db:
        try:
            webhooks = await webhook_store.list_for_agent(db, agent_id, active_only=True)
        except Exception as exc:
            logger.error(
                "Failed to fetch webhooks for dispatch",
                agent_id=str(agent_id),
                error=str(exc),
            )
            return

    # Filter to webhooks that subscribe to this decision result
    matching = [w for w in webhooks if _should_deliver(w, decision)]

    if not matching:
        return

    logger.info(
        "Dispatching webhooks",
        agent_id=str(agent_id),
        result=decision.result.value,
        webhook_count=len(matching),
    )

    event = WebhookEvent(decision.result.value)
    payload = WebhookPayload(
        event=event,
        agent_id=agent_id,
        decision=decision,
    )

    # Fire all matching webhooks concurrently; each retries independently
    await asyncio.gather(
        *[_deliver_with_retry(webhook, payload) for webhook in matching],
        return_exceptions=True,  # don't let one failure cancel others
    )
