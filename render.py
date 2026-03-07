"""
Console renderer for traces.

Pretty-prints traces in a tree format.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tracer import Trace, TraceEvent


def render_trace(trace: "Trace") -> str:
    """Render a trace as a human-readable tree string."""
    
    lines = []
    lines.append("")
    lines.append("AgentLedger Trace")
    lines.append("─" * 55)
    
    # Group events into LLM call pairs
    i = 0
    events = trace.events
    event_count = 0
    
    while i < len(events):
        event = events[i]
        
        if event.event_type == "llm_start":
            # Find matching llm_end
            end_event = None
            for j in range(i + 1, len(events)):
                if events[j].event_type == "llm_end" and events[j].parent_id == event.event_id:
                    end_event = events[j]
                    break
            
            event_count += 1
            is_last = (i >= len(events) - 2) or (end_event and not end_event.data.get("tool_calls"))
            prefix = "└─►" if is_last else "├─►"
            
            # Model and duration
            model = event.data.get("model", "unknown")
            duration = f"{end_event.duration_ms:.0f}ms" if end_event and end_event.duration_ms else "..."
            
            lines.append(f"{prefix} LLM Call ({model}) {'─' * (20 - len(model))} {duration}")
            
            # Input (first user message or summary)
            messages = event.data.get("messages", [])
            input_text = _extract_user_input(messages)
            if input_text:
                connector = "│" if not is_last else " "
                lines.append(f"{connector}   Input: {_truncate(input_text, 50)}")
            
            # Output and tool calls from end event
            if end_event:
                response = end_event.data.get("response", {})
                output_text = _extract_response_text(response)
                tool_calls = end_event.data.get("tool_calls", [])
                
                connector = "│" if not is_last else " "
                
                if output_text and not tool_calls:
                    lines.append(f"{connector}   Output: {_truncate(output_text, 50)}")
                
                for tc in tool_calls:
                    name = tc.get("name", "unknown_tool")
                    args = tc.get("arguments", {})
                    args_str = _format_args(args)
                    lines.append(f"{connector}   Tool Request: {name}({args_str})")
            
            lines.append("│")
            
            # Skip to after end event
            if end_event:
                i = events.index(end_event) + 1
            else:
                i += 1
        
        elif event.event_type == "error":
            lines.append(f"├─► Error ─────────────────────────────────")
            lines.append(f"│   {event.data.get('error_type')}: {event.data.get('error_message')}")
            lines.append("│")
            i += 1
        
        else:
            i += 1
    
    # Footer
    duration = f"{trace.duration_ms:.0f}ms" if trace.duration_ms else "..."
    lines.append(f"└─► Done {'─' * 36} {duration} total")
    lines.append("")
    
    return "\n".join(lines)


def _extract_user_input(messages) -> str:
    """Extract the user's input from messages."""
    if not messages:
        return ""
    
    if isinstance(messages, list):
        for msg in reversed(messages):
            if isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user" and content:
                    if isinstance(content, str):
                        return content
                    if isinstance(content, list):
                        # Handle content blocks
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
        
        # Direct content
        if "content" in response and isinstance(response["content"], str):
            return response["content"]
    
    return ""


def _format_args(args) -> str:
    """Format tool arguments for display."""
    if not args:
        return ""
    
    if isinstance(args, str):
        # Try to parse JSON string
        try:
            import json
            args = json.loads(args)
        except:
            return _truncate(args, 40)
    
    if isinstance(args, dict):
        parts = []
        for k, v in list(args.items())[:3]:  # Max 3 args shown
            v_str = str(v) if not isinstance(v, str) else f'"{v}"'
            parts.append(f'{k}={_truncate(v_str, 20)}')
        result = ", ".join(parts)
        if len(args) > 3:
            result += ", ..."
        return result
    
    return str(args)[:40]


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
