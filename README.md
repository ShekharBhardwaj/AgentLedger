# AgentLedger

See exactly what your AI agent did and why.

Works with any agent framework, any LLM provider, any model gateway — zero code changes required. Point your agent at the proxy and everything is captured automatically.

---

## Quick Start

**1. Start the proxy**

With Docker (no Python required):
```bash
docker run -p 8000:8000 \
  -e AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
  -v $(pwd)/data:/data \
  ghcr.io/shekharBhardwaj/agentledger:latest
```

Or with `uv`:
```bash
uv add "agentledger @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com uv run python -m agentledger.proxy
```

Or with `pip`:
```bash
python -m venv venv && source venv/bin/activate
pip install "agentledger @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com ./venv/bin/python -m agentledger.proxy
```

Proxy starts on `http://localhost:8000`. Traces are saved to `agentledger.db` in your current folder (or `/data/agentledger.db` in Docker).

**2. Point your agent at the proxy**

Change `base_url` to the proxy and add a session ID header. Everything else stays the same.

OpenAI:
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-openai-key",
    default_headers={"x-agentledger-session-id": "run-1"},
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What is 2 + 2?"}],
)
```

Anthropic:
```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",
    api_key="your-anthropic-key",
    default_headers={"x-agentledger-session-id": "run-1"},
)
```

**3. See what happened**

Open the dashboard — it updates live as calls come in:
```
http://localhost:8000
```

- **Calls tab** — every LLM call with full prompts, tool calls, tool results, cost, latency, and errors
- **Flow tab** — visual DAG of your multi-agent flow with cost and latency per agent. Click a node to highlight its calls.
- **Search** — find any call by prompt, output, or agent name across all sessions

Or query directly:
```bash
# All calls in a session
curl http://localhost:8000/session/run-1

# Search
curl "http://localhost:8000/api/search?q=tool+failed"

# Download JSON compliance export (includes SHA-256 integrity hash)
curl http://localhost:8000/export/run-1 -o run-1.json

# Printable HTML audit report
open http://localhost:8000/export/run-1/report
```

---

## What gets captured

Every LLM call through the proxy is stored with:

- **Full prompt** — messages, system prompt, tools available, temperature, max tokens
- **Full response** — output text, tool calls made, stop reason
- **Tool results** — what tools returned, fed back into the next call
- **Token usage and cost** — per call and aggregated per session
- **Latency** — end-to-end response time
- **Errors** — non-200 responses captured with the upstream error message
- **Agent metadata** — name, user, environment, parent call, handoffs (from request headers)

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Live dashboard |
| `WS` | `/ws` | WebSocket event stream (powers live updates) |
| `GET` | `/api/sessions` | List recent sessions |
| `GET` | `/api/search?q=...` | Full-text search across all captured calls |
| `GET` | `/session/{session_id}` | All calls in a session, ordered by time |
| `GET` | `/explain/{action_id}` | Single captured call by action ID |
| `GET` | `/export/{session_id}` | JSON compliance export with SHA-256 integrity hash |
| `GET` | `/export/{session_id}/report` | Printable HTML audit report |
| `POST` | `/mcp` | MCP tool server |

---

## Configuration

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENTLEDGER_UPSTREAM_URL` | **Yes** | `https://api.openai.com` | Where to forward LLM requests. Supports OpenAI, Anthropic, LiteLLM, OpenRouter, or any OpenAI-compatible URL. |
| `AGENTLEDGER_DSN` | No | `sqlite:///agentledger.db` | Database. SQLite for local dev, Postgres URL for production. |
| `AGENTLEDGER_HOST` | No | `0.0.0.0` | Host to bind to. Use `127.0.0.1` to restrict to localhost only. |
| `AGENTLEDGER_PORT` | No | `8000` | Port to run on. |
| `AGENTLEDGER_API_KEY` | No | _(none)_ | Protects the dashboard and all read endpoints. Skip for local dev. Set it when the proxy is exposed on a server — you choose the value. |
| `AGENTLEDGER_BUDGET_SESSION` | No | _(none)_ | Max USD spend per `session_id`. Calls that exceed this return HTTP 429. |
| `AGENTLEDGER_BUDGET_AGENT` | No | _(none)_ | Max USD per agent name per calendar day (UTC). |
| `AGENTLEDGER_BUDGET_DAILY` | No | _(none)_ | Max USD total across all calls per calendar day (UTC). |

**Common setups:**

```bash
# Local dev — Anthropic
AGENTLEDGER_UPSTREAM_URL=https://api.anthropic.com uv run python -m agentledger.proxy

# Local dev — LiteLLM (any model via one gateway)
AGENTLEDGER_UPSTREAM_URL=http://localhost:4000 uv run python -m agentledger.proxy

# Production — Postgres + auth + spend limits
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
AGENTLEDGER_DSN=postgresql://user:password@localhost/agentledger \
AGENTLEDGER_API_KEY=my-secret \
AGENTLEDGER_BUDGET_DAILY=10.00 \
AGENTLEDGER_BUDGET_SESSION=1.00 \
uv run python -m agentledger.proxy
```

With docker compose (edit `docker-compose.yml` to uncomment Postgres):
```bash
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
AGENTLEDGER_API_KEY=my-secret \
docker compose up
```

When `AGENTLEDGER_API_KEY` is set, pass it to access protected endpoints:
```bash
curl -H "x-agentledger-api-key: my-secret" http://localhost:8000/session/run-1
# or in a browser: http://localhost:8000?api_key=my-secret
```

---

### Request headers

Pass these from your agent on each LLM call. All are optional.

| Header | Default | Description |
|---|---|---|
| `x-agentledger-session-id` | _(none)_ | Groups all calls in a run. Use a consistent ID per execution (e.g. `"run-1"`, a UUID). Without this, calls are stored but not grouped. |
| `x-agentledger-user-id` | _(none)_ | The end user who triggered this run. Useful for per-user auditing. |
| `x-agentledger-agent-name` | _(none)_ | Name of the agent making this call (e.g. `"researcher"`). Powers the Flow tab and agent-level budget tracking. |
| `x-agentledger-app-id` | _(none)_ | Application name or ID. Useful if multiple apps share one proxy. |
| `x-agentledger-parent-action-id` | _(none)_ | The `action_id` returned from the parent call. Used to build nested agent call graphs. |
| `x-agentledger-environment` | `development` | `production`, `staging`, or `development`. |
| `x-agentledger-handoff-from` | _(none)_ | Agent handing off control (e.g. `"orchestrator"`). Renders as an edge in the Flow DAG. |
| `x-agentledger-handoff-to` | _(none)_ | Agent receiving control (e.g. `"researcher"`). Renders as an edge in the Flow DAG. |

**Fully annotated example:**

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-openai-key",
    default_headers={
        "x-agentledger-session-id":   "run-abc123",
        "x-agentledger-user-id":      "user-42",
        "x-agentledger-agent-name":   "researcher",
        "x-agentledger-app-id":       "my-app",
        "x-agentledger-environment":  "production",
    },
)
```

**Multi-agent handoff tracking:**

```python
# When orchestrator hands off to researcher
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-openai-key",
    default_headers={
        "x-agentledger-session-id":   "run-abc123",
        "x-agentledger-agent-name":   "researcher",
        "x-agentledger-handoff-from": "orchestrator",
        "x-agentledger-handoff-to":   "researcher",
    },
)
```

The Flow tab will render `orchestrator → researcher` as a DAG node with arrows, cost, and latency on each agent.

---

## License

MIT
