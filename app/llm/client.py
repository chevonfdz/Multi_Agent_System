"""LLM wrapper.

LLM_PROVIDER=none (the default) runs the whole system with the rule-based task planner and
template replies, so no API key is needed. LLM_PROVIDER=anthropic uses Claude for task
planning and for writing combined replies; any failure falls back to the rules automatically.
To add another provider, subclass LLMClient and register it in build_llm().
"""
from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMClient:
    """Base class and the "none" provider: not enabled, every call raises LLMError."""
    provider = "none"
    model = ""

    @property
    def enabled(self) -> bool:
        return False

    async def complete(self, system: str, user: str, max_tokens: int = 4000) -> str:
        raise LLMError("No LLM provider is configured")

    async def complete_json(self, system: str, user: str, schema: dict[str, Any],
                            max_tokens: int = 4000) -> dict[str, Any]:
        raise LLMError("No LLM provider is configured")


class AnthropicLLM(LLMClient):
    provider = "anthropic"

    def __init__(self, model: str, timeout: float):
        import anthropic

        self._anthropic = anthropic
        self.model = model
        self.client = anthropic.AsyncAnthropic(timeout=timeout, max_retries=1)
        self.disabled_reason: str | None = None

    @property
    def enabled(self) -> bool:
        return self.disabled_reason is None

    async def _create(self, system: str, user: str, max_tokens: int,
                      output_config: dict[str, Any]) -> str:
        if not self.enabled:
            raise LLMError(self.disabled_reason or "LLM disabled")
        anthropic = self._anthropic
        try:
            response = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config=output_config,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                anthropic.NotFoundError) as exc:
            # Wrong key or model: stop calling the API and use the rules from now on.
            self.disabled_reason = f"{type(exc).__name__}: {exc}"
            log.error("Disabling the LLM and using rule-based mode: %s", self.disabled_reason)
            raise LLMError(self.disabled_reason) from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Rate limited by the LLM provider") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"LLM API error {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the LLM provider") from exc
        except anthropic.AnthropicError as exc:
            raise LLMError(str(exc)) from exc

        if response.stop_reason == "refusal":
            raise LLMError("The model declined the request")
        if response.stop_reason == "max_tokens":
            raise LLMError("The model response was cut off")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise LLMError("Empty response from the model")
        return text

    async def complete(self, system: str, user: str, max_tokens: int = 4000) -> str:
        return await self._create(system, user, max_tokens, {"effort": "low"})

    async def complete_json(self, system: str, user: str, schema: dict[str, Any],
                            max_tokens: int = 4000) -> dict[str, Any]:
        text = await self._create(system, user, max_tokens, {
            "effort": "low",
            "format": {"type": "json_schema", "schema": schema},
        })
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError("The model did not return valid JSON") from exc


def build_llm(provider: str, model: str, timeout: float) -> LLMClient:
    provider = (provider or "none").lower()
    if provider in ("", "none", "off", "rules"):
        return LLMClient()
    if provider == "anthropic":
        try:
            return AnthropicLLM(model=model, timeout=timeout)
        except Exception as exc:  # missing package or credentials problem
            log.error("Could not start the Anthropic client (%s); using rule-based mode", exc)
            return LLMClient()
    log.error("Unknown LLM_PROVIDER '%s'; using rule-based mode", provider)
    return LLMClient()
