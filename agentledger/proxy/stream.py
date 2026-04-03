"""
SSE chunk accumulation for streaming LLM responses.

Reconstructs a CanonicalResponse from accumulated OpenAI-format SSE chunks.
Anthropic streaming is normalized to OpenAI format by LiteLLM before it
reaches the proxy, so we only need to handle one format here.

If the request bypasses LiteLLM and goes directly to Anthropic, we also
handle Anthropic's native SSE format (content_block_delta events).
"""

import json
from typing import Optional

from .normalize import CanonicalResponse
from .pricing import compute_cost


def reconstruct_from_sse(body: bytes, latency_ms: float, model_id: str = "") -> CanonicalResponse:
    """Reconstruct a CanonicalResponse from raw SSE bytes."""
    text = body.decode("utf-8", errors="replace")

    # Detect format from first meaningful data line
    first_chunk = _first_json_chunk(text)
    if first_chunk and "type" in first_chunk:
        return _reconstruct_anthropic(text, latency_ms, model_id)
    return _reconstruct_openai(text, latency_ms, model_id)


# ── OpenAI SSE format ────────────────────────────────────────────────────────

def _reconstruct_openai(text: str, latency_ms: float, model_id: str = "") -> CanonicalResponse:
    text_parts: list[str] = []
    tool_calls: dict[int, dict] = {}  # index → {id, name, arguments}
    stop_reason: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None

    for chunk in _iter_sse_json(text):
        choices = chunk.get("choices", [])
        if choices:
            choice = choices[0]
            delta = choice.get("delta", {})

            if delta.get("content"):
                text_parts.append(delta["content"])

            if choice.get("finish_reason"):
                stop_reason = choice["finish_reason"]

            for tc_delta in delta.get("tool_calls", []):
                idx = tc_delta.get("index", 0)
                if idx not in tool_calls:
                    tool_calls[idx] = {"id": None, "name": None, "arguments": ""}
                if tc_delta.get("id"):
                    tool_calls[idx]["id"] = tc_delta["id"]
                fn = tc_delta.get("function", {})
                if fn.get("name"):
                    tool_calls[idx]["name"] = fn["name"]
                if fn.get("arguments"):
                    tool_calls[idx]["arguments"] += fn["arguments"]

        usage = chunk.get("usage", {})
        if usage:
            tokens_in = usage.get("prompt_tokens")
            tokens_out = usage.get("completion_tokens")

    return CanonicalResponse(
        content="".join(text_parts) or None,
        tool_calls=[
            {"id": tc["id"], "name": tc["name"], "arguments": tc["arguments"]}
            for tc in tool_calls.values()
        ] or None,
        stop_reason=stop_reason,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        cost_usd=compute_cost(model_id, tokens_in, tokens_out),
    )


# ── Anthropic native SSE format ──────────────────────────────────────────────

def _reconstruct_anthropic(text: str, latency_ms: float, model_id: str = "") -> CanonicalResponse:
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    current_tool: Optional[dict] = None
    stop_reason: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None

    for chunk in _iter_sse_json(text):
        event_type = chunk.get("type")

        if event_type == "content_block_start":
            block = chunk.get("content_block", {})
            if block.get("type") == "tool_use":
                current_tool = {
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "arguments": "",
                }

        elif event_type == "content_block_delta":
            delta = chunk.get("delta", {})
            if delta.get("type") == "text_delta":
                text_parts.append(delta.get("text", ""))
            elif delta.get("type") == "input_json_delta" and current_tool is not None:
                current_tool["arguments"] += delta.get("partial_json", "")

        elif event_type == "content_block_stop":
            if current_tool is not None:
                tool_calls.append(current_tool)
                current_tool = None

        elif event_type == "message_delta":
            delta = chunk.get("delta", {})
            if delta.get("stop_reason"):
                stop_reason = delta["stop_reason"]
            usage = chunk.get("usage", {})
            if usage:
                tokens_out = usage.get("output_tokens")

        elif event_type == "message_start":
            usage = chunk.get("message", {}).get("usage", {})
            if usage:
                tokens_in = usage.get("input_tokens")

    return CanonicalResponse(
        content="".join(text_parts) or None,
        tool_calls=tool_calls or None,
        stop_reason=stop_reason,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        cost_usd=compute_cost(model_id, tokens_in, tokens_out),
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _iter_sse_json(text: str):
    """Yield parsed JSON objects from SSE data lines."""
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def _first_json_chunk(text: str) -> Optional[dict]:
    return next(_iter_sse_json(text), None)
