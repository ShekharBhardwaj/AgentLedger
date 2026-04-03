"""
python -m agentledger.proxy

Reads config from environment variables:
    AGENTLEDGER_UPSTREAM_URL     Where to forward LLM requests (default: https://api.openai.com)
    AGENTLEDGER_DSN              Database URL (default: sqlite:///agentledger.db)
    AGENTLEDGER_HOST             Bind host (default: 0.0.0.0)
    AGENTLEDGER_PORT             Bind port (default: 8000)
    AGENTLEDGER_API_KEY          Protect dashboard/retrieval endpoints (default: none)
    AGENTLEDGER_BUDGET_SESSION   Max USD per session_id (default: none)
    AGENTLEDGER_BUDGET_AGENT     Max USD per agent per day (default: none)
    AGENTLEDGER_BUDGET_DAILY     Max USD total per calendar day (default: none)
"""

import os

import uvicorn

from .app import create_app


def _float_env(key: str):
    val = os.environ.get(key)
    return float(val) if val else None


upstream_url = os.environ.get("AGENTLEDGER_UPSTREAM_URL", "https://api.openai.com")
dsn          = os.environ.get("AGENTLEDGER_DSN", "sqlite:///agentledger.db")
host         = os.environ.get("AGENTLEDGER_HOST", "0.0.0.0")
port         = int(os.environ.get("AGENTLEDGER_PORT", "8000"))

app = create_app(
    upstream_url=upstream_url,
    dsn=dsn,
    budget_session=_float_env("AGENTLEDGER_BUDGET_SESSION"),
    budget_agent=_float_env("AGENTLEDGER_BUDGET_AGENT"),
    budget_daily=_float_env("AGENTLEDGER_BUDGET_DAILY"),
)

uvicorn.run(app, host=host, port=port)
