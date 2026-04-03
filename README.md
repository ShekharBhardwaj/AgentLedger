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

## Optional headers

Pass these on each LLM call to enrich your traces:

| Header | Description |
|---|---|
| `x-agentledger-session-id` | Group calls into a run (e.g. `"run-1"`) |
| `x-agentledger-user-id` | Which end user triggered this |
| `x-agentledger-agent-name` | Which agent made this call |
| `x-agentledger-app-id` | Which application |
| `x-agentledger-parent-action-id` | Parent call's action ID (for nested agents) |
| `x-agentledger-environment` | `production` / `staging` / `development` |
| `x-agentledger-handoff-from` | Agent handing off (e.g. `"orchestrator"`) |
| `x-agentledger-handoff-to` | Agent receiving the handoff (e.g. `"researcher"`) |

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AGENTLEDGER_UPSTREAM_URL` | `https://api.openai.com` | Where to forward LLM requests |
| `AGENTLEDGER_DSN` | `sqlite:///agentledger.db` | Database — SQLite or Postgres |
| `AGENTLEDGER_PORT` | `8000` | Proxy port |
| `AGENTLEDGER_API_KEY` | _(none)_ | Protect the dashboard and retrieval endpoints |

To secure the dashboard, pick any secret string and set it when starting the proxy:

```bash
AGENTLEDGER_API_KEY=my-secret AGENTLEDGER_UPSTREAM_URL=https://api.openai.com uv run python -m agentledger.proxy
```

Then pass it when accessing the dashboard or API:

```bash
curl -H "x-agentledger-api-key: my-secret" http://localhost:8000/session/run-1
# or open in browser:
# http://localhost:8000?api_key=my-secret
```

Optional — skip it if you're running locally.

---

## License

MIT
