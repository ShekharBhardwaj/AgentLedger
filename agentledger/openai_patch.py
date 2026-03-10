"""
OpenAI client patch.

Instruments openai.chat.completions.create to capture LLM calls.
"""

from typing import TYPE_CHECKING
import functools

if TYPE_CHECKING:
    from ..tracer import Tracer

_patched = False


def patch(tracer: "Tracer") -> None:
    """Patch the OpenAI client to capture LLM calls."""
    global _patched
    
    if _patched:
        return
    
    try:
        import openai
    except ImportError:
        # OpenAI not installed, skip
        return
    
    _patch_chat_completions(tracer, openai)
    _patched = True


def _patch_chat_completions(tracer: "Tracer", openai_module) -> None:
    """Patch chat.completions.create method."""
    
    try:
        # Get the Completions class
        original_create = openai_module.resources.chat.completions.Completions.create
    except AttributeError:
        # API structure might be different, skip
        return
    
    @functools.wraps(original_create)
    def patched_create(self, *args, **kwargs):
        # Extract relevant info
        model = kwargs.get("model", "unknown")
        messages = kwargs.get("messages", [])
        
        # Record start
        event_id = tracer.record_llm_start(
            model=model,
            messages=messages,
            provider="openai",
        )
        
        try:
            # Call original
            response = original_create(self, *args, **kwargs)
            
            # Extract tool calls if present
            tool_calls = _extract_tool_calls(response)
            
            # Record end
            tracer.record_llm_end(
                event_id=event_id,
                response=_serialize_response(response),
                tool_calls=tool_calls,
            )
            
            return response
            
        except Exception as e:
            tracer.record_error(e, context="openai.chat.completions.create")
            raise
    
    # Apply patch
    openai_module.resources.chat.completions.Completions.create = patched_create
    
    # Also patch async version if available
    try:
        original_acreate = openai_module.resources.chat.completions.AsyncCompletions.create
        
        @functools.wraps(original_acreate)
        async def patched_acreate(self, *args, **kwargs):
            model = kwargs.get("model", "unknown")
            messages = kwargs.get("messages", [])
            
            event_id = tracer.record_llm_start(
                model=model,
                messages=messages,
                provider="openai",
            )
            
            try:
                response = await original_acreate(self, *args, **kwargs)
                tool_calls = _extract_tool_calls(response)
                
                tracer.record_llm_end(
                    event_id=event_id,
                    response=_serialize_response(response),
                    tool_calls=tool_calls,
                )
                
                return response
                
            except Exception as e:
                tracer.record_error(e, context="openai.chat.completions.create (async)")
                raise
        
        openai_module.resources.chat.completions.AsyncCompletions.create = patched_acreate
        
    except AttributeError:
        pass


def _extract_tool_calls(response) -> list:
    """Extract tool calls from OpenAI response."""
    tool_calls = []
    
    try:
        if hasattr(response, 'choices') and response.choices:
            message = response.choices[0].message
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id if hasattr(tc, 'id') else None,
                        "name": tc.function.name if hasattr(tc, 'function') else None,
                        "arguments": tc.function.arguments if hasattr(tc, 'function') else None,
                    })
    except Exception:
        pass
    
    return tool_calls


def _serialize_response(response) -> dict:
    """Serialize OpenAI response to dict."""
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
