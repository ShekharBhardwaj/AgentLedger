"""
python -m agentledger.proxy

Reads config from environment variables:

  Core:
    AGENTLEDGER_UPSTREAM_URL          LLM endpoint to proxy (default: https://api.openai.com)
    AGENTLEDGER_DSN                   Database URL (default: sqlite:///agentledger.db)
    AGENTLEDGER_HOST                  Bind host (default: 0.0.0.0)
    AGENTLEDGER_PORT                  Bind port (default: 8000)
    AGENTLEDGER_API_KEY               Protect dashboard/API endpoints (default: none)
    AGENTLEDGER_EXTRA_PATHS           Extra comma-separated paths to capture (default: none)

  Budgets (returns HTTP 429 when exceeded, or warns — see AGENTLEDGER_BUDGET_ACTION):
    AGENTLEDGER_BUDGET_SESSION        Max USD per session_id (default: none)
    AGENTLEDGER_BUDGET_AGENT          Max USD per agent_name per calendar day (default: none)
    AGENTLEDGER_BUDGET_DAILY          Max USD total per calendar day (default: none)
    AGENTLEDGER_BUDGET_ACTION         block (default) | warn | both

  Rate limits (returns HTTP 429, sliding 60-second window):
    AGENTLEDGER_RATE_LIMIT_RPM        Max requests per minute globally (default: none)
    AGENTLEDGER_RATE_LIMIT_SESSION_RPM  Max requests per minute per session_id (default: none)
    AGENTLEDGER_RATE_LIMIT_AGENT_RPM  Max requests per minute per agent_name (default: none)
    AGENTLEDGER_RATE_LIMIT_USER_RPM   Max requests per minute per user_id (default: none)

  Alerts (POST to webhook on threshold breach — does not block calls):
    AGENTLEDGER_ALERT_WEBHOOK_URL     Webhook URL for alerts (default: none)
    AGENTLEDGER_ALERT_COST_PER_CALL   Alert if single call costs more than $X (default: none)
    AGENTLEDGER_ALERT_LATENCY_MS      Alert if single call takes longer than Xms (default: none)
    AGENTLEDGER_ALERT_ERROR_RATE      Alert if session error rate exceeds X, e.g. 0.5 (default: none)
    AGENTLEDGER_ALERT_DAILY_SPEND     Alert when daily spend crosses $X (default: none)

  OpenTelemetry (requires pip install 'agentic-ledger[otel]'):
    AGENTLEDGER_OTEL_ENDPOINT         OTLP/HTTP base URL, e.g. http://localhost:4318 (default: none)
    AGENTLEDGER_OTEL_SERVICE_NAME     service.name reported to collector (default: agentledger)
    AGENTLEDGER_OTEL_HEADERS          Comma-separated key=value auth headers (default: none)

  Pricing overrides (merged over the built-in table at startup):
    AGENTLEDGER_PRICING               Inline JSON — e.g. '{"gpt-4o": [2.50, 10.00], "my-model": [1.00, 2.00]}'
    AGENTLEDGER_PRICING_FILE          Path to a JSON file with the same format
"""

import logging
import os

import uvicorn

from .alerts import AlertConfig
from .app import create_app
from .otel import init_otel
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


_otel_endpoint = os.environ.get("AGENTLEDGER_OTEL_ENDPOINT")
if _otel_endpoint:
    _otel_headers: dict[str, str] = {}
    for pair in os.environ.get("AGENTLEDGER_OTEL_HEADERS", "").split(","):
        pair = pair.strip()
        if "=" in pair:
            k, _, v = pair.partition("=")
            _otel_headers[k.strip()] = v.strip()
    init_otel(
        endpoint=_otel_endpoint,
        service_name=os.environ.get("AGENTLEDGER_OTEL_SERVICE_NAME", "agentledger"),
        headers=_otel_headers or None,
    )

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
    budget_action=os.environ.get("AGENTLEDGER_BUDGET_ACTION", "block"),
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
