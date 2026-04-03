"""
Normalize provider-native request/response formats to AgentLedger's
canonical internal schema.

Canonical request:  { messages, tools, model_id, provider, timestamp,
                      system_prompt, temperature, max_tokens, tool_results }
Canonical response: { content, tool_calls, stop_reason, tokens_in,
                      tokens_out, latency_ms, cost_usd }

Never store provider-native formats as source of truth.
"""

import time
from dataclasses import dataclass
from typing import Any, Optional

from .pricing import compute_cost


@dataclass
class CanonicalRequest:
    messages: list[dict]
    model_id: str
    provider: str
    timestamp: float
    tools: Optional[list[dict]] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tool_results: Optional[list[dict]] = None  # results fed into this call


@dataclass
class CanonicalResponse:
    content: Optional[str]
    tool_calls: Optional[list[dict]]
    stop_reason: Optional[str]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    latency_ms: float
    cost_usd: Optional[float] = None


def detect_provider(path: str, model: str) -> str:
    if "messages" in path or model.startswith("claude"):
        return "anthropic"
    return "openai"


def normalize_request(body: dict, path: str) -> CanonicalRequest:
    model = body.get("model", "unknown")
    provider = detect_provider(path, model)

    messages = list(body.get("messages", []))
    system_prompt: Optional[str] = None

    # Anthropic puts the system prompt as a top-level key
    system = body.get("system")
    if system and provider == "anthropic":
        system_prompt = system if isinstance(system, str) else None
        messages = [{"role": "system", "content": system}] + messages
    else:
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "system":
                content = msg.get("content", "")
                if isinstance(content, str):
                    system_prompt = content
                break

    tools: Optional[list[dict]] = body.get("tools") or body.get("functions") or None

    return CanonicalRequest(
        messages=messages,
        tools=tools,
        model_id=model,
        provider=provider,
        timestamp=time.time(),
        system_prompt=system_prompt,
        temperature=body.get("temperature"),
        max_tokens=body.get("max_tokens"),
        tool_results=_extract_tool_results(messages),
    )


def normalize_response(body: dict, latency_ms: float, model_id: str = "") -> CanonicalResponse:
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
        tokens_in = usage.get("prompt_tokens")
        tokens_out = usage.get("completion_tokens")
        return CanonicalResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=choice.get("finish_reason"),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cost_usd=compute_cost(model_id, tokens_in, tokens_out),
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
        tokens_in = usage.get("input_tokens")
        tokens_out = usage.get("output_tokens")
        return CanonicalResponse(
            content=text,
            tool_calls=tool_calls,
            stop_reason=body.get("stop_reason"),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cost_usd=compute_cost(model_id, tokens_in, tokens_out),
        )

    return CanonicalResponse(
        content=None,
        tool_calls=None,
        stop_reason=None,
        tokens_in=None,
        tokens_out=None,
        latency_ms=latency_ms,
    )


def _extract_tool_results(messages: list[dict]) -> Optional[list[dict]]:
    """Extract tool execution results from the message history sent to the model."""
    results = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        # OpenAI: role=tool
        if msg.get("role") == "tool":
            results.append({
                "tool_call_id": msg.get("tool_call_id"),
                "content": msg.get("content"),
            })
        # Anthropic: tool_result blocks inside a user message
        elif msg.get("role") == "user":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        results.append({
                            "tool_use_id": block.get("tool_use_id"),
                            "content": block.get("content"),
                        })
    return results or None
