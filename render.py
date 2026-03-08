"""
Console renderer for traces.

Pretty-prints traces as a causal decision chain.
"""

from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .tracer import Trace, TraceEvent


def render_trace(trace: "Trace") -> str:
    """
    Render a trace as a human-readable causal chain.
    
    Shows:
    - LLM calls with prompts and token usage
    - Tool requests from LLM
    - Tool executions with args and results
    - Final output (clearly marked)
    - Timing for each step
    """
    
    lines = []
    lines.append("")
    lines.append("AgentLedger Trace")
    lines.append(f"Trace ID: {trace.trace_id}")
    lines.append("─" * 50)
    
    # Process events into a causal chain
    events = trace.events
    i = 0
    
    while i < len(events):
        event = events[i]
        
        if event.event_type == "llm_start":
            # Find matching llm_end
            end_event = _find_end_event(events, i, event.event_id)
            
            # Determine if this LLM call has tool calls or is final
            tool_calls = []
            output_text = ""
            tokens_in = None
            tokens_out = None
            if end_event:
                tool_calls = end_event.data.get("tool_calls", [])
                response = end_event.data.get("response", {})
                output_text = _extract_response_text(response)
                tokens_in, tokens_out = _extract_token_usage(response)
            
            # Model and duration
            model = _shorten_model_name(event.data.get("model", "unknown"))
            duration = f"{end_event.duration_ms:.0f}ms" if end_event and end_event.duration_ms else "..."
            
            # LLM Call header
            lines.append("")
            lines.append(f"┌─ LLM Call ({model}) ─ {duration}")
            
            # Token usage if available
            if tokens_in is not None and tokens_out is not None:
                lines.append(f"│  Tokens: {tokens_in} in / {tokens_out} out")
            
            # Input (first user message)
            messages = event.data.get("messages", [])
            input_text = _extract_user_input(messages)
            if input_text:
                lines.append(f"│  Prompt: {_truncate(input_text, 45)}")
            
            # Tool request or final output
            if tool_calls:
                for idx, tc in enumerate(tool_calls):
                    name = tc.get("name", "unknown_tool")
                    args = tc.get("arguments", {})
                    args_str = _format_args(args)
                    tc_id = tc.get("id")
                    lines.append(f"│")
                    lines.append(f"└──► Tool Request: {name}({args_str})")
                    
                    # Look for tool result in the next LLM call's messages
                    tool_result = _find_tool_result_by_id(events, i, tc_id, name)
                    if tool_result:
                        lines.append(f"")
                        lines.append(f"     ┌─ Tool Execution: {name}")
                        lines.append(f"     │  Args: {args_str}")
                        lines.append(f"     └─ Result: {_truncate(str(tool_result), 40)}")
            else:
                # Final output (no tool calls) - mark it clearly
                if output_text:
                    lines.append(f"│")
                    lines.append(f"└──► Final Output:")
                    lines.append(f"     {_truncate(output_text, 45)}")
            
            # Skip to after end event
            if end_event:
                i = events.index(end_event) + 1
            else:
                i += 1
        
        elif event.event_type == "tool_execution":
            # Explicit tool execution events (if captured)
            name = event.data.get("name", "unknown")
            result = event.data.get("result", "")
            duration = f"{event.duration_ms:.0f}ms" if event.duration_ms else ""
            
            lines.append(f"")
            lines.append(f"┌─ Tool Execution: {name} ─ {duration}")
            lines.append(f"└─ Result: {_truncate(str(result), 45)}")
            i += 1
        
        elif event.event_type == "error":
            lines.append(f"")
            lines.append(f"┌─ Error ─────────────────────────")
            lines.append(f"│  {event.data.get('error_type')}")
            lines.append(f"└─ {_truncate(str(event.data.get('error_message')), 40)}")
            i += 1
        
        else:
            i += 1
    
    # Footer
    lines.append("")
    lines.append("─" * 50)
    duration = f"{trace.duration_ms:.0f}ms" if trace.duration_ms else "..."
    lines.append(f"Done ─ Total: {duration}")
    lines.append("")
    
    return "\n".join(lines)


def _find_end_event(events: List, start_idx: int, event_id: str):
    """Find the matching llm_end event."""
    for j in range(start_idx + 1, len(events)):
        if events[j].event_type == "llm_end" and events[j].parent_id == event_id:
            return events[j]
    return None


def _find_tool_result(events: List, current_idx: int, tool_name: str) -> Optional[str]:
    """
    Try to find the tool result from subsequent messages.
    
    Looks at the next LLM call's messages to find tool results.
    """
    for j in range(current_idx + 1, len(events)):
        if events[j].event_type == "llm_start":
            messages = events[j].data.get("messages", [])
            for msg in messages:
                if isinstance(msg, dict):
                    # OpenAI format: role=tool
                    role = msg.get("role", "")
                    if role in ("tool", "function"):
                        content = msg.get("content", "")
                        if content:
                            return content
                    
                    # Anthropic format: tool_result in content blocks
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict):
                                if block.get("type") == "tool_result":
                                    result_content = block.get("content", "")
                                    if isinstance(result_content, list):
                                        for sub in result_content:
                                            if isinstance(sub, dict) and sub.get("type") == "text":
                                                return sub.get("text", "")
                                    return result_content
            break
    return None


def _find_tool_result_by_id(events: List, current_idx: int, tool_call_id: Optional[str], tool_name: str) -> Optional[str]:
    """
    Find the tool result matching a specific tool call ID.
    
    Falls back to matching by tool name if ID not available.
    """
    for j in range(current_idx + 1, len(events)):
        if events[j].event_type == "llm_start":
            messages = events[j].data.get("messages", [])
            for msg in messages:
                if isinstance(msg, dict):
                    # OpenAI format: role=tool with tool_call_id
                    role = msg.get("role", "")
                    if role in ("tool", "function"):
                        msg_tool_id = msg.get("tool_call_id")
                        if tool_call_id and msg_tool_id == tool_call_id:
                            return msg.get("content", "")
                        # Fallback: if no ID match, return first tool result
                        if not tool_call_id:
                            return msg.get("content", "")
                    
                    # Anthropic format: tool_result in content blocks
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_result":
                                block_tool_id = block.get("tool_use_id")
                                if tool_call_id and block_tool_id == tool_call_id:
                                    result_content = block.get("content", "")
                                    return _extract_tool_result_content(result_content)
                                # Fallback
                                if not tool_call_id:
                                    result_content = block.get("content", "")
                                    return _extract_tool_result_content(result_content)
            break
    return None


def _extract_tool_result_content(content) -> str:
    """Extract text from tool result content (handles nested structures)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text", "")
        # Fallback: join all text
        texts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
        return " ".join(texts) if texts else str(content)
    return str(content)


def _extract_token_usage(response) -> tuple:
    """Extract token usage from response. Returns (input_tokens, output_tokens)."""
    if not response or not isinstance(response, dict):
        return None, None
    
    # OpenAI format
    usage = response.get("usage", {})
    if usage:
        return usage.get("prompt_tokens"), usage.get("completion_tokens")
    
    # Anthropic format
    usage = response.get("usage", {})
    if usage:
        return usage.get("input_tokens"), usage.get("output_tokens")
    
    return None, None


def _shorten_model_name(model: str) -> str:
    """Shorten model names for display."""
    replacements = {
        "claude-haiku-4-5-20251001": "Claude Haiku",
        "claude-sonnet-4-5-20251001": "Claude Sonnet", 
        "claude-opus-4-5-20251001": "Claude Opus",
        "claude-3-5-sonnet": "Claude 3.5 Sonnet",
        "claude-3-5-haiku": "Claude 3.5 Haiku",
        "gpt-4o-mini": "GPT-4o Mini",
        "gpt-4o": "GPT-4o",
        "gpt-4-turbo": "GPT-4 Turbo",
        "gpt-4": "GPT-4",
        "gpt-3.5-turbo": "GPT-3.5",
    }
    
    for long, short in replacements.items():
        if long in model:
            return short
    
    if len(model) > 20:
        return model[:17] + "..."
    return model


def _extract_user_input(messages) -> str:
    """Extract the user's input from messages."""
    if not messages:
        return ""
    
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "")
                if role == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        return content
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                return block.get("text", "")
    
    return ""


def _extract_response_text(response) -> str:
    """Extract text from an LLM response."""
    if not response:
        return ""
    
    if isinstance(response, str):
        return response
    
    if isinstance(response, dict):
        # OpenAI format
        choices = response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            if content:
                return content
        
        # Anthropic format
        content = response.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
        
        if "content" in response and isinstance(response["content"], str):
            return response["content"]
    
    return ""


def _format_args(args) -> str:
    """Format tool arguments for display."""
    if not args:
        return ""
    
    if isinstance(args, str):
        try:
            import json
            args = json.loads(args)
        except:
            return _truncate(args, 35)
    
    if isinstance(args, dict):
        parts = []
        for k, v in list(args.items())[:3]:
            if isinstance(v, str):
                v_str = f'"{_truncate(v, 15)}"'
            else:
                v_str = str(v)
            parts.append(f'{k}={v_str}')
        result = ", ".join(parts)
        if len(args) > 3:
            result += ", ..."
        return result
    
    return str(args)[:35]


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    text = str(text).replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
