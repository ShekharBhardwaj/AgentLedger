"""
Normalize provider-native request/response formats to AgentLedger's
canonical internal schema.

Canonical request:  { messages, tools, model_id, provider, timestamp }
Canonical response: { content, tool_calls, stop_reason, tokens_in, tokens_out, latency_ms }

Never store provider-native formats as source of truth.
"""

import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CanonicalRequest:
    messages: list[dict]
    model_id: str
    provider: str
    timestamp: float
    tools: Optional[list[dict]] = None


@dataclass
class CanonicalResponse:
    content: Optional[str]
    tool_calls: Optional[list[dict]]
    stop_reason: Optional[str]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    latency_ms: float


def detect_provider(path: str, model: str) -> str:
    if "messages" in path or model.startswith("claude"):
        return "anthropic"
    return "openai"


def normalize_request(body: dict, path: str) -> CanonicalRequest:
    model = body.get("model", "unknown")
    provider = detect_provider(path, model)

    messages = list(body.get("messages", []))

    # Anthropic puts the system prompt as a top-level key, not in messages
    system = body.get("system")
    if system and provider == "anthropic":
        messages = [{"role": "system", "content": system}] + messages

    # Normalize tools: OpenAI uses "tools", older OpenAI used "functions"
    tools: Optional[list[dict]] = body.get("tools") or body.get("functions") or None

    return CanonicalRequest(
        messages=messages,
        tools=tools,
        model_id=model,
        provider=provider,
        timestamp=time.time(),
    )


def normalize_response(body: dict, latency_ms: float) -> CanonicalResponse:
    # OpenAI / LiteLLM format
    choices = body.get("choices")
    if choices:
        choice = choices[0]
        msg = choice.get("message", {})
        content = msg.get("content")

        raw_tcs = msg.get("tool_calls") or []
        tool_calls: Optional[list[dict]] = [
            {
                "id": tc.get("id"),
                "name": tc["function"]["name"],
                "arguments": tc["function"]["arguments"],
            }
            for tc in raw_tcs
        ] or None

        usage = body.get("usage", {})
        return CanonicalResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=choice.get("finish_reason"),
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            latency_ms=latency_ms,
        )

    # Anthropic format
    content_blocks = body.get("content")
    if content_blocks:
        text = next(
            (b["text"] for b in content_blocks if b.get("type") == "text"), None
        )
        tool_calls = [
            {"id": b.get("id"), "name": b.get("name"), "arguments": b.get("input")}
            for b in content_blocks
            if b.get("type") == "tool_use"
        ] or None

        usage = body.get("usage", {})
        return CanonicalResponse(
            content=text,
            tool_calls=tool_calls,
            stop_reason=body.get("stop_reason"),
            tokens_in=usage.get("input_tokens"),
            tokens_out=usage.get("output_tokens"),
            latency_ms=latency_ms,
        )

    return CanonicalResponse(
        content=None,
        tool_calls=None,
        stop_reason=None,
        tokens_in=None,
        tokens_out=None,
        latency_ms=latency_ms,
    )
