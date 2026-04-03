# AgentLedger

Runtime observability for AI agents — see exactly what your agent did, why it did it, and what it cost.

Works with **any agent framework**, **any LLM provider**, **any model gateway**. Zero code changes required. Point your agent at the proxy and everything is captured automatically.

---

## How it works

AgentLedger runs as a transparent proxy between your agent and the LLM provider. It intercepts every request and response, assigns it an `action_id`, stores it, and returns the upstream response unmodified. Your agent never knows the proxy is there.

```
Your Agent  →  AgentLedger Proxy  →  OpenAI / Anthropic / LiteLLM / any LLM
                      ↓
               SQLite or Postgres
                      ↓
               Live Dashboard + API
```

---

## Quick Start

**Step 1 — Start the proxy**

With Docker (recommended, no Python required):
```bash
docker run -p 8000:8000 \
  -e AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
  -v $(pwd)/data:/data \
  ghcr.io/shekharBhardwaj/agentledger:latest
```

With `uv`:
```bash
uv add "agentledger @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com uv run python -m agentledger.proxy
```

With `pip`:
```bash
python -m venv venv && source venv/bin/activate
pip install "agentledger @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com ./venv/bin/python -m agentledger.proxy
```

Proxy starts on `http://localhost:8000`. Traces are saved to `agentledger.db` in the current folder (or `/data/agentledger.db` in Docker).

---

**Step 2 — Point your agent at the proxy**

Two changes: set `base_url` to the proxy, and add a `session_id` header to group calls into a run. Everything else — your API key, model, messages — stays exactly the same.

**OpenAI:**
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",  # ← proxy
    api_key="your-openai-key",
    default_headers={"x-agentledger-session-id": "run-1"},
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Research the top 3 AI trends in 2026"}],
)
```

**Anthropic:**
```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",  # ← proxy
    api_key="your-anthropic-key",
    default_headers={"x-agentledger-session-id": "run-1"},
)
```

**LiteLLM / OpenRouter / any gateway:**
```bash
AGENTLEDGER_UPSTREAM_URL=http://localhost:4000 uv run python -m agentledger.proxy
```
Then point your agent at `http://localhost:8000` — AgentLedger proxies through to LiteLLM.

---

**Step 3 — Open the dashboard**

```
http://localhost:8000
```

The dashboard updates live via WebSocket as calls come in. No refresh needed.

- **Calls tab** — every LLM call with full prompt, system prompt, tool calls, tool results, output, tokens, cost, latency, and errors
- **Flow tab** — visual DAG of your multi-agent system. Shows each agent as a node with aggregated cost, latency, and call count. Edges represent handoffs between agents. Click a node to highlight its calls.
- **Search** — full-text search across all sessions by prompt content, output, agent name, or user

---

## What gets captured

Every LLM call is stored with:

| Field | What it contains |
|---|---|
| `action_id` | UUID assigned at interception time |
| `session_id` | Run grouping (from header) |
| `timestamp` | When the call was made |
| `model_id` | Model used |
| `provider` | `openai` or `anthropic` |
| `messages` | Full message history sent to the model |
| `system_prompt` | Extracted system prompt |
| `tools` | Tool definitions available to the model |
| `tool_calls` | Tools the model decided to call |
| `tool_results` | What the tools returned (from next call's messages) |
| `content` | Model's text output |
| `stop_reason` | Why the model stopped |
| `tokens_in` / `tokens_out` | Token usage |
| `cost_usd` | Estimated cost based on model pricing |
| `latency_ms` | End-to-end response time |
| `status_code` | HTTP status from upstream (captures errors too) |
| `error_detail` | Upstream error message for non-200 responses |
| `agent_name` | From header |
| `user_id` | From header |
| `app_id` | From header |
| `environment` | From header |
| `parent_action_id` | Parent call in a nested agent graph |
| `handoff_from` / `handoff_to` | Agent handoff tracking |

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Live dashboard |
| `WS` | `/ws` | WebSocket stream — dashboard connects here for live updates |
| `GET` | `/api/sessions` | List recent sessions with aggregated stats |
| `GET` | `/api/search?q=...` | Full-text search across all captured calls |
| `GET` | `/session/{session_id}` | All calls in a session, ordered by time |
| `GET` | `/explain/{action_id}` | Single call by action ID |
| `GET` | `/export/{session_id}` | JSON compliance export with SHA-256 integrity hash |
| `GET` | `/export/{session_id}/report` | Printable HTML audit report |
| `POST` | `/mcp` | MCP tool server — expose captured data to other agents |

**Examples:**
```bash
# Inspect a session
curl http://localhost:8000/session/run-1

# Search across all sessions
curl "http://localhost:8000/api/search?q=failed+to+connect"

# Download JSON audit trail (includes SHA-256 hash for tamper detection)
curl http://localhost:8000/export/run-1 -o audit-run-1.json

# Open printable HTML report — print to PDF from browser
open http://localhost:8000/export/run-1/report
```

---

## Configuration

### Environment variables

**Core:**

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENTLEDGER_UPSTREAM_URL` | **Yes** | `https://api.openai.com` | LLM endpoint to forward requests to. Accepts OpenAI, Anthropic, LiteLLM, OpenRouter, or any OpenAI-compatible URL. |
| `AGENTLEDGER_DSN` | No | `sqlite:///agentledger.db` | Database connection string. SQLite for local dev, Postgres URL for production. |
| `AGENTLEDGER_HOST` | No | `0.0.0.0` | Host to bind to. Use `127.0.0.1` to restrict to localhost only. |
| `AGENTLEDGER_PORT` | No | `8000` | Port to run on. |
| `AGENTLEDGER_API_KEY` | No | _(none)_ | Protects the dashboard and all read endpoints. Skip for local dev. Set when the proxy is exposed on a server — you choose the value. |

**Cost budgets** — block calls that would exceed a spend limit (returns HTTP 429):

| Variable | Default | Description |
|---|---|---|
| `AGENTLEDGER_BUDGET_SESSION` | _(none)_ | Max USD per `session_id` across its lifetime. |
| `AGENTLEDGER_BUDGET_AGENT` | _(none)_ | Max USD per `agent_name` per calendar day (UTC). |
| `AGENTLEDGER_BUDGET_DAILY` | _(none)_ | Max USD total across all calls per calendar day (UTC). |

**Rate limits** — block calls that exceed request frequency (returns HTTP 429, resets every 60 seconds):

| Variable | Default | Description |
|---|---|---|
| `AGENTLEDGER_RATE_LIMIT_RPM` | _(none)_ | Max requests per minute globally. |
| `AGENTLEDGER_RATE_LIMIT_SESSION_RPM` | _(none)_ | Max requests per minute per `session_id`. |
| `AGENTLEDGER_RATE_LIMIT_AGENT_RPM` | _(none)_ | Max requests per minute per `agent_name`. |
| `AGENTLEDGER_RATE_LIMIT_USER_RPM` | _(none)_ | Max requests per minute per `user_id`. |

**Alerts** — fire a webhook when a threshold is breached (does not block, see [Alerts](#alerts)):

| Variable | Default | Description |
|---|---|---|
| `AGENTLEDGER_ALERT_WEBHOOK_URL` | _(none)_ | URL to POST alert payloads to. Required for any alerts to fire. |
| `AGENTLEDGER_ALERT_COST_PER_CALL` | _(none)_ | Alert when a single call costs more than `$X`. |
| `AGENTLEDGER_ALERT_LATENCY_MS` | _(none)_ | Alert when a single call takes longer than `Xms`. |
| `AGENTLEDGER_ALERT_ERROR_RATE` | _(none)_ | Alert when session error rate exceeds `X` (e.g. `0.5` = 50%). |
| `AGENTLEDGER_ALERT_DAILY_SPEND` | _(none)_ | Alert when daily spend crosses `$X`. Unlike budgets, this does not block calls. |

---

### Common startup examples

```bash
# Local dev — OpenAI
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com uv run python -m agentledger.proxy

# Local dev — Anthropic
AGENTLEDGER_UPSTREAM_URL=https://api.anthropic.com uv run python -m agentledger.proxy

# Local dev — LiteLLM gateway
AGENTLEDGER_UPSTREAM_URL=http://localhost:4000 uv run python -m agentledger.proxy

# Production — Postgres + auth + budgets + rate limits + alerts
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
AGENTLEDGER_DSN=postgresql://user:password@localhost/agentledger \
AGENTLEDGER_API_KEY=my-secret \
AGENTLEDGER_BUDGET_DAILY=20.00 \
AGENTLEDGER_BUDGET_SESSION=2.00 \
AGENTLEDGER_RATE_LIMIT_SESSION_RPM=20 \
AGENTLEDGER_RATE_LIMIT_USER_RPM=60 \
AGENTLEDGER_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz \
AGENTLEDGER_ALERT_COST_PER_CALL=0.50 \
AGENTLEDGER_ALERT_DAILY_SPEND=15.00 \
uv run python -m agentledger.proxy

# Docker Compose (SQLite, edit docker-compose.yml to switch to Postgres)
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com docker compose up
```

When `AGENTLEDGER_API_KEY` is set:
```bash
# Header
curl -H "x-agentledger-api-key: my-secret" http://localhost:8000/session/run-1

# Query param (browser)
http://localhost:8000?api_key=my-secret
```

---

### Request headers

Pass these from your agent on each LLM call. All optional. They enrich captured data, power the Flow tab, and enable per-dimension budgets and rate limits.

| Header | Default | Description |
|---|---|---|
| `x-agentledger-session-id` | _(none)_ | Groups all calls in a run. Use a consistent ID per agent execution (e.g. a UUID or `"run-1"`). Without this, calls are stored but not grouped in the dashboard. |
| `x-agentledger-user-id` | _(none)_ | End user who triggered this run. Enables per-user rate limiting and auditing. |
| `x-agentledger-agent-name` | _(none)_ | Name of the agent making this call (e.g. `"orchestrator"`, `"researcher"`). Powers the Flow tab DAG and agent-level budgets and rate limits. |
| `x-agentledger-app-id` | _(none)_ | Application name or ID. Useful when multiple apps share one proxy. |
| `x-agentledger-parent-action-id` | _(none)_ | The `action_id` of the call that spawned this one. Builds the nested agent call graph. |
| `x-agentledger-environment` | `development` | `production`, `staging`, or `development`. Shown in the dashboard. |
| `x-agentledger-handoff-from` | _(none)_ | Agent handing off control. Renders as a directed edge in the Flow DAG. |
| `x-agentledger-handoff-to` | _(none)_ | Agent receiving control. Renders as a directed edge in the Flow DAG. |

**Single agent — fully annotated:**
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-openai-key",
    default_headers={
        "x-agentledger-session-id":  "run-abc123",
        "x-agentledger-user-id":     "user-42",
        "x-agentledger-agent-name":  "researcher",
        "x-agentledger-app-id":      "my-app",
        "x-agentledger-environment": "production",
    },
)
```

**Multi-agent system — tracking handoffs:**
```python
# Orchestrator makes a call, then hands off to researcher
orchestrator_client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-openai-key",
    default_headers={
        "x-agentledger-session-id":  "run-abc123",
        "x-agentledger-agent-name":  "orchestrator",
    },
)

# Researcher picks up the task
researcher_client = OpenAI(
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

The Flow tab renders `orchestrator → researcher` as a DAG with cost and latency on each node.

---

## Alerts

AgentLedger fires a `POST` to your webhook URL when a threshold is breached. You connect it to whatever you already use — Slack, PagerDuty, Discord, email, or a custom endpoint. AgentLedger sends the payload; integration is on your side.

**Payload format:**
```json
{
  "type":       "high_cost",
  "message":    "Single call cost $0.1842 exceeded threshold $0.10",
  "value":      0.1842,
  "threshold":  0.10,
  "action_id":  "a1b2c3d4-...",
  "session_id": "run-1",
  "agent_name": "researcher",
  "timestamp":  "2026-04-03T12:00:00+00:00"
}
```

**Alert types:**

| Type | Triggered when |
|---|---|
| `high_cost` | A single call exceeds `AGENTLEDGER_ALERT_COST_PER_CALL` |
| `high_latency` | A single call exceeds `AGENTLEDGER_ALERT_LATENCY_MS` |
| `high_error_rate` | Session error rate exceeds `AGENTLEDGER_ALERT_ERROR_RATE` |
| `daily_spend` | Daily total spend crosses `AGENTLEDGER_ALERT_DAILY_SPEND` |

**Difference between alerts and budgets:**
- **Budgets** block the call before it reaches the LLM — the agent gets HTTP 429
- **Alerts** fire after a call completes — the call goes through, you get notified

**Slack** — create an [Incoming Webhook](https://api.slack.com/messaging/webhooks) and point `AGENTLEDGER_ALERT_WEBHOOK_URL` at it. The `message` field contains the human-readable text.

**PagerDuty** — use the [Events API v2](https://developer.pagerduty.com/docs/events-api-v2/) URL or a thin adapter that maps `type` → PagerDuty severity.

**Discord** — use a Discord channel webhook URL directly.

**Custom** — any HTTP endpoint that accepts a JSON POST works.

---

## Compliance export

Every session can be exported as a signed audit trail — useful for regulated industries, internal audits, or passing traces to external tools.

```bash
# Machine-readable JSON with SHA-256 integrity hash
curl http://localhost:8000/export/run-1 -o audit-run-1.json

# Printable HTML — open in browser and print to PDF
open http://localhost:8000/export/run-1/report
```

The JSON export includes a `sha256` hash of the calls array. Recipients can verify the export has not been modified after generation.

---

## License

MIT
