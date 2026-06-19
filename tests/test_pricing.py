"""Tests for agentledger/proxy/pricing.py — cost computation + override loading.

The pricing module exposes:
  * ``_PRICES``          built-in per-million-token (input, output) table.
  * ``compute_cost``     model_id + tokens_in/out -> USD cost (or None).
  * ``_load_overrides``  merges AGENTLEDGER_PRICING / *_FILE env overrides into _PRICES.

Per the module docstring, prices are quoted *per million tokens*, so feeding
exactly 1_000_000 input tokens and 0 output tokens of a model must return its
input price directly (e.g. gpt-4o -> 2.50).

NOTE on test isolation: ``_load_overrides`` mutates the module-global ``_PRICES``
in place and is *not* idempotent across env changes. Every override test
snapshots and restores ``_PRICES`` so it cannot leak into sibling tests.
"""

import copy
import json

import pytest

from agentledger.proxy import pricing

# ── helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture
def restore_prices():
    """Snapshot _PRICES and restore it verbatim after the test.

    Needed because _load_overrides() permanently mutates the module global.
    """
    snapshot = copy.deepcopy(pricing._PRICES)
    try:
        yield
    finally:
        pricing._PRICES.clear()
        pricing._PRICES.update(snapshot)


# ── compute_cost: basic known-model pricing ───────────────────────────────────

def test_known_model_input_only():
    """gpt-4o at 1M input / 0 output tokens costs exactly its input price (2.50)."""
    assert pricing.compute_cost("gpt-4o", 1_000_000, 0) == 2.50


def test_known_model_output_only():
    """gpt-4o at 0 input / 1M output tokens costs exactly its output price (10.00)."""
    assert pricing.compute_cost("gpt-4o", 0, 1_000_000) == 10.00


def test_known_model_both_sides():
    """Cost is input*in_price + output*out_price, scaled per million tokens."""
    # 0.5M in @2.50 + 0.5M out @10.00 = 1.25 + 5.00 = 6.25
    assert pricing.compute_cost("gpt-4o", 500_000, 500_000) == 6.25


def test_partial_token_amounts_scale_linearly():
    """Sub-million token counts scale the per-million price proportionally."""
    # 100 input tokens of gpt-4o @ 2.50/1M = 0.00025
    assert pricing.compute_cost("gpt-4o", 100, 0) == round(100 * 2.50 / 1_000_000, 8)


# ── compute_cost: None / zero handling ────────────────────────────────────────

def test_both_tokens_none_returns_none():
    """When both token counts are None there is nothing to price -> None."""
    assert pricing.compute_cost("gpt-4o", None, None) is None


def test_input_none_treated_as_zero():
    """A None input side is treated as 0, so only output is charged."""
    assert pricing.compute_cost("gpt-4o", None, 1_000_000) == 10.00


def test_output_none_treated_as_zero():
    """A None output side is treated as 0, so only input is charged."""
    assert pricing.compute_cost("gpt-4o", 1_000_000, None) == 2.50


def test_zero_tokens_both_sides_is_zero_not_none():
    """Explicit 0/0 (not None) is a real, priced call costing 0.0."""
    assert pricing.compute_cost("gpt-4o", 0, 0) == 0.0


# ── compute_cost: unknown models ──────────────────────────────────────────────

def test_unknown_model_returns_none():
    """A model with no matching pricing entry returns None even with tokens."""
    assert pricing.compute_cost("totally-made-up-model", 1_000_000, 1_000_000) is None


def test_unknown_model_with_none_tokens_returns_none():
    """Unknown model + no tokens is still None (None short-circuits first)."""
    assert pricing.compute_cost("totally-made-up-model", None, None) is None


# ── compute_cost: case-insensitivity ──────────────────────────────────────────

def test_uppercase_model_matches():
    """Model ids are matched case-insensitively (all upper)."""
    assert pricing.compute_cost("GPT-4O", 1_000_000, 0) == 2.50


def test_mixed_case_model_matches():
    """Model ids are matched case-insensitively (mixed case)."""
    assert pricing.compute_cost("Gpt-4O", 0, 1_000_000) == 10.00


def test_provider_prefixed_model_id_still_matches():
    """A vendor-prefixed id (substring match) still resolves to the base price."""
    # OpenRouter / Bedrock style ids embed the canonical name as a substring.
    assert pricing.compute_cost("openai/gpt-4o", 1_000_000, 0) == 2.50


# ── compute_cost: model-specificity correctness checks ────────────────────────
#
# Specificity: a model id often contains a shorter, more general id as a
# substring (e.g. "gpt-4o" inside "gpt-4o-mini"). compute_cost must price by the
# LONGEST (most specific) matching pattern so the specific model gets its own rate.

def test_gpt_4o_mini_uses_its_own_rate():
    """gpt-4o-mini must use its own 0.15 input price, not gpt-4o's 2.50."""
    assert pricing.compute_cost("gpt-4o-mini", 1_000_000, 0) == 0.15


def test_gpt_4o_mini_output_uses_its_own_rate():
    """gpt-4o-mini output must be 0.60, not gpt-4o's 10.00."""
    assert pricing.compute_cost("gpt-4o-mini", 0, 1_000_000) == 0.60


def test_o1_mini_uses_its_own_rate():
    """o1-mini must use its own 3.00 input price, not o1's 15.00."""
    assert pricing.compute_cost("o1-mini", 1_000_000, 0) == 3.00


def test_o1_uses_its_own_rate():
    """o1 (no suffix) correctly resolves to its own 15.00 input price."""
    assert pricing.compute_cost("o1", 1_000_000, 0) == 15.00


def test_o3_mini_uses_its_own_rate():
    """o3-mini must use its own 1.10 input price, not o3's 10.00."""
    assert pricing.compute_cost("o3-mini", 1_000_000, 0) == 1.10


def test_gpt_41_mini_uses_its_own_rate():
    """gpt-4.1-mini must use its own 0.40 input price, not gpt-4.1's 2.00."""
    assert pricing.compute_cost("gpt-4.1-mini", 1_000_000, 0) == 0.40


def test_gpt_41_nano_uses_its_own_rate():
    """gpt-4.1-nano must use its own 0.10 input price, not gpt-4.1's 2.00."""
    assert pricing.compute_cost("gpt-4.1-nano", 1_000_000, 0) == 0.10


def test_claude_3_5_sonnet_uses_its_own_rate():
    """claude-3-5-sonnet resolves to its own 3.00 input price (and 15.00 out)."""
    # claude-3-5-sonnet is not a superstring of any earlier-inserted pattern,
    # so it is priced correctly even under substring matching.
    assert pricing.compute_cost("claude-3-5-sonnet", 1_000_000, 0) == 3.00
    assert pricing.compute_cost("claude-3-5-sonnet", 0, 1_000_000) == 15.00


def test_claude_3_sonnet_uses_its_own_rate():
    """claude-3-sonnet resolves to its own 3.00 / 15.00 rate."""
    assert pricing.compute_cost("claude-3-sonnet", 1_000_000, 0) == 3.00
    assert pricing.compute_cost("claude-3-sonnet", 0, 1_000_000) == 15.00


def test_claude_3_haiku_not_shadowed_by_claude_3_5_haiku():
    """claude-3-haiku keeps its own 0.25 input price (distinct from 3-5-haiku's 0.80)."""
    assert pricing.compute_cost("claude-3-haiku", 1_000_000, 0) == 0.25


def test_gpt_4_turbo_uses_its_own_rate():
    """gpt-4-turbo is priced at 10.00 in, distinct from bare gpt-4's 30.00."""
    # gpt-4-turbo is inserted before gpt-4, so its more-specific entry wins.
    assert pricing.compute_cost("gpt-4-turbo", 1_000_000, 0) == 10.00


# ── _load_overrides: inline JSON env var ──────────────────────────────────────

def test_override_inline_json_adds_new_model(restore_prices, monkeypatch):
    """AGENTLEDGER_PRICING inline JSON registers a brand-new model price."""
    monkeypatch.delenv("AGENTLEDGER_PRICING_FILE", raising=False)
    monkeypatch.setenv("AGENTLEDGER_PRICING", json.dumps({"my-model": [1.00, 2.00]}))

    assert pricing.compute_cost("my-model", 1_000_000, 0) is None  # not yet loaded
    pricing._load_overrides()

    assert pricing.compute_cost("my-model", 1_000_000, 0) == 1.00
    assert pricing.compute_cost("my-model", 0, 1_000_000) == 2.00


def test_override_inline_json_overrides_existing_model(restore_prices, monkeypatch):
    """An override for an existing model replaces its built-in price."""
    monkeypatch.delenv("AGENTLEDGER_PRICING_FILE", raising=False)
    monkeypatch.setenv("AGENTLEDGER_PRICING", json.dumps({"gpt-4o": [99.0, 100.0]}))
    pricing._load_overrides()

    assert pricing.compute_cost("gpt-4o", 1_000_000, 0) == 99.0
    assert pricing.compute_cost("gpt-4o", 0, 1_000_000) == 100.0


def test_override_model_key_is_lowercased(restore_prices, monkeypatch):
    """Override keys are normalised to lowercase so case-insensitive lookup works."""
    monkeypatch.delenv("AGENTLEDGER_PRICING_FILE", raising=False)
    monkeypatch.setenv("AGENTLEDGER_PRICING", json.dumps({"My-Custom-MODEL": [5.0, 6.0]}))
    pricing._load_overrides()

    assert "my-custom-model" in pricing._PRICES
    assert pricing.compute_cost("MY-CUSTOM-MODEL", 1_000_000, 0) == 5.0


def test_invalid_inline_json_is_ignored(restore_prices, monkeypatch):
    """Malformed AGENTLEDGER_PRICING JSON is logged and ignored, not fatal."""
    monkeypatch.delenv("AGENTLEDGER_PRICING_FILE", raising=False)
    monkeypatch.setenv("AGENTLEDGER_PRICING", "{not valid json")
    pricing._load_overrides()  # must not raise

    # Built-in table is untouched.
    assert pricing.compute_cost("gpt-4o", 1_000_000, 0) == 2.50


def test_malformed_entry_is_skipped_others_applied(restore_prices, monkeypatch):
    """A single bad entry is skipped; valid sibling entries still apply."""
    monkeypatch.delenv("AGENTLEDGER_PRICING_FILE", raising=False)
    monkeypatch.setenv(
        "AGENTLEDGER_PRICING",
        json.dumps({"bad-model": ["oops"], "good-model": [1.0, 2.0]}),
    )
    pricing._load_overrides()  # must not raise

    assert pricing.compute_cost("good-model", 1_000_000, 0) == 1.0
    assert pricing.compute_cost("bad-model", 1_000_000, 0) is None


def test_empty_pricing_env_is_noop(restore_prices, monkeypatch):
    """An empty/whitespace AGENTLEDGER_PRICING leaves the table unchanged."""
    monkeypatch.delenv("AGENTLEDGER_PRICING_FILE", raising=False)
    monkeypatch.setenv("AGENTLEDGER_PRICING", "   ")
    before = copy.deepcopy(pricing._PRICES)
    pricing._load_overrides()
    assert before == pricing._PRICES


# ── _load_overrides: file-based override ──────────────────────────────────────

def test_override_from_file(restore_prices, monkeypatch, tmp_path):
    """AGENTLEDGER_PRICING_FILE loads a JSON file and applies its prices."""
    pf = tmp_path / "pricing.json"
    pf.write_text(json.dumps({"file-model": [3.0, 4.0], "gpt-4o": [50.0, 60.0]}))

    monkeypatch.delenv("AGENTLEDGER_PRICING", raising=False)
    monkeypatch.setenv("AGENTLEDGER_PRICING_FILE", str(pf))
    pricing._load_overrides()

    assert pricing.compute_cost("file-model", 1_000_000, 0) == 3.0
    assert pricing.compute_cost("gpt-4o", 1_000_000, 0) == 50.0


def test_missing_file_is_ignored(restore_prices, monkeypatch, tmp_path):
    """A non-existent AGENTLEDGER_PRICING_FILE is logged and ignored, not fatal."""
    monkeypatch.delenv("AGENTLEDGER_PRICING", raising=False)
    monkeypatch.setenv("AGENTLEDGER_PRICING_FILE", str(tmp_path / "does-not-exist.json"))
    pricing._load_overrides()  # must not raise

    assert pricing.compute_cost("gpt-4o", 1_000_000, 0) == 2.50


def test_inline_and_file_both_applied(restore_prices, monkeypatch, tmp_path):
    """Inline JSON and file overrides are both merged into the table."""
    pf = tmp_path / "pricing.json"
    pf.write_text(json.dumps({"from-file": [7.0, 8.0]}))

    monkeypatch.setenv("AGENTLEDGER_PRICING", json.dumps({"from-inline": [1.5, 2.5]}))
    monkeypatch.setenv("AGENTLEDGER_PRICING_FILE", str(pf))
    pricing._load_overrides()

    assert pricing.compute_cost("from-inline", 1_000_000, 0) == 1.5
    assert pricing.compute_cost("from-file", 1_000_000, 0) == 7.0


def test_file_overrides_win_over_inline_for_same_key(restore_prices, monkeypatch, tmp_path):
    """When inline and file both define a model, the file value wins (applied last)."""
    pf = tmp_path / "pricing.json"
    pf.write_text(json.dumps({"dup-model": [9.0, 9.0]}))

    monkeypatch.setenv("AGENTLEDGER_PRICING", json.dumps({"dup-model": [1.0, 1.0]}))
    monkeypatch.setenv("AGENTLEDGER_PRICING_FILE", str(pf))
    pricing._load_overrides()

    # overrides.update(file) runs after overrides.update(inline), so file wins.
    assert pricing.compute_cost("dup-model", 1_000_000, 0) == 9.0
