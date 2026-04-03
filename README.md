# AgentLedger

**Runtime observability for AI agents. See exactly why your agent did what it did.**

Point your agent at AgentLedger instead of LiteLLM. Every LLM call is captured, stored, and retrievable by action ID — no code changes to your agent required.

---

## How it works

```
Your Agent → AgentLedger Proxy → LiteLLM → Any Model
                    ↓
               Postgres (canonical trace)
```

AgentLedger intercepts HTTP traffic at the network level. It works with any agent framework, any model, any gateway.

---

## Install

```bash
pip install "git+https://github.com/ShekharBhardwaj/AgentLedger.git[proxy]"
```

---

## Quick Start

**1. Start the proxy**

```bash
AGENTLEDGER_UPSTREAM_URL=http://localhost:4000 \
AGENTLEDGER_PG_DSN=postgresql://user:pass@localhost/agentledger \
python -m agentledger.proxy
```

**2. Point your agent at the proxy instead of LiteLLM**

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-key",
)

# Your agent code is unchanged from here
```

**3. Retrieve what happened**

Every response includes an `x-agentledger-action-id` header. Use it to pull the full trace:

```bash
curl http://localhost:8000/explain/<action_id>
```

---

## Sessions

Group all LLM calls from a single agent run under one session ID:

```python
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-key",
    default_headers={"x-agentledger-session-id": "run-42"},
)
```

Retrieve the full decision chain for that run:

```bash
curl http://localhost:8000/session/run-42
```

Returns all calls in order, with prompts, tool calls, responses, and timing.

---

## What gets captured

Every intercepted call is normalized to a canonical schema and stored in Postgres:

| Field | Description |
|---|---|
| `action_id` | UUID assigned at interception time |
| `session_id` | Caller-supplied run identifier (optional) |
| `messages` | Full prompt including system prompt |
| `tools` | Tool definitions passed to the model |
| `content` | Model's text response |
| `tool_calls` | Tool calls the model requested |
| `stop_reason` | Why the model stopped |
| `tokens_in / tokens_out` | Token usage |
| `latency_ms` | End-to-end call time |

---

## Provider support

The proxy normalizes all provider formats internally. It works with anything LiteLLM supports — OpenAI, Anthropic, Azure, Gemini, local models, and more.

Direct Anthropic (`POST /v1/messages`) is also intercepted if you route it through the proxy.

---

## API reference

| Endpoint | Description |
|---|---|
| `POST /v1/chat/completions` | Proxied + captured |
| `POST /v1/messages` | Proxied + captured (Anthropic) |
| `GET /explain/{action_id}` | Retrieve a single captured call |
| `GET /session/{session_id}` | Retrieve all calls in a run, ordered by time |

---

## Configuration

| Env var | Default | Description |
|---|---|---|
| `AGENTLEDGER_UPSTREAM_URL` | `http://localhost:4000` | LiteLLM base URL |
| `AGENTLEDGER_PG_DSN` | *(required)* | Postgres connection string |
| `AGENTLEDGER_HOST` | `0.0.0.0` | Proxy bind host |
| `AGENTLEDGER_PORT` | `8000` | Proxy bind port |

---

## MCP tool server

AgentLedger exposes its retrieval tools as an MCP server at `POST /mcp`.

Configure in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentledger": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Available tools: `explain(action_id)`, `get_session(session_id)`.

---

## Roadmap

- [x] Transparent HTTP proxy
- [x] Canonical schema normalization (OpenAI + Anthropic)
- [x] Postgres storage
- [x] `explain(action_id)` retrieval
- [x] Session grouping
- [x] Streaming capture
- [x] MCP tool layer
- [ ] Dashboard

---

## License

MIT
