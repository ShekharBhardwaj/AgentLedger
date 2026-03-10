"""
Anthropic client patch.

Instruments anthropic.messages.create to capture LLM calls.
"""

from typing import TYPE_CHECKING
import functools

if TYPE_CHECKING:
    from ..tracer import Tracer

_patched = False


def patch(tracer: "Tracer") -> None:
    """Patch the Anthropic client to capture LLM calls."""
    global _patched
    
    if _patched:
        return
    
    try:
        import anthropic
    except ImportError:
        # Anthropic not installed, skip
        return
    
    _patch_messages(tracer, anthropic)
    _patched = True


def _patch_messages(tracer: "Tracer", anthropic_module) -> None:
    """Patch messages.create method."""
    
    try:
        original_create = anthropic_module.resources.messages.Messages.create
    except AttributeError:
        return
    
    @functools.wraps(original_create)
    def patched_create(self, *args, **kwargs):
        model = kwargs.get("model", "unknown")
        messages = kwargs.get("messages", [])
        system = kwargs.get("system", None)
        
        # Include system prompt in messages for tracing
        trace_messages = messages
        if system:
            trace_messages = [{"role": "system", "content": system}] + list(messages)
        
        event_id = tracer.record_llm_start(
            model=model,
            messages=trace_messages,
            provider="anthropic",
        )
        
        try:
            response = original_create(self, *args, **kwargs)
            tool_calls = _extract_tool_use(response)
            
            tracer.record_llm_end(
                event_id=event_id,
                response=_serialize_response(response),
                tool_calls=tool_calls,
            )
            
            return response
            
        except Exception as e:
            tracer.record_error(e, context="anthropic.messages.create")
            raise
    
    anthropic_module.resources.messages.Messages.create = patched_create
    
    # Patch async version
    try:
        original_acreate = anthropic_module.resources.messages.AsyncMessages.create
        
        @functools.wraps(original_acreate)
        async def patched_acreate(self, *args, **kwargs):
            model = kwargs.get("model", "unknown")
            messages = kwargs.get("messages", [])
            system = kwargs.get("system", None)
            
            trace_messages = messages
            if system:
                trace_messages = [{"role": "system", "content": system}] + list(messages)
            
            event_id = tracer.record_llm_start(
                model=model,
                messages=trace_messages,
                provider="anthropic",
            )
            
            try:
                response = await original_acreate(self, *args, **kwargs)
                tool_calls = _extract_tool_use(response)
                
                tracer.record_llm_end(
                    event_id=event_id,
                    response=_serialize_response(response),
                    tool_calls=tool_calls,
                )
                
                return response
                
            except Exception as e:
                tracer.record_error(e, context="anthropic.messages.create (async)")
                raise
        
        anthropic_module.resources.messages.AsyncMessages.create = patched_acreate
        
    except AttributeError:
        pass


def _extract_tool_use(response) -> list:
    """Extract tool use blocks from Anthropic response."""
    tool_calls = []
    
    try:
        if hasattr(response, 'content'):
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'tool_use':
                    tool_calls.append({
                        "id": block.id if hasattr(block, 'id') else None,
                        "name": block.name if hasattr(block, 'name') else None,
                        "arguments": block.input if hasattr(block, 'input') else None,
                    })
    except Exception:
        pass
    
    return tool_calls


def _serialize_response(response) -> dict:
    """Serialize Anthropic response to dict."""
    try:
        if hasattr(response, 'model_dump'):
            return response.model_dump()
        if hasattr(response, 'to_dict'):
            return response.to_dict()
        if hasattr(response, '__dict__'):
            return dict(response.__dict__)
    except Exception:
        pass
    
    return {"raw": str(response)}
