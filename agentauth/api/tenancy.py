"""
Multi-tenancy: API key authentication and organisation resolution.

This module provides the FastAPI dependency ``get_current_org`` that:
  1. Reads the ``X-API-Key`` header from the request
  2. Hashes it (SHA-256) and looks up the matching org_api_keys row
  3. Returns the Organisation Pydantic model

Endpoints use ``Depends(get_current_org)`` to get the caller's org, then
all data operations are scoped to that org's ``org_id``.

API key format: ``aak_<32-char-random>``
Sent by clients as ``X-API-Key: aak_<...>`` header.

The plaintext key is never stored — only its SHA-256 hash.
"""

from __future__ import annotations

import hashlib
import secrets
from uuid import UUID, uuid4

import structlog
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentauth.core.models import Organization, OrgApiKey, OrgApiKeyIssuance
from agentauth.db.session import get_db
from agentauth.db.stores import org_api_key_store, organization_store

logger = structlog.get_logger(__name__)

_KEY_PREFIX_STR = "aak_"       # AgentAuth Key
_KEY_RANDOM_LENGTH = 32        # chars of randomness after prefix
_KEY_LOOKUP_PREFIX_LEN = 8     # first 8 chars after prefix, used for DB index


def _generate_api_key() -> str:
    """Generate a new random API key: aak_<32-char-hex>."""
    random_part = secrets.token_hex(_KEY_RANDOM_LENGTH // 2)  # hex → 32 chars
    return f"{_KEY_PREFIX_STR}{random_part}"


def _hash_key(plaintext: str) -> str:
    """Return the SHA-256 hex digest of an API key."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _extract_prefix(plaintext: str) -> str:
    """Return the first 8 chars after the aak_ prefix, for DB indexing."""
    # Remove the aak_ prefix, take first 8 chars of the remainder
    without_prefix = plaintext[len(_KEY_PREFIX_STR):]
    return without_prefix[:_KEY_LOOKUP_PREFIX_LEN]


async def issue_api_key(
    db: AsyncSession,
    org_id: UUID,
    name: str,
) -> OrgApiKeyIssuance:
    """
    Generate, hash, and persist a new API key for an org.

    Returns OrgApiKeyIssuance containing the metadata + the plaintext key.
    The plaintext is only available in this return value — it is never
    retrievable again.

    Args:
        db:     Async session.
        org_id: The org to issue the key for.
        name:   Human-readable label, e.g. "Production".
    """
    plaintext = _generate_api_key()
    key_hash = _hash_key(plaintext)
    key_prefix = _extract_prefix(plaintext)

    api_key = OrgApiKey(
        id=uuid4(),
        org_id=org_id,
        name=name,
        key_prefix=key_prefix,
    )

    await org_api_key_store.create(db, api_key, key_hash)

    return OrgApiKeyIssuance(api_key=api_key, key=plaintext)


async def get_current_org(
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Organization:
    """
    FastAPI dependency that resolves the caller's organisation from the
    X-API-Key header.

    Raises 401 if no key is provided or the key is invalid.
    Raises 403 if the key is valid but the org is deactivated.

    Usage:
        @app.get("/agents")
        async def list_agents(org: Organization = Depends(get_current_org)):
            # org.id is the caller's org — scope all queries to it
            ...
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Validate key format
    if not x_api_key.startswith(_KEY_PREFIX_STR):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    key_hash = _hash_key(x_api_key)
    key_prefix = _extract_prefix(x_api_key)

    # Look up the key in the DB
    result = await org_api_key_store.get_by_prefix_and_hash(db, key_prefix, key_hash)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    api_key, org_id = result

    # Fetch the org
    org = await organization_store.get(db, org_id)
    if org is None or not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organisation not found or deactivated.",
        )

    # Update last_used_at (fire and forget — don't block the request)
    try:
        await org_api_key_store.update_last_used(db, api_key.id)
    except Exception:
        logger.warning("Failed to update API key last_used_at", key_id=str(api_key.id))

    logger.debug(
        "Org authenticated",
        org_id=str(org.id),
        org_name=org.name,
        key_prefix=key_prefix,
    )

    return org
