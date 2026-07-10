"""
AgentAuth Core Engine.

The heart of AgentAuth: uses Google Gemini to evaluate whether an AI agent's
requested action is permitted under its assigned policies.

This is NOT a rules engine. It is an intelligent reasoning engine that
understands nuanced, context-dependent policies in natural language.
"""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import UUID

import google.generativeai as genai
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

_EVALUATION_PROMPT_TEMPLATE = """
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


class AgentAuthEngine:
    """
    The AgentAuth permission evaluation engine.

    Uses Google Gemini to intelligently evaluate whether an AI agent's
    requested action complies with its assigned natural language policies.

    Usage:
        engine = AgentAuthEngine(api_key="your-gemini-api-key")

        policy = Policy(
            name="trading-policy",
            rules=[
                "Agent may only execute trades during market hours",
                "Agent may not execute trades above $10,000 without approval",
            ]
        )

        agent = Agent(
            name="portfolio-rebalancer",
            owner_id="user_123",
            scopes=[AgentScope.EXECUTE],
            policy_ids=[policy.id],
        )

        permission = Permission(
            action="execute_trade",
            resource="binance_spot",
            context={"amount": 500, "symbol": "BTCUSDT"},
        )

        decision = await engine.evaluate(agent, [policy], permission)
        print(decision.result)  # DecisionResult.ALLOW
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        temperature: float = 0.1,
    ) -> None:
        """
        Initialize the AgentAuth engine.

        Args:
            api_key: Google Gemini API key.
            model: Gemini model to use. Defaults to gemini-1.5-flash for speed.
            temperature: Lower = more deterministic decisions. Keep at 0.1 or below.
        """
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name=model,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
        self._model_name = model
        logger.info("AgentAuth engine initialized", model=model)

    async def evaluate(
        self,
        agent: Agent,
        policies: list[Policy],
        permission: Permission,
    ) -> PermissionDecision:
        """
        Evaluate whether an agent is permitted to perform an action.

        Args:
            agent: The agent requesting the action.
            policies: The policies assigned to the agent.
            permission: The action the agent wants to perform.

        Returns:
            PermissionDecision with result, reason, confidence, and matched rules.
        """
        start_time = time.monotonic()

        if not agent.is_active:
            return self._deny_decision(
                agent_id=agent.id,
                permission=permission,
                reason="Agent is deactivated and cannot perform any actions.",
                latency_ms=0.0,
            )

        if not policies:
            return self._deny_decision(
                agent_id=agent.id,
                permission=permission,
                reason="No policies assigned to this agent. All actions are denied by default.",
                latency_ms=0.0,
            )

        prompt = self._build_prompt(agent, policies, permission)

        try:
            response = await self._call_gemini(prompt)
            parsed = self._parse_response(response)
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
                agent=agent.name,
                action=permission.action,
                result=decision.result.value,
                confidence=decision.confidence.value,
                latency_ms=decision.latency_ms,
            )
            return decision

        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.error("Evaluation failed", error=str(e), agent=agent.name)
            # Fail closed — deny on error
            return self._deny_decision(
                agent_id=agent.id,
                permission=permission,
                reason=f"Evaluation engine error. Access denied for safety. Error: {str(e)}",
                latency_ms=round(latency_ms, 2),
            )

    def evaluate_sync(
        self,
        agent: Agent,
        policies: list[Policy],
        permission: Permission,
    ) -> PermissionDecision:
        """
        Synchronous version of evaluate() for non-async contexts.
        Uses Gemini's synchronous API.
        """
        import asyncio
        return asyncio.run(self.evaluate(agent, policies, permission))

    def _build_prompt(
        self,
        agent: Agent,
        policies: list[Policy],
        permission: Permission,
    ) -> str:
        """Build the evaluation prompt for Gemini."""
        from datetime import datetime, timezone

        policies_text = ""
        for i, policy in enumerate(policies, 1):
            policies_text += f"\n### Policy {i}: {policy.name}\n"
            if policy.description:
                policies_text += f"Description: {policy.description}\n"
            policies_text += "Rules:\n"
            for rule in policy.rules:
                policies_text += f"  - {rule}\n"

        additional_context = json.dumps(permission.context, indent=2) if permission.context else "{}"

        return _EVALUATION_PROMPT_TEMPLATE.format(
            agent_name=agent.name,
            agent_scopes=", ".join(s.value for s in agent.scopes),
            policies_text=policies_text,
            permission_request=permission.as_natural_language,
            current_time=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            additional_context=additional_context,
        )

    async def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API and return raw response text."""
        response = await self._model.generate_content_async(prompt)
        return response.text

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        """Parse and validate Gemini's JSON response."""
        try:
            parsed = json.loads(response_text.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"Gemini returned invalid JSON: {response_text}") from e

        required_fields = {"decision", "reason", "confidence"}
        missing = required_fields - set(parsed.keys())
        if missing:
            raise ValueError(f"Gemini response missing required fields: {missing}")

        valid_decisions = {d.value for d in DecisionResult}
        if parsed["decision"] not in valid_decisions:
            raise ValueError(f"Invalid decision value: {parsed['decision']}")

        valid_confidence = {c.value for c in ConfidenceLevel}
        if parsed["confidence"] not in valid_confidence:
            raise ValueError(f"Invalid confidence value: {parsed['confidence']}")

        return parsed

    def _deny_decision(
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
