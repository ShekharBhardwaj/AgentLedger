# AgentLedger

See exactly what your AI agent did and why.

Works with any agent framework, any LLM provider, any model gateway — no code changes required. Just point your agent at the proxy.

---

## Quick Start

**1. Install**

With `uv` (recommended):
```bash
uv add "agentledger @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"
```

With `pip`:
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install "agentledger @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"
```

**2. Start the proxy**

Open a terminal and keep it running:

```bash
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com uv run python -m agentledger.proxy
```

With `pip`:
```bash
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com ./venv/bin/python -m agentledger.proxy
```

Proxy starts on `http://localhost:8000`. Traces are saved to `agentledger.db` in your current folder.

**3. Point your agent at the proxy**

Two changes — `base_url` and a session ID:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-openai-key",
    default_headers={"x-agentledger-session-id": "run-1"},
)

# Everything else stays exactly the same
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What is 2 + 2?"}],
)
```

**4. See what happened**

Open the live dashboard:
```
http://localhost:8000
```

The dashboard updates in real time as calls come in. Use the search bar to find any call by prompt, output, or agent name.

---

## Using Anthropic?

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",
    api_key="your-anthropic-key",
    default_headers={"x-agentledger-session-id": "run-1"},
)
```

---

## Using Postgres in production?

```bash
uv add "agentledger[postgres] @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"

AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
AGENTLEDGER_DSN=postgresql://user:password@localhost/agentledger \
uv run python -m agentledger.proxy
```

---

## What gets captured

Every LLM call through the proxy is stored with:

- Full prompt — messages, system prompt, tools available
- Full response — output text, tool calls made, stop reason
- Tool results — what the tools returned, fed into the next call
- Token usage and cost — per call and aggregated per session
- Latency — end-to-end response time
- Errors — non-200 responses from the upstream with the error detail
- Metadata — agent name, user, environment, handoffs (from request headers)

---

## API endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Live dashboard |
| `WS` | `/ws` | WebSocket event stream (used by dashboard) |
| `GET` | `/api/sessions` | List recent sessions |
| `GET` | `/api/search?q=...` | Full-text search across all captured calls |
| `GET` | `/session/{session_id}` | All calls in a session, ordered by time |
| `GET` | `/explain/{action_id}` | Single captured call by action ID |
| `GET` | `/export/{session_id}` | JSON compliance export with SHA-256 integrity hash |
| `GET` | `/export/{session_id}/report` | Printable HTML audit report |
| `POST` | `/mcp` | MCP tool server |

**Examples:**

```bash
# All calls in a session
curl http://localhost:8000/session/run-1

# Search
curl "http://localhost:8000/api/search?q=tool+failed"

# Download JSON audit trail
curl http://localhost:8000/export/run-1 -o run-1.json

# Open printable HTML report (print to PDF from browser)
open http://localhost:8000/export/run-1/report
```

---

## Configuration

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENTLEDGER_UPSTREAM_URL` | **Yes** | `https://api.openai.com` | Where to forward LLM requests. Can be OpenAI, Anthropic, LiteLLM, OpenRouter, or any OpenAI-compatible URL. |
| `AGENTLEDGER_DSN` | No | `sqlite:///agentledger.db` | Database. SQLite for local dev, Postgres URL for production. |
| `AGENTLEDGER_HOST` | No | `0.0.0.0` | Host to bind to. Use `127.0.0.1` to restrict to localhost only. |
| `AGENTLEDGER_PORT` | No | `8000` | Port to run on. |
| `AGENTLEDGER_API_KEY` | No | _(none)_ | Protects the dashboard and all read endpoints. Optional — skip for local dev, set it when running on a server. You choose the value. |
| `AGENTLEDGER_BUDGET_SESSION` | No | _(none)_ | Max USD spend per `session_id`. Calls that would exceed this return HTTP 429. |
| `AGENTLEDGER_BUDGET_AGENT` | No | _(none)_ | Max USD per agent name per calendar day (UTC). |
| `AGENTLEDGER_BUDGET_DAILY` | No | _(none)_ | Max USD total across all calls per calendar day (UTC). |

**Examples:**

```bash
# Local dev — OpenAI
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com uv run python -m agentledger.proxy

# Local dev — Anthropic
AGENTLEDGER_UPSTREAM_URL=https://api.anthropic.com uv run python -m agentledger.proxy

# Local dev — LiteLLM (any model)
AGENTLEDGER_UPSTREAM_URL=http://localhost:4000 uv run python -m agentledger.proxy

# Custom port
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
AGENTLEDGER_PORT=9000 \
uv run python -m agentledger.proxy

# Production — Postgres, auth, cost budgets
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
AGENTLEDGER_DSN=postgresql://user:password@localhost/agentledger \
AGENTLEDGER_API_KEY=my-secret \
AGENTLEDGER_BUDGET_DAILY=10.00 \
AGENTLEDGER_BUDGET_SESSION=1.00 \
uv run python -m agentledger.proxy
```

**Using the API key:**

```bash
# Header
curl -H "x-agentledger-api-key: my-secret" http://localhost:8000/session/run-1

# Query param (for browser access)
http://localhost:8000?api_key=my-secret
```

---

### Request headers

Pass these from your agent on each LLM call. All are optional.

| Header | Default | Description |
|---|---|---|
| `x-agentledger-session-id` | _(none)_ | Groups all calls in a run. Use a consistent ID per execution (e.g. `"run-1"`, a UUID). Without this, calls are stored but not grouped. |
| `x-agentledger-user-id` | _(none)_ | The end user who triggered this run. Useful for per-user auditing. |
| `x-agentledger-agent-name` | _(none)_ | Name of the agent making this call (e.g. `"researcher"`). Used for agent-level budget tracking. |
| `x-agentledger-app-id` | _(none)_ | Application name or ID. Useful if multiple apps share one proxy. |
| `x-agentledger-parent-action-id` | _(none)_ | The `action_id` of the call that triggered this one. Builds the agent call graph. |
| `x-agentledger-environment` | `development` | `production`, `staging`, or `development`. |
| `x-agentledger-handoff-from` | _(none)_ | Agent handing off control (e.g. `"orchestrator"`). |
| `x-agentledger-handoff-to` | _(none)_ | Agent receiving control (e.g. `"researcher"`). |

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

**Handoff tracking** — when one agent passes control to another:

```python
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

---

## License

MIT
