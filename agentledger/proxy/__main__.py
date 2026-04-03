"""
python -m agentledger.proxy

Reads config from environment variables:
    AGENTLEDGER_UPSTREAM_URL   LiteLLM base URL  (default: http://localhost:4000)
    AGENTLEDGER_PG_DSN         Postgres DSN      (required)
    AGENTLEDGER_HOST            Bind host         (default: 0.0.0.0)
    AGENTLEDGER_PORT            Bind port         (default: 8000)
"""

import os
import sys

import uvicorn

from .app import create_app

upstream_url = os.environ.get("AGENTLEDGER_UPSTREAM_URL", "http://localhost:4000")
pg_dsn = os.environ.get("AGENTLEDGER_PG_DSN", "")
host = os.environ.get("AGENTLEDGER_HOST", "0.0.0.0")
port = int(os.environ.get("AGENTLEDGER_PORT", "8000"))

if not pg_dsn:
    print("Error: AGENTLEDGER_PG_DSN is required", file=sys.stderr)
    sys.exit(1)

app = create_app(upstream_url=upstream_url, pg_dsn=pg_dsn)
uvicorn.run(app, host=host, port=port)
