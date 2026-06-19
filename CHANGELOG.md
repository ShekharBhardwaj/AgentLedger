# Changelog

All notable changes to AgentLedger are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive automated test suite (`tests/`) with ~250 tests covering request/response
  normalization, streaming SSE reconstruction, pricing, rate limiting, budgets, the storage
  layer, the proxy request path, compliance export, the MCP server, and webhook alerts.
- Shared pytest harness (`tests/conftest.py`) with a mock-upstream proxy fixture and
  provider wire-format builders — tests are fully offline and deterministic.
- CI now runs `ruff` linting and `pytest` with coverage (gated at 70%) across Python
  3.10 / 3.11 / 3.12.
- CodeQL security scanning and Dependabot dependency updates.
- Community health files: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`,
  pull-request template, and issue templates.
- `ruff` configuration and a `[dev]` tooling extra (`pytest-cov`, `ruff`).

### Fixed
- **Postgres data loss:** the production Postgres backend typed `session_id` as `UUID`
  and cast every id with `uuid.UUID(...)`. Agent session ids are arbitrary strings — the
  proxy mints `auto-<date>` when no header is supplied, and users pass human-readable run
  names — so any non-UUID session id raised and, because the proxy save path is fail-open,
  was **silently dropped**. `session_id` is now `TEXT` (matching SQLite); existing databases
  are migrated in place on connect (`ALTER COLUMN session_id TYPE TEXT`). Added a Postgres
  regression test suite (runs in CI against a Postgres service; skipped locally without one).
- **Cost computation:** `compute_cost` now matches the longest (most specific) pricing
  pattern instead of the first substring match. Previously `gpt-4o-mini`, `o1-mini`,
  `o3-mini`, `gpt-4.1-mini`, and `gpt-4.1-nano` were each priced at their parent model's
  (much higher) rate — e.g. `gpt-4o-mini` was billed at `gpt-4o` rates (~16× too high on
  input). Captured costs for these models are now correct.

### Changed
- Stopped tracking the runtime SQLite database (`agentledger.db`) in git and added `*.db`
  to `.gitignore`. The database is a runtime artifact and may contain captured prompt data.

<!--
## [0.1.7] - YYYY-MM-DD
Older releases predate this changelog. See the GitHub Releases page for history:
https://github.com/ShekharBhardwaj/AgentLedger/releases
-->

[Unreleased]: https://github.com/ShekharBhardwaj/AgentLedger/compare/v0.1.7...HEAD
