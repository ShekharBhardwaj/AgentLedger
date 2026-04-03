# AgentLedger

See exactly what your AI agent did and why.

---

## Prerequisites

- Python 3.9+

That's it. AgentLedger uses SQLite by default — no database setup required.

---

## Install

```bash
pip install "agentledger @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"
```

---

## Quick Start

**1. Start the proxy**

```bash
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
python -m agentledger.proxy
```

- `AGENTLEDGER_UPSTREAM_URL` — where to forward LLM requests (OpenAI, Anthropic, or your own gateway)

The proxy starts on `http://localhost:8000` and saves traces to `agentledger.db` in your current directory.

**2. Point your agent at the proxy**

Change one line — the `base_url`:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-openai-key",
)

# Everything else stays exactly the same
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What is 2 + 2?"}],
)
```

**3. See what happened**

Every response comes back with an `x-agentledger-action-id` header:

```python
print(response.headers["x-agentledger-action-id"])
# → "3f2a1b4c-..."
```

Retrieve the full trace:

```bash
curl http://localhost:8000/explain/3f2a1b4c-...
```

---

## Group an agent run into a session

Pass a session ID to link all calls from one run:

```python
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-openai-key",
    default_headers={"x-agentledger-session-id": "my-run-1"},
)
```

Retrieve the full decision chain:

```bash
curl http://localhost:8000/session/my-run-1
```

---

## Using Anthropic?

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",
    api_key="your-anthropic-key",
)
```

---

## Using Postgres in production?

```bash
pip install "agentledger[postgres] @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"

AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
AGENTLEDGER_DSN=postgresql://localhost/agentledger \
python -m agentledger.proxy
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AGENTLEDGER_UPSTREAM_URL` | `https://api.openai.com` | Where to forward requests |
| `AGENTLEDGER_DSN` | `sqlite:///agentledger.db` | Database — SQLite or Postgres |
| `AGENTLEDGER_PORT` | `8000` | Proxy port |

---

## License

MIT
