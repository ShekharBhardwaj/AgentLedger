"""
python -m agentledger.proxy

Reads config from environment variables:
    AGENTLEDGER_UPSTREAM_URL   Where to forward LLM requests (default: https://api.openai.com)
    AGENTLEDGER_DSN            Database URL (default: sqlite:///agentledger.db)
    AGENTLEDGER_HOST           Bind host (default: 0.0.0.0)
    AGENTLEDGER_PORT           Bind port (default: 8000)
"""

import os

import uvicorn

from .app import create_app

upstream_url = os.environ.get("AGENTLEDGER_UPSTREAM_URL", "https://api.openai.com")
dsn = os.environ.get("AGENTLEDGER_DSN", "sqlite:///agentledger.db")
host = os.environ.get("AGENTLEDGER_HOST", "0.0.0.0")
port = int(os.environ.get("AGENTLEDGER_PORT", "8000"))

app = create_app(upstream_url=upstream_url, dsn=dsn)
uvicorn.run(app, host=host, port=port)
