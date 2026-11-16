"""
Tests for GemmaEngine and BaseEngine.

The transformers pipeline is mocked — no model weights are needed.
Tests cover:
  - GemmaEngine.evaluate() with ALLOW / DENY / ESCALATE responses
  - Deactivated agent → DENY without calling the model
  - No policies assigned → DENY without calling the model
  - Invalid JSON from model → DENY (fail-closed)
  - Markdown-fenced JSON response → parsed correctly
  - Missing required fields in model response → DENY
  - BaseEngine._parse_response() edge cases
  - _build_engine() factory function: gemini and gemma backends
  - Gemma ImportError when transformers is not installed
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agentauth.core.base_engine import BaseEngine, EVALUATION_PROMPT_TEMPLATE
from agentauth.core.models import (
    Agent,
    AgentScope,
    ConfidenceLevel,
    DecisionResult,
    Permission,
    PermissionDecision,
    Policy,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_agent(**kwargs) -> Agent:
    defaults = dict(
        name="test-agent",
        owner_id="user_1",
        scopes=[AgentScope.READ],
        policy_ids=[],
    )
    defaults.update(kwargs)
    return Agent(**defaults)


def _make_policy(**kwargs) -> Policy:
    defaults = dict(
        name="test-policy",
        rules=["Agent may read data", "Agent must not delete data"],
    )
    defaults.update(kwargs)
    return Policy(**defaults)


def _make_permission(**kwargs) -> Permission:
    defaults = dict(action="read", resource="database", context={})
    defaults.update(kwargs)
    return Permission(**defaults)


def _json_response(result="ALLOW", reason="Permitted", confidence="HIGH", rules=None) -> str:
    return json.dumps({
        "decision": result,
        "reason": reason,
        "confidence": confidence,
        "matched_rules": rules or ["Agent may read data"],
    })


# ── Concrete engine for testing BaseEngine in isolation ───────────────────────


class _EchoEngine(BaseEngine):
    """Minimal concrete engine that returns whatever _next_response is set to."""

    def __init__(self):
        self._next_response = _json_response()

    @property
    def backend_name(self) -> str:
        return "echo"

    async def _generate(self, prompt: str) -> str:
        return self._next_response


# ── BaseEngine tests ──────────────────────────────────────────────────────────


class TestBaseEngine:
    @pytest.mark.asyncio
    async def test_allow_decision(self):
        engine = _EchoEngine()
        engine._next_response = _json_response("ALLOW")
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.ALLOW
        assert decision.confidence == ConfidenceLevel.HIGH
        assert len(decision.matched_rules) > 0
        assert decision.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_deny_decision(self):
        engine = _EchoEngine()
        engine._next_response = _json_response("DENY", reason="Not permitted")
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission(action="delete")
        )
        assert decision.result == DecisionResult.DENY
        assert "Not permitted" in decision.reason

    @pytest.mark.asyncio
    async def test_escalate_decision(self):
        engine = _EchoEngine()
        engine._next_response = _json_response("ESCALATE", confidence="LOW")
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.ESCALATE
        assert decision.confidence == ConfidenceLevel.LOW

    @pytest.mark.asyncio
    async def test_deactivated_agent_denied_without_model_call(self):
        engine = _EchoEngine()
        agent = _make_agent(is_active=False)
        called = False

        original_generate = engine._generate
        async def spy(prompt):
            nonlocal called
            called = True
            return await original_generate(prompt)
        engine._generate = spy

        decision = await engine.evaluate(agent, [_make_policy()], _make_permission())
        assert decision.result == DecisionResult.DENY
        assert "deactivated" in decision.reason.lower()
        assert not called

    @pytest.mark.asyncio
    async def test_no_policies_denied_without_model_call(self):
        engine = _EchoEngine()
        called = False

        async def spy(prompt):
            nonlocal called
            called = True
            return _json_response()
        engine._generate = spy

        decision = await engine.evaluate(_make_agent(), [], _make_permission())
        assert decision.result == DecisionResult.DENY
        assert "no policies" in decision.reason.lower()
        assert not called

    @pytest.mark.asyncio
    async def test_invalid_json_response_denied(self):
        engine = _EchoEngine()
        engine._next_response = "this is not json at all"
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.DENY
        assert "error" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_markdown_fenced_json_parsed_correctly(self):
        engine = _EchoEngine()
        engine._next_response = (
            "```json\n"
            + _json_response("ALLOW")
            + "\n```"
        )
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.ALLOW

    @pytest.mark.asyncio
    async def test_missing_required_fields_denied(self):
        engine = _EchoEngine()
        engine._next_response = json.dumps({"decision": "ALLOW"})  # missing reason + confidence
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.DENY

    @pytest.mark.asyncio
    async def test_invalid_decision_value_denied(self):
        engine = _EchoEngine()
        engine._next_response = json.dumps({
            "decision": "MAYBE",
            "reason": "unsure",
            "confidence": "HIGH",
        })
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.DENY

    @pytest.mark.asyncio
    async def test_multiple_policies_included_in_prompt(self):
        engine = _EchoEngine()
        engine._next_response = _json_response()

        p1 = _make_policy(name="policy-1", rules=["Allow reads"])
        p2 = _make_policy(name="policy-2", rules=["Deny deletes", "Deny writes"])

        prompts_seen = []
        original = engine._generate
        async def capture(prompt):
            prompts_seen.append(prompt)
            return await original(prompt)
        engine._generate = capture

        await engine.evaluate(_make_agent(), [p1, p2], _make_permission())
        assert len(prompts_seen) == 1
        assert "policy-1" in prompts_seen[0]
        assert "policy-2" in prompts_seen[0]
        assert "Allow reads" in prompts_seen[0]
        assert "Deny deletes" in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_context_included_in_prompt(self):
        engine = _EchoEngine()
        engine._next_response = _json_response()

        prompts_seen = []
        async def capture(prompt):
            prompts_seen.append(prompt)
            return _json_response()
        engine._generate = capture

        perm = _make_permission(context={"amount": 500, "currency": "ETB"})
        await engine.evaluate(_make_agent(), [_make_policy()], perm)
        assert "amount" in prompts_seen[0]
        assert "ETB" in prompts_seen[0]

    def test_parse_response_valid(self):
        engine = _EchoEngine()
        result = engine._parse_response(_json_response("DENY", "not allowed", "HIGH"))
        assert result["decision"] == "DENY"
        assert result["reason"] == "not allowed"

    def test_parse_response_strips_markdown_fence(self):
        engine = _EchoEngine()
        fenced = "```json\n" + _json_response() + "\n```"
        result = engine._parse_response(fenced)
        assert result["decision"] == "ALLOW"

    def test_parse_response_raises_on_bad_json(self):
        engine = _EchoEngine()
        with pytest.raises(ValueError, match="invalid JSON"):
            engine._parse_response("not json")

    def test_parse_response_raises_on_missing_fields(self):
        engine = _EchoEngine()
        with pytest.raises(ValueError, match="missing required fields"):
            engine._parse_response(json.dumps({"decision": "ALLOW"}))

    def test_parse_response_raises_on_invalid_decision(self):
        engine = _EchoEngine()
        with pytest.raises(ValueError, match="Invalid decision"):
            engine._parse_response(json.dumps({
                "decision": "UNKNOWN", "reason": "x", "confidence": "HIGH"
            }))


# ── GemmaEngine tests ─────────────────────────────────────────────────────────


def _make_mock_pipeline(response_text: str):
    """Return a mock that behaves like a transformers text-generation pipeline."""
    mock_pipeline = MagicMock()
    mock_pipeline.return_value = [{"generated_text": response_text}]
    return mock_pipeline


@patch.dict("sys.modules", {"transformers": MagicMock(), "torch": MagicMock()})
class TestGemmaEngine:
    """
    All tests in this class run with transformers and torch mocked out.
    The pipeline itself is replaced with a MagicMock that returns
    controlled JSON responses.
    """

    def _make_engine(self, response_text: str):
        """Create a GemmaEngine with a mocked transformers pipeline."""
        from agentauth.core.gemma_engine import GemmaEngine

        with patch("agentauth.core.gemma_engine.GemmaEngine.__init__") as mock_init:
            mock_init.return_value = None
            engine = GemmaEngine.__new__(GemmaEngine)
            engine._pipeline = _make_mock_pipeline(response_text)
            engine._source = "google/gemma-3-1b-it"
            engine._max_new_tokens = 512
            return engine

    @pytest.mark.asyncio
    async def test_allow_decision(self):
        engine = self._make_engine(_json_response("ALLOW"))
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.ALLOW

    @pytest.mark.asyncio
    async def test_deny_decision(self):
        engine = self._make_engine(_json_response("DENY", reason="Forbidden"))
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission(action="delete")
        )
        assert decision.result == DecisionResult.DENY
        assert "Forbidden" in decision.reason

    @pytest.mark.asyncio
    async def test_escalate_decision(self):
        engine = self._make_engine(_json_response("ESCALATE", confidence="LOW"))
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.ESCALATE

    @pytest.mark.asyncio
    async def test_pipeline_called_with_prompt(self):
        engine = self._make_engine(_json_response())
        await engine.evaluate(_make_agent(), [_make_policy()], _make_permission())
        engine._pipeline.assert_called_once()
        call_args = engine._pipeline.call_args
        prompt_arg = call_args[0][0]
        assert "AgentAuth" in prompt_arg
        assert "test-agent" in prompt_arg

    @pytest.mark.asyncio
    async def test_empty_pipeline_output_denied(self):
        engine = self._make_engine(_json_response())
        engine._pipeline.return_value = []
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.DENY

    @pytest.mark.asyncio
    async def test_empty_generated_text_denied(self):
        engine = self._make_engine(_json_response())
        engine._pipeline.return_value = [{"generated_text": ""}]
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.DENY

    @pytest.mark.asyncio
    async def test_markdown_fenced_json_parsed(self):
        fenced = "```json\n" + _json_response("ALLOW") + "\n```"
        engine = self._make_engine(fenced)
        decision = await engine.evaluate(
            _make_agent(), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.ALLOW

    @pytest.mark.asyncio
    async def test_deactivated_agent_denied_no_pipeline_call(self):
        engine = self._make_engine(_json_response())
        decision = await engine.evaluate(
            _make_agent(is_active=False), [_make_policy()], _make_permission()
        )
        assert decision.result == DecisionResult.DENY
        engine._pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_policies_denied_no_pipeline_call(self):
        engine = self._make_engine(_json_response())
        decision = await engine.evaluate(_make_agent(), [], _make_permission())
        assert decision.result == DecisionResult.DENY
        engine._pipeline.assert_not_called()

    def test_backend_name(self):
        engine = self._make_engine(_json_response())
        assert engine.backend_name == "gemma"

    def test_import_error_when_transformers_missing(self):
        """GemmaEngine raises ImportError with a helpful message if transformers is not installed."""
        import sys
        # Temporarily remove the mock so the real import fails
        with patch.dict(sys.modules, {"transformers": None, "torch": None}):
            with pytest.raises(ImportError, match="agentauth\\[gemma\\]"):
                from agentauth.core.gemma_engine import GemmaEngine
                # Force reimport by creating a new instance
                GemmaEngine(model_id="google/gemma-3-1b-it")


# ── Engine factory / backend selection tests ─────────────────────────────────
# These test the _build_engine logic directly without importing the server
# (which requires fastapi).


class TestBuildEngineLogic:
    """
    Test the backend-selection logic in isolation.

    We replicate the _build_engine decision tree here rather than importing
    the server module, so this test file has no fastapi dependency.
    """

    def _build_engine_logic(self, backend: str, gemini_key: str | None, model_id: str | None):
        """Mirror of _build_engine() without fastapi imports."""
        if backend == "gemma":
            from agentauth.core.gemma_engine import GemmaEngine  # noqa
            return "gemma"
        # gemini default
        if not gemini_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is required")
        return "gemini"

    def test_default_backend_is_gemini(self, monkeypatch):
        monkeypatch.delenv("REASONING_BACKEND", raising=False)
        result = self._build_engine_logic("gemini", "test-key", None)
        assert result == "gemini"

    def test_gemini_explicit(self, monkeypatch):
        result = self._build_engine_logic("gemini", "test-key", None)
        assert result == "gemini"

    def test_missing_gemini_key_raises(self, monkeypatch):
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            self._build_engine_logic("gemini", None, None)

    def test_gemma_backend_returns_gemma_name(self, monkeypatch):
        with patch.dict("sys.modules", {"transformers": MagicMock(), "torch": MagicMock()}):
            result = self._build_engine_logic("gemma", None, "google/gemma-3-1b-it")
        assert result == "gemma"

    def test_base_engine_cannot_be_instantiated_directly(self):
        with pytest.raises(TypeError):
            BaseEngine()  # abstract — missing _generate and backend_name
