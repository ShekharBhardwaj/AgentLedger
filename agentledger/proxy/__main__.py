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

import logging
import os

import uvicorn

from .alerts import AlertConfig
from .app import create_app
from .ratelimit import RateLimitConfig


class _QuietFilter(logging.Filter):
    """Suppress dashboard polling from uvicorn access logs."""
    _NOISY = ("/api/sessions", "/api/search", "/session/", "/export/", "GET / ", "GET /ws")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in self._NOISY)


logging.getLogger("uvicorn.access").addFilter(_QuietFilter())


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
    rate_limit_config=RateLimitConfig(
        global_rpm=  int(os.environ["AGENTLEDGER_RATE_LIMIT_RPM"])          if os.environ.get("AGENTLEDGER_RATE_LIMIT_RPM")          else None,
        session_rpm= int(os.environ["AGENTLEDGER_RATE_LIMIT_SESSION_RPM"])  if os.environ.get("AGENTLEDGER_RATE_LIMIT_SESSION_RPM")  else None,
        agent_rpm=   int(os.environ["AGENTLEDGER_RATE_LIMIT_AGENT_RPM"])    if os.environ.get("AGENTLEDGER_RATE_LIMIT_AGENT_RPM")    else None,
        user_rpm=    int(os.environ["AGENTLEDGER_RATE_LIMIT_USER_RPM"])     if os.environ.get("AGENTLEDGER_RATE_LIMIT_USER_RPM")     else None,
    ),
    alert_config=AlertConfig(
        webhook_url=os.environ.get("AGENTLEDGER_ALERT_WEBHOOK_URL"),
        cost_per_call=_float_env("AGENTLEDGER_ALERT_COST_PER_CALL"),
        latency_ms=_float_env("AGENTLEDGER_ALERT_LATENCY_MS"),
        error_rate=_float_env("AGENTLEDGER_ALERT_ERROR_RATE"),
        daily_spend=_float_env("AGENTLEDGER_ALERT_DAILY_SPEND"),
    ),
)

uvicorn.run(app, host=host, port=port)
