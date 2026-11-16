"""
AgentAuth Gemini Engine.

Uses Google Gemini to evaluate whether an AI agent's requested action is
permitted under its assigned policies.

This is the default reasoning backend. For offline / air-gapped environments
set REASONING_BACKEND=gemma to use GemmaEngine instead.
"""

from __future__ import annotations

import structlog

from agentauth.core.base_engine import BaseEngine

logger = structlog.get_logger(__name__)


class AgentAuthEngine(BaseEngine):
    """
    Gemini-powered permission evaluation engine.

    Extends BaseEngine — all prompt construction, JSON parsing, error
    handling, and audit logging live in the base class. This class only
    handles Gemini-specific initialisation and the _generate() call.

    Usage:
        engine = AgentAuthEngine(api_key="your-gemini-api-key")
        decision = await engine.evaluate(agent, policies, permission)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        temperature: float = 0.1,
    ) -> None:
        """
        Args:
            api_key:     Google Gemini API key.
            model:       Gemini model to use. Defaults to gemini-1.5-flash.
            temperature: Lower = more deterministic. Keep at 0.1 or below.
        """
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError(
                "google-generativeai is required for AgentAuthEngine. "
                "Install it with: pip install agentauth"
            ) from exc

        genai.configure(api_key=api_key)
        self._gemini_model = genai.GenerativeModel(
            model_name=model,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
        self._model_name = model
        logger.info("AgentAuth Gemini engine initialized", model=model)

    @property
    def backend_name(self) -> str:
        return "gemini"

    async def _generate(self, prompt: str) -> str:
        """Call Gemini and return raw response text."""
        response = await self._gemini_model.generate_content_async(prompt)
        return response.text

    # Keep evaluate_sync for non-async callers
    def evaluate_sync(self, agent, policies, permission):
        """Synchronous wrapper for non-async contexts."""
        import asyncio
        return asyncio.run(self.evaluate(agent, policies, permission))
