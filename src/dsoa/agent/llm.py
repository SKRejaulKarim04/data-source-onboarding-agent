"""LLM access, behind a one-method protocol.

The protocol exists so the entire pipeline can be tested without a network call
or an API key. :class:`ScriptedClient` is not a mock of an LLM's behaviour — it
returns real JSON payloads that a real model produced, which keeps the tests
honest about the shape of what arrives.

Structured output uses tool-calling rather than "please reply with JSON":
the schema is enforced by the API, so parsing failures and markdown fences stop
being a class of bug you have to handle.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-3-5-sonnet-20241022"


class LLMError(RuntimeError):
    """The provider call failed or returned something unusable."""


@runtime_checkable
class LLMClient(Protocol):
    """Anything that can turn a prompt into a JSON object matching a schema."""

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        tool_name: str = "emit",
    ) -> dict[str, Any]:
        """Return a dict conforming to ``schema``."""
        ...


class AnthropicClient:
    """Structured extraction via the Anthropic Messages API.

    The SDK is imported lazily so that the package installs and the test suite
    runs on a machine that has never heard of it.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.0,
    ) -> None:
        self.model = model or os.environ.get("DSOA_LLM_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens
        # Temperature zero: this is extraction, not writing. Two identical
        # prompts producing two different specs would make the eval harness
        # meaningless and the artifacts irreproducible.
        self.temperature = temperature
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Export it, or use ScriptedClient "
                "for offline work."
            )
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ImportError as exc:  # pragma: no cover
                raise LLMError(
                    "The 'anthropic' package is not installed. " "pip install anthropic"
                ) from exc
            self._client = Anthropic(api_key=self._api_key)
        return self._client

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        tool_name: str = "emit",
    ) -> dict[str, Any]:
        client = self._get_client()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[
                    {
                        "name": tool_name,
                        "description": "Emit the extracted structure.",
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": tool_name},
            )
        except Exception as exc:
            raise LLMError(f"Provider call failed: {exc}") from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)

        raise LLMError("Model returned no tool_use block")


class GeminiClient:
    """Structured extraction via the Gemini API.

    The SDK is imported lazily so that the package installs and the test suite
    runs on a machine that has never heard of it.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        self.model = model or os.environ.get("DSOA_LLM_MODEL", "gemini-2.5-flash")
        self.temperature = temperature
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self._api_key:
            raise LLMError(
                "GEMINI_API_KEY is not set. Export it, or use ScriptedClient "
                "for offline work."
            )
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover
                raise LLMError(
                    "The 'google-genai' package is not installed. " "pip install google-genai"
                ) from exc
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        tool_name: str = "emit",
    ) -> dict[str, Any]:
        client = self._get_client()
        try:
            from google.genai import types
        except ImportError as exc:
            raise LLMError("Could not import types from google.genai") from exc

        # The standard JSON schema from Pydantic contains things like ['string', 'null']
        # which google.genai.types.Schema rejects. We pass it in the prompt instead.
        import json as json_mod
        full_system = f"{system}\n\nYou must respond with a JSON object that strictly conforms to this schema:\n{json_mod.dumps(schema)}"
        
        config = types.GenerateContentConfig(
            temperature=self.temperature,
            system_instruction=full_system,
            response_mime_type="application/json",
        )
        
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=user,
                config=config,
            )
        except Exception as exc:
            raise LLMError(f"Provider call failed: {exc}") from exc

        if not response.text:
            raise LLMError("Model returned empty response")

        try:
            return json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Failed to parse JSON response: {exc}") from exc




class ScriptedClient:
    """Deterministic client for tests, demos, and CI.

    Args:
        responses: Payloads returned in order, or keyed by a substring that must
            appear in the user prompt.
        default: Returned when nothing matches.
    """

    def __init__(
        self,
        responses: list[dict[str, Any]] | dict[str, dict[str, Any]] | None = None,
        *,
        default: dict[str, Any] | None = None,
    ) -> None:
        self._responses = responses if responses is not None else []
        self._default = default if default is not None else {}
        self._index = 0
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        tool_name: str = "emit",
    ) -> dict[str, Any]:
        self.calls.append({"system": system, "user": user, "tool": tool_name})

        if isinstance(self._responses, dict):
            for needle, payload in self._responses.items():
                if needle.lower() in user.lower():
                    return json.loads(json.dumps(payload))
            return json.loads(json.dumps(self._default))

        if self._index < len(self._responses):
            payload = self._responses[self._index]
            self._index += 1
            return json.loads(json.dumps(payload))

        return json.loads(json.dumps(self._default))


def default_client() -> LLMClient:
    """Real client when a key is present, scripted client otherwise."""
    try:
        return GeminiClient()
    except LLMError:
        pass
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClient()
    logger.warning("No API key set — falling back to ScriptedClient")
    return ScriptedClient()

class DeepseekClient:
    """Structured extraction via the Deepseek API (using OpenAI SDK)."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        self.model = model or os.environ.get("DSOA_LLM_MODEL", "deepseek-chat")
        self.temperature = temperature
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self._api_key:
            raise LLMError("DEEPSEEK_API_KEY is not set.")
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LLMError("pip install openai") from exc
            self._client = OpenAI(api_key=self._api_key, base_url="https://api.deepseek.com")
        return self._client

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        tool_name: str = "emit",
    ) -> dict[str, Any]:
        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "description": "Emit the extracted structure.",
                            "parameters": schema,
                        }
                    }
                ],
                tool_choice={"type": "function", "function": {"name": tool_name}},
            )
        except Exception as exc:
            raise LLMError(f"Provider call failed: {exc}") from exc

        message = response.choices[0].message
        if not message.tool_calls:
            raise LLMError("Model returned no tool calls")
            
        return json.loads(message.tool_calls[0].function.arguments)
