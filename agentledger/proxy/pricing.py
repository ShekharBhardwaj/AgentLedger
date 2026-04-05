"""
Per-token pricing table for common models.
Cost is computed at capture time and stored with each call.

Prices are per million tokens (input, output).
Update this table as providers change pricing.

User overrides (merged over the built-in table at startup):

  AGENTLEDGER_PRICING       Inline JSON — useful for Docker env vars
                            e.g. '{"gpt-4o": [2.50, 10.00], "my-model": [1.00, 2.00]}'

  AGENTLEDGER_PRICING_FILE  Path to a JSON file with the same format
                            e.g. /etc/agentledger/pricing.json
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# (input_per_million_tokens, output_per_million_tokens) in USD
_PRICES: dict[str, tuple[float, float]] = {
    # OpenAI — GPT-4o family
    "gpt-4o":            (2.50,  10.00),
    "gpt-4o-mini":       (0.15,   0.60),
    # OpenAI — GPT-4.1 family
    "gpt-4.1":           (2.00,   8.00),
    "gpt-4.1-mini":      (0.40,   1.60),
    "gpt-4.1-nano":      (0.10,   0.40),
    # OpenAI — GPT-4 legacy
    "gpt-4-turbo":      (10.00,  30.00),
    "gpt-4":            (30.00,  60.00),
    "gpt-3.5-turbo":     (0.50,   1.50),
    # OpenAI — reasoning models
    "o3":               (10.00,  40.00),
    "o3-mini":           (1.10,   4.40),
    "o1":               (15.00,  60.00),
    "o1-mini":           (3.00,  12.00),
    "o4-mini":           (1.10,   4.40),
    # Anthropic — Claude 4 family
    "claude-opus-4":    (15.00,  75.00),
    "claude-sonnet-4":   (3.00,  15.00),
    "claude-haiku-4":    (0.80,   4.00),
    # Anthropic — Claude 3.7
    "claude-3-7-sonnet": (3.00,  15.00),
    # Anthropic — Claude 3.5
    "claude-3-5-sonnet": (3.00,  15.00),
    "claude-3-5-haiku":  (0.80,   4.00),
    # Anthropic — Claude 3
    "claude-3-opus":    (15.00,  75.00),
    "claude-3-sonnet":   (3.00,  15.00),
    "claude-3-haiku":    (0.25,   1.25),
    # Google Gemini
    "gemini-2.5-pro":    (1.25,  10.00),
    "gemini-2.0-flash":  (0.10,   0.40),
    "gemini-1.5-pro":    (1.25,   5.00),
    "gemini-1.5-flash":  (0.075,  0.30),
}


def _load_overrides() -> None:
    """Merge user-supplied pricing overrides into _PRICES at startup."""
    overrides: dict[str, list] = {}

    env_json = os.environ.get("AGENTLEDGER_PRICING", "").strip()
    if env_json:
        try:
            overrides.update(json.loads(env_json))
        except Exception as exc:
            logger.warning("AGENTLEDGER_PRICING is not valid JSON, ignoring: %s", exc)

    pricing_file = os.environ.get("AGENTLEDGER_PRICING_FILE", "").strip()
    if pricing_file:
        try:
            with open(pricing_file) as f:
                overrides.update(json.load(f))
        except Exception as exc:
            logger.warning("AGENTLEDGER_PRICING_FILE could not be loaded, ignoring: %s", exc)

    for model, price in overrides.items():
        try:
            _PRICES[model.lower()] = (float(price[0]), float(price[1]))
        except Exception:
            logger.warning("Invalid pricing entry %r: %r — expected [input, output]", model, price)

_load_overrides()


def compute_cost(
    model_id: str,
    tokens_in: Optional[int],
    tokens_out: Optional[int],
) -> Optional[float]:
    """Return estimated cost in USD, or None if model is not in the pricing table."""
    if tokens_in is None and tokens_out is None:
        return None
    model_lower = model_id.lower()
    for pattern, (in_price, out_price) in _PRICES.items():
        if pattern in model_lower:
            cost = ((tokens_in or 0) * in_price + (tokens_out or 0) * out_price) / 1_000_000
            return round(cost, 8)
    return None
