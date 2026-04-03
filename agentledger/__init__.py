"""
AgentLedger - See what your AI agent actually did.

Usage:
    import agentledger
    agentledger.auto_instrument()
    
    # Your agent code runs normally
    # AgentLedger prints the decision trace automatically
"""

from .tracer import Tracer, Trace, TraceEvent, get_tracer, get_last_trace
from .render import render_trace

__version__ = "0.1.0"
__all__ = [
    "auto_instrument",
    "get_last_trace",
    "get_tracer",
    "render_trace",
    "Trace",
    "TraceEvent",
]

_instrumented = False


def auto_instrument(
    print_traces: bool = True,
    capture_inputs: bool = True,
    capture_outputs: bool = True,
) -> None:
    """
    Automatically instrument LLM clients to capture agent execution traces.
    
    Call this once at the start of your program:
    
        import agentledger
        agentledger.auto_instrument()
    
    Args:
        print_traces: Print traces to console when complete (default: True)
        capture_inputs: Capture full prompts/inputs (default: True)
        capture_outputs: Capture full responses/outputs (default: True)
    """
    global _instrumented
    
    if _instrumented:
        return
    
    tracer = get_tracer()
    tracer.config.print_traces = print_traces
    tracer.config.capture_inputs = capture_inputs
    tracer.config.capture_outputs = capture_outputs
    
    # Patch supported clients
    from . import openai_patch, anthropic_patch
    
    openai_patch.patch(tracer)
    anthropic_patch.patch(tracer)
    
    _instrumented = True
