# AgentLedger

**See what your AI agent actually did.**

```python
import agentledger
agentledger.auto_instrument()

# Your existing agent code — unchanged
agent.run("Find the best flight to NYC")
```

Output:

```
AgentLedger Trace
─────────────────────────────────────────────────────
├─► LLM Call (gpt-4o) ─────────────────── 1,247ms
│   Input: "Find the best flight to NYC"
│   Tool Request: search_flights(destination="NYC")
│
├─► Tool: search_flights ──────────────── 892ms
│   Input: {"destination": "NYC"}
│   Result: [{"flight": "AA203", "price": 420}]
│
├─► LLM Call (gpt-4o) ─────────────────── 634ms
│   Output: "Flight AA203 at $420 is the best option"
│
└─► Done ──────────────────────────────── 2,773ms total
```

## The Problem

Your AI agent did something unexpected. Now what?

- Check logs → useless, just says "tool called"
- Check LLM traces → shows prompt/response, not the decision chain
- Add print statements → redeploy, wait, pray
- Ask the agent → it hallucinates an explanation

**AgentLedger answers one question: "Why did my agent do that?"**

## Install

```bash
pip install agentledger
```

## Quick Start

```python
import agentledger
agentledger.auto_instrument()

# That's it. Your agent code stays exactly the same.
# AgentLedger automatically traces all LLM calls and tool usage.
```

## What Gets Captured

| Event | Captured |
|-------|----------|
| LLM prompts | ✓ |
| LLM responses | ✓ |
| Tool calls | ✓ |
| Tool arguments | ✓ |
| Tool results | ✓ |
| Timing | ✓ |
| Errors | ✓ |

## Supported Providers

- [x] OpenAI
- [x] Anthropic
- [ ] LiteLLM (coming soon)
- [ ] Azure OpenAI (coming soon)

## Framework Agnostic

Works with any agent framework:

- LangChain
- CrewAI
- AutoGen
- Custom implementations

AgentLedger patches at the LLM client level, so it captures everything regardless of which framework you use.

## API

```python
import agentledger

# Start auto-instrumentation
agentledger.auto_instrument()

# Get the last trace
trace = agentledger.get_last_trace()

# Print it again
print(trace.explain())

# Access raw events
for event in trace.events:
    print(event.type, event.duration_ms)
```

## Configuration

```python
agentledger.auto_instrument(
    print_traces=True,      # Auto-print to console (default: True)
    capture_inputs=True,    # Capture full prompts (default: True)
    capture_outputs=True,   # Capture full responses (default: True)
)
```

## Why Not LangSmith / OpenTelemetry / etc?

| Tool | Limitation |
|------|------------|
| LangSmith | LangChain only |
| OpenTelemetry | Doesn't understand agent semantics |
| Datadog | No concept of "agent decision" |
| Print statements | Manual, incomplete, painful |

AgentLedger is **framework-agnostic** and **agent-aware**.

## Roadmap

- [x] OpenAI instrumentation
- [x] Anthropic instrumentation
- [ ] LiteLLM support
- [ ] Structured event export (JSON)
- [ ] Framework adapters (LangChain, CrewAI)
- [ ] `explain(action_id)` for deep inspection
- [ ] Policy violations detection
- [ ] Dashboard (optional hosted)

## License

MIT

## Contributing

Issues and PRs welcome. This is early — feedback shapes the direction.
