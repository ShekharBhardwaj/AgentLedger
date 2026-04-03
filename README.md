# AgentLedger

See exactly what your AI agent did and why.

---

## Prerequisites

- Python 3.9+
- Postgres running locally (`brew install postgresql` on Mac)

---

## Install

```bash
pip install "agentledger @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"
```

---

## Setup

**1. Create the database**

```bash
createdb agentledger
```

**2. Start the proxy**

```bash
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
AGENTLEDGER_PG_DSN=postgresql://localhost/agentledger \
python -m agentledger.proxy
```

- `AGENTLEDGER_UPSTREAM_URL` — where to forward LLM requests (OpenAI, Anthropic, or your own gateway)
- `AGENTLEDGER_PG_DSN` — the Postgres database you created in step 1

The proxy is now running on `http://localhost:8000`.

**3. Point your agent at the proxy**

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

**4. See what happened**

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

## Using LiteLLM?

Set the upstream to your LiteLLM instance:

```bash
AGENTLEDGER_UPSTREAM_URL=http://localhost:4000 \
AGENTLEDGER_PG_DSN=postgresql://localhost/agentledger \
python -m agentledger.proxy
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AGENTLEDGER_UPSTREAM_URL` | `https://api.openai.com` | Where to forward requests |
| `AGENTLEDGER_PG_DSN` | *(required)* | Postgres connection string |
| `AGENTLEDGER_PORT` | `8000` | Proxy port |

---

## License

MIT
