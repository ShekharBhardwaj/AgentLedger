# AgentLedger

See exactly what your AI agent did and why.

---

## Quick Start

**1. Install**

Open a terminal and run:

```bash
python -m venv venv
source venv/bin/activate
pip install "agentledger @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"
```

> Windows: use `venv\Scripts\activate` instead

**2. Start the proxy**

In a new terminal tab (keep this running):

```bash
source venv/bin/activate
AGENTLEDGER_UPSTREAM_URL=https://api.openai.com python -m agentledger.proxy
```

You should see uvicorn start on `http://localhost:8000`.
Traces are saved to `agentledger.db` in your current directory.

**3. Point your agent at the proxy**

Two changes: set `base_url` and add a session ID so you can retrieve the trace later.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-openai-key",
    default_headers={"x-agentledger-session-id": "run-1"},
)

# Your agent code is unchanged from here
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What is 2 + 2?"}],
)
```

**4. See what happened**

```bash
curl http://localhost:8000/session/run-1
```

Returns every LLM call in that run — prompts, tool calls, responses, token usage, and timing.

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
pip install "agentledger[postgres] @ git+https://github.com/ShekharBhardwaj/AgentLedger.git"

AGENTLEDGER_UPSTREAM_URL=https://api.openai.com \
AGENTLEDGER_DSN=postgresql://localhost/agentledger \
python -m agentledger.proxy
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AGENTLEDGER_UPSTREAM_URL` | `https://api.openai.com` | Where to forward LLM requests |
| `AGENTLEDGER_DSN` | `sqlite:///agentledger.db` | Database — SQLite or Postgres |
| `AGENTLEDGER_PORT` | `8000` | Proxy port |

---

## License

MIT
