"""
AgentAuth Gemma Engine.

Uses a locally-running Google Gemma model (via HuggingFace transformers)
to evaluate permissions entirely offline — no API key, no cloud calls,
no data leaves the machine.

This is the alternative to AgentAuthEngine (Gemini) for:
  - Air-gapped / offline environments
  - Cost-sensitive deployments (no per-call API fees)
  - Privacy-first setups where policy data must not leave the host
  - Edge / on-device inference

## Setup

Install the gemma extras:

    pip install "agentauth[gemma]"

Set environment variables:

    REASONING_BACKEND=gemma
    GEMMA_MODEL_ID=google/gemma-3-1b-it     # HuggingFace model ID (auto-downloaded)
    # OR
    GEMMA_MODEL_PATH=/path/to/local/weights  # local directory with model files

## Supported models

Any instruction-tuned model that follows the prompt format works, but
Google's Gemma family gives the best results for structured JSON output:

  - google/gemma-3-1b-it   (~1 GB, runs on CPU, fastest)
  - google/gemma-3-4b-it   (~4 GB, better reasoning)
  - google/gemma-3-12b-it  (~12 GB, requires GPU or quantisation)

For CPU-only inference with limited RAM, use gemma-3-1b-it with 4-bit
quantisation (requires bitsandbytes):

    GEMMA_MODEL_ID=google/gemma-3-1b-it
    GEMMA_LOAD_IN_4BIT=true

## HuggingFace access

Gemma models require accepting Google's licence on HuggingFace before
downloading. Set HF_TOKEN in your environment after accepting the licence:

    HF_TOKEN=hf_your_token_here

For fully offline use, download the weights once and set GEMMA_MODEL_PATH
to the local directory.
"""

from __future__ import annotations

import asyncio
import os
from functools import partial
from typing import Any

import structlog

from agentauth.core.base_engine import BaseEngine

logger = structlog.get_logger(__name__)

# Maximum new tokens the model is allowed to generate.
# The JSON response is short — 512 tokens is more than enough.
_MAX_NEW_TOKENS = 512

# Default model — smallest Gemma that reliably produces structured JSON.
_DEFAULT_MODEL_ID = "google/gemma-3-1b-it"


class GemmaEngine(BaseEngine):
    """
    Local Gemma permission evaluation engine.

    Loads a Gemma (or any compatible) model via HuggingFace transformers
    and runs inference in a thread pool so the async event loop is never
    blocked.

    The same prompt template as AgentAuthEngine is used, so decisions are
    comparable between backends.
    """

    def __init__(
        self,
        model_id: str | None = None,
        model_path: str | None = None,
        device: str | None = None,
        load_in_4bit: bool = False,
        load_in_8bit: bool = False,
        max_new_tokens: int = _MAX_NEW_TOKENS,
    ) -> None:
        """
        Load the Gemma model and tokenizer.

        One of ``model_id`` or ``model_path`` must be provided. If neither
        is set, falls back to the ``GEMMA_MODEL_ID`` / ``GEMMA_MODEL_PATH``
        environment variables, then to the default 1B model.

        Args:
            model_id:       HuggingFace model identifier, e.g.
                            ``"google/gemma-3-1b-it"``. The model is
                            downloaded on first use and cached by HF.
            model_path:     Local directory containing model weights.
                            Takes precedence over model_id if both are set.
            device:         ``"cpu"``, ``"cuda"``, ``"mps"``, or ``None``
                            to auto-detect. Defaults to CPU when no GPU
                            is available.
            load_in_4bit:   Load with 4-bit quantisation (requires
                            bitsandbytes). Halves VRAM/RAM at the cost
                            of a small quality degradation.
            load_in_8bit:   Load with 8-bit quantisation. Middle ground
                            between 4-bit and full precision.
            max_new_tokens: Maximum tokens to generate per evaluation.
        """
        # Import here so transformers is only required when GemmaEngine is used
        try:
            from transformers import pipeline as hf_pipeline
            import torch
        except ImportError as exc:
            raise ImportError(
                "transformers and torch are required for GemmaEngine. "
                "Install them with: pip install 'agentauth[gemma]'"
            ) from exc

        # Resolve model source
        source = (
            model_path
            or os.getenv("GEMMA_MODEL_PATH")
            or model_id
            or os.getenv("GEMMA_MODEL_ID")
            or _DEFAULT_MODEL_ID
        )

        # Resolve device
        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"

        # Build quantisation kwargs
        pipeline_kwargs: dict[str, Any] = {
            "task": "text-generation",
            "model": source,
            "device_map": "auto" if device != "cpu" else None,
            "max_new_tokens": max_new_tokens,
            "do_sample": False,         # greedy decoding — deterministic
            "temperature": None,        # required when do_sample=False in newer transformers
            "top_p": None,
        }

        if load_in_4bit or load_in_8bit:
            try:
                from transformers import BitsAndBytesConfig
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=load_in_4bit,
                    load_in_8bit=load_in_8bit,
                )
                pipeline_kwargs["model_kwargs"] = {"quantization_config": bnb_config}
            except ImportError:
                logger.warning(
                    "bitsandbytes not installed — loading model at full precision. "
                    "Install with: pip install bitsandbytes"
                )

        if device == "cpu":
            pipeline_kwargs["device"] = -1  # -1 = CPU in transformers

        logger.info(
            "Loading Gemma model",
            source=source,
            device=device,
            load_in_4bit=load_in_4bit,
            load_in_8bit=load_in_8bit,
        )

        self._pipeline = hf_pipeline(**pipeline_kwargs)
        self._source = source
        self._max_new_tokens = max_new_tokens

        logger.info("GemmaEngine ready", source=source, device=device)

    @property
    def backend_name(self) -> str:
        return "gemma"

    async def _generate(self, prompt: str) -> str:
        """
        Run the Gemma model in a thread pool so the async event loop
        is not blocked during inference (which can take several seconds
        on CPU).
        """
        loop = asyncio.get_event_loop()
        # Run the synchronous HuggingFace pipeline in a thread
        result = await loop.run_in_executor(
            None,
            partial(self._run_pipeline, prompt),
        )
        return result

    def _run_pipeline(self, prompt: str) -> str:
        """
        Synchronous inference call. Runs in a thread pool executor.

        Returns the generated text (excluding the input prompt).
        """
        outputs = self._pipeline(
            prompt,
            max_new_tokens=self._max_new_tokens,
            return_full_text=False,   # only return the generated part, not the prompt
        )

        if not outputs or not outputs[0]:
            raise ValueError("Gemma pipeline returned empty output")

        generated = outputs[0].get("generated_text", "")
        if not generated:
            raise ValueError("Gemma pipeline returned no generated_text")

        return generated
