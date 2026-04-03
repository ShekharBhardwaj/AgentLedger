# AgentLedger

See exactly what your AI agent did and why.

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

Open a terminal in your project folder and keep it running:

With `uv`:
```bash
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com uv run python -m agentledger.proxy
```

With `pip`:
```bash
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com ./venv/bin/python -m agentledger.proxy
```

You should see the server start on `http://localhost:8000`.
Traces are saved to `agentledger.db` in your project folder.

**3. Point your agent at the proxy**

Two changes to your existing code — `base_url` and a session ID:

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

Open the dashboard in your browser:

```
http://localhost:8000
```

Or fetch raw JSON:

```bash
curl http://localhost:8000/session/run-1
```

Returns every LLM call in that run — prompts, tool calls, tool results, responses, token usage, cost, and timing.

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
AGENTLEDGER_DSN=postgresql://localhost/agentledger \
uv run python -m agentledger.proxy
```

---

## Configuration

### Environment variables

Set these when starting the proxy.

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENTLEDGER_UPSTREAM_URL` | **Yes** | `https://api.openai.com` | LLM gateway to forward requests to. Can be OpenAI, Anthropic, LiteLLM, OpenRouter, or any OpenAI-compatible URL. |
| `AGENTLEDGER_DSN` | No | `sqlite:///agentledger.db` | Database connection string. SQLite file for local dev, Postgres URL for production. |
| `AGENTLEDGER_HOST` | No | `0.0.0.0` | Host to bind the proxy to. Use `127.0.0.1` to restrict to localhost only. |
| `AGENTLEDGER_PORT` | No | `8000` | Port to run the proxy on. |
| `AGENTLEDGER_API_KEY` | No | _(none)_ | Secret key to protect the dashboard and retrieval endpoints. Skip for local development. Set it when the proxy is exposed on a server. |

**Examples:**

```bash
# Local dev, OpenAI
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com uv run python -m agentledger.proxy

# Local dev, Anthropic
AGENTLEDGER_UPSTREAM_URL=https://api.anthropic.com uv run python -m agentledger.proxy

# Local dev, LiteLLM gateway (any model)
AGENTLEDGER_UPSTREAM_URL=http://localhost:4000 uv run python -m agentledger.proxy

# Custom port
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
AGENTLEDGER_PORT=9000 \
uv run python -m agentledger.proxy

# Production — Postgres + auth
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
AGENTLEDGER_DSN=postgresql://user:password@localhost/agentledger \
AGENTLEDGER_API_KEY=my-secret \
uv run python -m agentledger.proxy
```

When `AGENTLEDGER_API_KEY` is set, pass it to access the dashboard or API:

```bash
# Header
curl -H "x-agentledger-api-key: my-secret" http://localhost:8000/session/run-1

# Query param (browser)
http://localhost:8000?api_key=my-secret
```

---

### Request headers

Pass these from your agent on each LLM call. All are optional.

| Header | Default | Description |
|---|---|---|
| `x-agentledger-session-id` | _(none)_ | Groups all calls in a run together. Use a consistent ID per agent execution (e.g. `"run-1"`, a UUID). Without this, calls are stored but not grouped. |
| `x-agentledger-user-id` | _(none)_ | The end user who triggered this agent run. Useful for per-user auditing. |
| `x-agentledger-agent-name` | _(none)_ | Name of the agent making this call (e.g. `"researcher"`, `"orchestrator"`). |
| `x-agentledger-app-id` | _(none)_ | Name or ID of your application. Useful if multiple apps share one proxy. |
| `x-agentledger-parent-action-id` | _(none)_ | The `action_id` of the call that triggered this one. Used to reconstruct nested agent call graphs. |
| `x-agentledger-environment` | `development` | Environment this call is from: `production`, `staging`, or `development`. |
| `x-agentledger-handoff-from` | _(none)_ | Name of the agent handing off control (e.g. `"orchestrator"`). |
| `x-agentledger-handoff-to` | _(none)_ | Name of the agent receiving control (e.g. `"researcher"`). |

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

**Handoff example** — when one agent passes control to another:

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
