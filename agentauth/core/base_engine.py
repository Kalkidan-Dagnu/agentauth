"""
AgentAuth Base Engine.

Defines the contract that every reasoning backend must satisfy.
Both AgentAuthEngine (Gemini) and GemmaEngine (local Gemma) extend this class.

Having a shared abstract base means the server, tests, and SDK never
depend on which backend is running — they only depend on this interface.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from agentauth.core.models import (
    Agent,
    ConfidenceLevel,
    DecisionResult,
    Permission,
    PermissionDecision,
    Policy,
)

logger = structlog.get_logger(__name__)

# ── Shared prompt template ──────────────────────────────────────────────────
# Both Gemini and Gemma receive the exact same prompt so evaluations are
# comparable between backends.

EVALUATION_PROMPT_TEMPLATE = """
You are AgentAuth, a strict and precise access control engine for AI agents.

Your task is to evaluate whether an AI agent's requested action is permitted
under its assigned policies. You must reason carefully and respond in valid JSON.

## Agent Information
- Agent Name: {agent_name}
- Agent Scopes: {agent_scopes}

## Assigned Policies
{policies_text}

## Requested Action
{permission_request}

## Current Context
- Evaluation Time (UTC): {current_time}
- Additional Context: {additional_context}

## Instructions
1. Read each policy rule carefully.
2. Determine if the requested action complies with ALL applicable rules.
3. If ANY rule is violated, the decision must be DENY.
4. If the request is ambiguous or unclear, use ESCALATE (requires human review).
5. Only use ALLOW if the request clearly complies with all rules.

## Response Format
Respond ONLY with valid JSON in this exact format:
{{
    "decision": "ALLOW" | "DENY" | "ESCALATE",
    "reason": "One clear sentence explaining your decision",
    "confidence": "HIGH" | "MEDIUM" | "LOW",
    "matched_rules": ["rule 1 that was relevant", "rule 2 that was relevant"]
}}

Do not include any text outside the JSON object.
"""


class BaseEngine(ABC):
    """
    Abstract base class for AgentAuth reasoning backends.

    Subclasses must implement ``_generate(prompt)`` which calls the
    underlying model and returns raw text. Everything else — prompt
    construction, JSON parsing, error handling, audit logging — is
    handled here in the base class so both backends behave identically.
    """

    # ── Abstract interface ──────────────────────────────────────────────────

    @abstractmethod
    async def _generate(self, prompt: str) -> str:
        """
        Call the underlying model with ``prompt`` and return raw text.

        Must be implemented by each backend. Should raise on hard errors
        (network failure, model load failure, etc.).
        """

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable name shown in logs (e.g. 'gemini', 'gemma')."""

    # ── Public API ──────────────────────────────────────────────────────────

    async def evaluate(
        self,
        agent: Agent,
        policies: list[Policy],
        permission: Permission,
    ) -> PermissionDecision:
        """
        Evaluate whether an agent is permitted to perform an action.

        Args:
            agent:      The agent requesting the action.
            policies:   The policies assigned to the agent.
            permission: The action the agent wants to perform.

        Returns:
            PermissionDecision with result, reason, confidence, and matched rules.
        """
        start_time = time.monotonic()

        if not agent.is_active:
            return self._deny(
                agent.id, permission, latency_ms=0.0,
                reason="Agent is deactivated and cannot perform any actions.",
            )

        if not policies:
            return self._deny(
                agent.id, permission, latency_ms=0.0,
                reason="No policies assigned to this agent. All actions are denied by default.",
            )

        prompt = self._build_prompt(agent, policies, permission)

        try:
            raw = await self._generate(prompt)
            parsed = self._parse_response(raw)
            latency_ms = (time.monotonic() - start_time) * 1000

            decision = PermissionDecision(
                agent_id=agent.id,
                permission=permission,
                result=DecisionResult(parsed["decision"]),
                reason=parsed["reason"],
                confidence=ConfidenceLevel(parsed["confidence"]),
                matched_rules=parsed.get("matched_rules", []),
                latency_ms=round(latency_ms, 2),
            )

            logger.info(
                "Permission evaluated",
                backend=self.backend_name,
                agent=agent.name,
                action=permission.action,
                result=decision.result.value,
                confidence=decision.confidence.value,
                latency_ms=decision.latency_ms,
            )
            return decision

        except Exception as exc:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "Evaluation failed",
                backend=self.backend_name,
                error=str(exc),
                agent=agent.name,
            )
            return self._deny(
                agent.id, permission,
                latency_ms=round(latency_ms, 2),
                reason=f"Evaluation engine error. Access denied for safety. Error: {exc}",
            )

    # ── Helpers shared by all backends ──────────────────────────────────────

    def _build_prompt(
        self,
        agent: Agent,
        policies: list[Policy],
        permission: Permission,
    ) -> str:
        """Build the shared evaluation prompt."""
        policies_text = ""
        for i, policy in enumerate(policies, 1):
            policies_text += f"\n### Policy {i}: {policy.name}\n"
            if policy.description:
                policies_text += f"Description: {policy.description}\n"
            policies_text += "Rules:\n"
            for rule in policy.rules:
                policies_text += f"  - {rule}\n"

        additional_context = (
            json.dumps(permission.context, indent=2) if permission.context else "{}"
        )

        return EVALUATION_PROMPT_TEMPLATE.format(
            agent_name=agent.name,
            agent_scopes=", ".join(s.value for s in agent.scopes),
            policies_text=policies_text,
            permission_request=permission.as_natural_language,
            current_time=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            additional_context=additional_context,
        )

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        """
        Parse and validate the model's JSON response.

        Raises ValueError if the JSON is malformed or missing required fields.
        """
        # Strip markdown code fences if the model wrapped the JSON
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            # Remove first and last fence lines
            text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model returned invalid JSON: {response_text!r}") from exc

        required = {"decision", "reason", "confidence"}
        missing = required - set(parsed.keys())
        if missing:
            raise ValueError(f"Model response missing required fields: {missing}")

        valid_decisions = {d.value for d in DecisionResult}
        if parsed["decision"] not in valid_decisions:
            raise ValueError(f"Invalid decision value: {parsed['decision']!r}")

        valid_confidence = {c.value for c in ConfidenceLevel}
        if parsed["confidence"] not in valid_confidence:
            raise ValueError(f"Invalid confidence value: {parsed['confidence']!r}")

        return parsed

    def _deny(
        self,
        agent_id: UUID,
        permission: Permission,
        reason: str,
        latency_ms: float,
    ) -> PermissionDecision:
        """Create a DENY decision (used for error/default cases)."""
        return PermissionDecision(
            agent_id=agent_id,
            permission=permission,
            result=DecisionResult.DENY,
            reason=reason,
            confidence=ConfidenceLevel.HIGH,
            matched_rules=[],
            latency_ms=latency_ms,
        )
