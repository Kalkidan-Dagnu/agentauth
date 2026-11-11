"""
AgentAuth Python SDK Client.

High-level client for interacting with the AgentAuth server.
Designed to be simple enough to integrate in minutes.

Usage:
    from agentauth.sdk.client import AgentAuthClient

    client = AgentAuthClient(base_url="http://localhost:8000")

    # Register an agent
    agent = client.agents.register(
        name="my-trading-agent",
        owner_id="user_123",
        scopes=["execute"],
        policy_ids=["policy-uuid-here"],
    )

    # Check permission
    decision = client.permissions.evaluate(
        agent_id=agent.id,
        action="execute_trade",
        resource="binance_spot",
        context={"amount": 500, "symbol": "BTCUSDT"},
    )

    if decision.result == "ALLOW":
        # proceed with the trade
        pass
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from agentauth.core.models import (
    Agent,
    AgentScope,
    Permission,
    PermissionDecision,
    Policy,
)


class AgentsResource:
    """SDK resource for managing agents."""

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def register(
        self,
        name: str,
        owner_id: str,
        scopes: list[str] | None = None,
        policy_ids: list[str] | None = None,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Agent:
        """Register a new agent with AgentAuth."""
        response = self._http.post(
            "/agents",
            json={
                "name": name,
                "owner_id": owner_id,
                "scopes": scopes or [],
                "policy_ids": policy_ids or [],
                "description": description,
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return Agent(**response.json())

    def get(self, agent_id: str | UUID) -> Agent:
        """Fetch an agent by ID."""
        response = self._http.get(f"/agents/{agent_id}")
        response.raise_for_status()
        return Agent(**response.json())

    def list(self, owner_id: str) -> list[Agent]:
        """List all agents for an owner."""
        response = self._http.get("/agents", params={"owner_id": owner_id})
        response.raise_for_status()
        return [Agent(**a) for a in response.json()]

    def deactivate(self, agent_id: str | UUID) -> bool:
        """Deactivate an agent (it can no longer request permissions)."""
        response = self._http.post(f"/agents/{agent_id}/deactivate")
        response.raise_for_status()
        return response.json().get("success", False)


class PoliciesResource:
    """SDK resource for managing policies."""

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def create(
        self,
        name: str,
        rules: list[str],
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Policy:
        """Create a new policy with natural language rules."""
        response = self._http.post(
            "/policies",
            json={
                "name": name,
                "rules": rules,
                "description": description,
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return Policy(**response.json())

    def get(self, policy_id: str | UUID) -> Policy:
        """Fetch a policy by ID."""
        response = self._http.get(f"/policies/{policy_id}")
        response.raise_for_status()
        return Policy(**response.json())

    def list(self) -> list[Policy]:
        """List all policies."""
        response = self._http.get("/policies")
        response.raise_for_status()
        return [Policy(**p) for p in response.json()]

    def create_from_template(
        self,
        template_name: str,
        policy_name: str,
        description: str = "",
        overrides: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Policy:
        """
        Create a policy from a pre-built NBE regulatory template.

        Templates provide a production-ready, NBE-compliant rule set as the
        base. Use ``overrides`` to append additional rules specific to your
        deployment without losing the regulatory baseline.

        Args:
            template_name: Template identifier, e.g. ``"nbe_payment_agent"``.
                           Call ``client.policies.list_templates()`` to see
                           all available templates.
            policy_name:   Name for the resulting policy.
            description:   Optional description. Defaults to the template
                           description if not provided.
            overrides:     Additional rules appended after the template's
                           base rules.
            metadata:      Extra key-value metadata stored on the policy.

        Returns:
            The created Policy with the template's rules (plus any overrides).

        Example::

            policy = client.policies.create_from_template(
                template_name="nbe_payment_agent",
                policy_name="telebirr-payment-policy",
                overrides=[
                    "Agent may not process payments above ETB 10,000 "
                    "without supervisor approval"
                ],
            )
        """
        response = self._http.post(
            "/policies/from-template",
            json={
                "template_name": template_name,
                "policy_name": policy_name,
                "description": description,
                "overrides": overrides or [],
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return Policy(**response.json())

    def list_templates(
        self,
        regulator: str | None = None,
        tag: str | None = None,
    ) -> list[dict]:
        """
        List all available policy templates.

        Args:
            regulator: Filter by regulator, e.g. ``"NBE"``.
            tag:       Filter by topic tag, e.g. ``"payment"``.

        Returns:
            List of template metadata dicts (name, display_name, description,
            rules, references, etc.).
        """
        params: dict[str, str] = {}
        if regulator:
            params["regulator"] = regulator
        if tag:
            params["tag"] = tag
        response = self._http.get("/templates", params=params)
        response.raise_for_status()
        return response.json()

    def get_template(self, template_name: str) -> dict:
        """
        Get a single policy template by name.

        Args:
            template_name: e.g. ``"nbe_mobile_banking"``

        Returns:
            Template metadata dict including the full rule set.
        """
        response = self._http.get(f"/templates/{template_name}")
        response.raise_for_status()
        return response.json()


class PermissionsResource:
    """SDK resource for evaluating permissions."""

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def evaluate(
        self,
        agent_id: str | UUID,
        action: str,
        resource: str,
        context: dict[str, Any] | None = None,
    ) -> PermissionDecision:
        """
        Evaluate whether an agent is permitted to perform an action.

        This is the core method of AgentAuth. Call this before any
        sensitive agent operation.

        Args:
            agent_id: The ID of the agent requesting the action.
            action: What the agent wants to do (e.g., "execute_trade").
            resource: The resource being acted upon (e.g., "binance_spot").
            context: Additional context for the evaluation.

        Returns:
            PermissionDecision with result ALLOW, DENY, or ESCALATE.
        """
        response = self._http.post(
            f"/agents/{agent_id}/evaluate",
            json={
                "action": action,
                "resource": resource,
                "context": context or {},
            },
        )
        response.raise_for_status()
        return PermissionDecision(**response.json())

    def is_allowed(
        self,
        agent_id: str | UUID,
        action: str,
        resource: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """
        Convenience method — returns True if action is ALLOW, False otherwise.
        Use this for simple allow/deny checks without needing the full decision.
        """
        decision = self.evaluate(agent_id, action, resource, context)
        return decision.result == "ALLOW"


class AgentAuthClient:
    """
    The AgentAuth Python SDK client.

    Provides a clean, resource-based interface to the AgentAuth server.
    Handles HTTP connections, authentication, and response parsing.

    Args:
        base_url: The AgentAuth server URL (e.g., "http://localhost:8000").
        api_key: Optional API key for authenticated requests.
        timeout: HTTP timeout in seconds. Default 30.

    Example:
        client = AgentAuthClient(base_url="http://localhost:8000")

        # Create a policy
        policy = client.policies.create(
            name="safe-trading",
            rules=[
                "Only execute trades during market hours",
                "Maximum single trade value is $5,000",
            ]
        )

        # Register an agent
        agent = client.agents.register(
            name="trading-bot",
            owner_id="user_abc",
            scopes=["execute"],
            policy_ids=[str(policy.id)],
        )

        # Evaluate permission before acting
        if client.permissions.is_allowed(agent.id, "buy", "BTCUSDT", {"amount": 200}):
            print("Trade approved!")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
        )

        self.agents = AgentsResource(self._http)
        self.policies = PoliciesResource(self._http)
        self.permissions = PermissionsResource(self._http)

    def health(self) -> dict[str, str]:
        """Check AgentAuth server health."""
        response = self._http.get("/health")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Close the HTTP connection."""
        self._http.close()

    def __enter__(self) -> AgentAuthClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
