"""
Per-token pricing table for common models.
Cost is computed at capture time and stored with each call.

Prices are per million tokens (input, output).
Update this table as providers change pricing.
"""

from typing import Optional

# (input_per_million_tokens, output_per_million_tokens) in USD
_PRICES: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o":            (2.50,  10.00),
    "gpt-4o-mini":       (0.15,   0.60),
    "gpt-4-turbo":      (10.00,  30.00),
    "gpt-4":            (30.00,  60.00),
    "gpt-3.5-turbo":     (0.50,   1.50),
    "o1":               (15.00,  60.00),
    "o1-mini":           (3.00,  12.00),
    "o3-mini":           (1.10,   4.40),
    # Anthropic
    "claude-opus-4":    (15.00,  75.00),
    "claude-sonnet-4":   (3.00,  15.00),
    "claude-haiku-4":    (0.80,   4.00),
    "claude-3-5-sonnet": (3.00,  15.00),
    "claude-3-5-haiku":  (0.80,   4.00),
    "claude-3-opus":    (15.00,  75.00),
    "claude-3-sonnet":   (3.00,  15.00),
    "claude-3-haiku":    (0.25,   1.25),
}


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
