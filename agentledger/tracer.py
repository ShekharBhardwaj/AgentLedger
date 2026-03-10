"""
Core tracer implementation.

Handles event capture, trace management, and thread-local storage.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from contextlib import contextmanager


@dataclass
class TracerConfig:
    """Configuration for the tracer."""
    print_traces: bool = True
    capture_inputs: bool = True
    capture_outputs: bool = True


@dataclass
class TraceEvent:
    """A single event in the agent execution trace."""
    
    event_type: str  # "llm_start", "llm_end", "tool_call", "error"
    timestamp: float
    data: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    duration_ms: Optional[float] = None
    parent_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "parent_id": self.parent_id,
            "data": self.data,
        }


@dataclass
class Trace:
    """A complete trace of an agent execution."""
    
    trace_id: str
    events: List[TraceEvent] = field(default_factory=list)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    @property
    def duration_ms(self) -> Optional[float]:
        """Total duration in milliseconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return None
    
    def add_event(self, event: TraceEvent) -> None:
        """Add an event to the trace."""
        if not self.start_time:
            self.start_time = event.timestamp
        self.events.append(event)
        self.end_time = event.timestamp
    
    def explain(self) -> str:
        """Render the trace as a human-readable string."""
        from .render import render_trace
        return render_trace(self)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "trace_id": self.trace_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "events": [e.to_dict() for e in self.events],
        }


class Tracer:
    """
    Main tracer class.
    
    Manages traces and provides methods for recording events.
    Uses thread-local storage for trace context.
    """
    
    def __init__(self):
        self.config = TracerConfig()
        self._local = threading.local()
        self._traces: List[Trace] = []
        self._lock = threading.Lock()
    
    @property
    def current_trace(self) -> Optional[Trace]:
        """Get the current trace for this thread."""
        return getattr(self._local, 'trace', None)
    
    def _ensure_trace(self) -> Trace:
        """Ensure a trace exists for the current thread."""
        if not self.current_trace:
            trace = Trace(trace_id=str(uuid.uuid4())[:12])
            self._local.trace = trace
            with self._lock:
                self._traces.append(trace)
        return self.current_trace
    
    def record_llm_start(
        self,
        model: str,
        messages: Any,
        **kwargs
    ) -> str:
        """Record the start of an LLM call. Returns event_id."""
        trace = self._ensure_trace()
        
        data = {
            "model": model,
            "provider": kwargs.get("provider", "unknown"),
        }
        
        if self.config.capture_inputs:
            data["messages"] = self._safe_serialize(messages)
        
        event = TraceEvent(
            event_type="llm_start",
            timestamp=time.time(),
            data=data,
        )
        
        trace.add_event(event)
        return event.event_id
    
    def record_llm_end(
        self,
        event_id: str,
        response: Any,
        tool_calls: Optional[List[Dict]] = None,
        **kwargs
    ) -> None:
        """Record the end of an LLM call."""
        trace = self.current_trace
        if not trace:
            return
        
        # Find the start event
        start_event = None
        for event in trace.events:
            if event.event_id == event_id:
                start_event = event
                break
        
        data = {}
        
        if self.config.capture_outputs:
            data["response"] = self._safe_serialize(response)
        
        if tool_calls:
            data["tool_calls"] = tool_calls
        
        duration_ms = None
        if start_event:
            duration_ms = (time.time() - start_event.timestamp) * 1000
        
        event = TraceEvent(
            event_type="llm_end",
            timestamp=time.time(),
            data=data,
            duration_ms=duration_ms,
            parent_id=event_id,
        )
        
        trace.add_event(event)
        
        # Print trace if configured
        if self.config.print_traces:
            self._maybe_print_trace()
    
    def record_error(self, error: Exception, context: Optional[str] = None) -> None:
        """Record an error event."""
        trace = self._ensure_trace()
        
        event = TraceEvent(
            event_type="error",
            timestamp=time.time(),
            data={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context,
            },
        )
        
        trace.add_event(event)
    
    def _safe_serialize(self, obj: Any) -> Any:
        """Safely serialize an object for storage."""
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, (list, tuple)):
            return [self._safe_serialize(item) for item in obj]
        if isinstance(obj, dict):
            return {k: self._safe_serialize(v) for k, v in obj.items()}
        # For objects, try to extract useful info
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        if hasattr(obj, '__dict__'):
            return {k: self._safe_serialize(v) for k, v in obj.__dict__.items() 
                    if not k.startswith('_')}
        return str(obj)
    
    def _maybe_print_trace(self) -> None:
        """Print the current trace if it looks complete."""
        trace = self.current_trace
        if not trace or not trace.events:
            return
        
        # Simple heuristic: print after each LLM end that doesn't have pending tool calls
        last_event = trace.events[-1]
        if last_event.event_type == "llm_end":
            tool_calls = last_event.data.get("tool_calls", [])
            if not tool_calls:
                # No pending tool calls, trace might be complete
                print(trace.explain())
    
    def get_last_trace(self) -> Optional[Trace]:
        """Get the most recent trace."""
        with self._lock:
            if self._traces:
                return self._traces[-1]
        return None
    
    def clear(self) -> None:
        """Clear all traces."""
        with self._lock:
            self._traces.clear()
        self._local.trace = None


# Global tracer instance
_tracer: Optional[Tracer] = None


def get_tracer() -> Tracer:
    """Get the global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer


def get_last_trace() -> Optional[Trace]:
    """Get the most recent trace."""
    return get_tracer().get_last_trace()
