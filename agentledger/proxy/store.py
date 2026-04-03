"""
Storage backends for AgentLedger.

Store.connect(dsn) returns the right backend based on the DSN prefix:

  sqlite:///agentledger.db   → SQLite  (zero setup, great for development)
  postgresql://...           → Postgres (recommended for production)

Schema is created automatically on first connect. New columns are added
non-destructively so existing databases survive upgrades.
"""

import datetime
import json
import uuid
from typing import Any, Optional

from .normalize import CanonicalRequest, CanonicalResponse

_MIGRATION_COLUMNS = [
    ("user_id",          "TEXT"),
    ("agent_name",       "TEXT"),
    ("app_id",           "TEXT"),
    ("parent_action_id", "TEXT"),
    ("environment",      "TEXT"),
    ("system_prompt",    "TEXT"),
    ("temperature",      "REAL"),
    ("max_tokens",       "INTEGER"),
    ("tool_results",     "TEXT"),   # JSON
    ("cost_usd",         "REAL"),
    ("handoff_from",     "TEXT"),
    ("handoff_to",       "TEXT"),
]


class Store:
    """Common interface — use Store.connect(), not the subclasses directly."""

    @classmethod
    async def connect(cls, dsn: str) -> "Store":
        if dsn.startswith("sqlite"):
            return await _SqliteStore._connect(dsn)
        return await _PostgresStore._connect(dsn)

    async def save(
        self,
        action_id: str,
        req: CanonicalRequest,
        resp: CanonicalResponse,
        *,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        app_id: Optional[str] = None,
        parent_action_id: Optional[str] = None,
        environment: str = "development",
        handoff_from: Optional[str] = None,
        handoff_to: Optional[str] = None,
    ) -> None:
        raise NotImplementedError

    async def get(self, action_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    async def get_session(self, session_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


# ── SQLite ───────────────────────────────────────────────────────────────────

class _SqliteStore(Store):

    def __init__(self, db) -> None:
        self._db = db

    @classmethod
    async def _connect(cls, dsn: str) -> "_SqliteStore":
        import aiosqlite
        path = dsn.split("sqlite:///", 1)[1] or ":memory:"
        db = await aiosqlite.connect(path)
        db.row_factory = aiosqlite.Row
        await db.execute("""
            CREATE TABLE IF NOT EXISTS llm_calls (
                action_id   TEXT PRIMARY KEY,
                session_id  TEXT,
                timestamp   REAL NOT NULL,
                model_id    TEXT NOT NULL,
                provider    TEXT NOT NULL,
                messages    TEXT NOT NULL,
                tools       TEXT,
                content     TEXT,
                tool_calls  TEXT,
                stop_reason TEXT,
                tokens_in   INTEGER,
                tokens_out  INTEGER,
                latency_ms  INTEGER
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS llm_calls_session_idx
            ON llm_calls (session_id) WHERE session_id IS NOT NULL
        """)
        for col, col_type in _MIGRATION_COLUMNS:
            try:
                await db.execute(f"ALTER TABLE llm_calls ADD COLUMN {col} {col_type}")
            except Exception:
                pass
        await db.commit()
        return cls(db)

    async def save(self, action_id, req, resp, *, session_id=None, user_id=None,
                   agent_name=None, app_id=None, parent_action_id=None,
                   environment="development", handoff_from=None, handoff_to=None) -> None:
        await self._db.execute(
            """
            INSERT INTO llm_calls
                (action_id, session_id, timestamp, model_id, provider,
                 messages, tools, content, tool_calls, stop_reason,
                 tokens_in, tokens_out, latency_ms,
                 user_id, agent_name, app_id, parent_action_id, environment,
                 system_prompt, temperature, max_tokens,
                 tool_results, cost_usd, handoff_from, handoff_to)
            VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?, ?,?,?,?,?, ?,?,?, ?,?,?,?)
            """,
            (
                action_id, session_id, req.timestamp, req.model_id, req.provider,
                json.dumps(req.messages),
                json.dumps(req.tools) if req.tools is not None else None,
                resp.content,
                json.dumps(resp.tool_calls) if resp.tool_calls is not None else None,
                resp.stop_reason, resp.tokens_in, resp.tokens_out, round(resp.latency_ms),
                user_id, agent_name, app_id, parent_action_id, environment,
                req.system_prompt, req.temperature, req.max_tokens,
                json.dumps(req.tool_results) if req.tool_results is not None else None,
                resp.cost_usd, handoff_from, handoff_to,
            ),
        )
        await self._db.commit()

    async def get(self, action_id: str) -> Optional[dict[str, Any]]:
        async with self._db.execute(
            "SELECT * FROM llm_calls WHERE action_id = ?", (action_id,)
        ) as cur:
            row = await cur.fetchone()
        return _sqlite_row(row) if row else None

    async def get_session(self, session_id: str) -> list[dict[str, Any]]:
        async with self._db.execute(
            "SELECT * FROM llm_calls WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [_sqlite_row(r) for r in rows]

    async def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._db.execute(
            """
            SELECT
                session_id,
                COUNT(*)         AS call_count,
                MIN(timestamp)   AS started_at,
                SUM(latency_ms)  AS total_latency_ms,
                SUM(tokens_in)   AS total_tokens_in,
                SUM(tokens_out)  AS total_tokens_out,
                SUM(cost_usd)    AS total_cost_usd,
                MAX(model_id)    AS model_id,
                MAX(agent_name)  AS agent_name,
                MAX(user_id)     AS user_id,
                MAX(environment) AS environment
            FROM llm_calls
            WHERE session_id IS NOT NULL
            GROUP BY session_id
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
        return [_sqlite_session_row(r) for r in rows]

    async def close(self) -> None:
        await self._db.close()


def _sqlite_row(row) -> dict[str, Any]:
    d = dict(row)
    for field in ("messages", "tools", "tool_calls", "tool_results"):
        if d.get(field):
            d[field] = json.loads(d[field])
    d["timestamp"] = _unix_to_iso(d["timestamp"])
    return d


def _sqlite_session_row(row) -> dict[str, Any]:
    d = dict(row)
    d["started_at"] = _unix_to_iso(d["started_at"])
    return d


def _unix_to_iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(
        ts, tz=datetime.timezone.utc
    ).isoformat()


# ── Postgres ─────────────────────────────────────────────────────────────────

class _PostgresStore(Store):

    def __init__(self, pool) -> None:
        self._pool = pool

    @classmethod
    async def _connect(cls, dsn: str) -> "_PostgresStore":
        import asyncpg
        pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_calls (
                    action_id   UUID        PRIMARY KEY,
                    session_id  UUID,
                    timestamp   TIMESTAMPTZ NOT NULL,
                    model_id    TEXT        NOT NULL,
                    provider    TEXT        NOT NULL,
                    messages    JSONB       NOT NULL,
                    tools       JSONB,
                    content     TEXT,
                    tool_calls  JSONB,
                    stop_reason TEXT,
                    tokens_in   INTEGER,
                    tokens_out  INTEGER,
                    latency_ms  INTEGER
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS llm_calls_session_idx
                ON llm_calls (session_id) WHERE session_id IS NOT NULL
            """)
            for col, col_type in _MIGRATION_COLUMNS:
                pg_type = "JSONB" if col in ("tool_results",) else col_type
                await conn.execute(
                    f"ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS {col} {pg_type}"
                )
        return cls(pool)

    async def save(self, action_id, req, resp, *, session_id=None, user_id=None,
                   agent_name=None, app_id=None, parent_action_id=None,
                   environment="development", handoff_from=None, handoff_to=None) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO llm_calls
                    (action_id, session_id, timestamp, model_id, provider,
                     messages, tools, content, tool_calls, stop_reason,
                     tokens_in, tokens_out, latency_ms,
                     user_id, agent_name, app_id, parent_action_id, environment,
                     system_prompt, temperature, max_tokens,
                     tool_results, cost_usd, handoff_from, handoff_to)
                VALUES
                    ($1,$2,to_timestamp($3),$4,$5,
                     $6::jsonb,$7::jsonb,$8,$9::jsonb,$10,
                     $11,$12,$13,
                     $14,$15,$16,$17,$18,
                     $19,$20,$21,
                     $22::jsonb,$23,$24,$25)
                """,
                uuid.UUID(action_id),
                uuid.UUID(session_id) if session_id else None,
                req.timestamp, req.model_id, req.provider,
                json.dumps(req.messages),
                json.dumps(req.tools) if req.tools is not None else None,
                resp.content,
                json.dumps(resp.tool_calls) if resp.tool_calls is not None else None,
                resp.stop_reason, resp.tokens_in, resp.tokens_out, round(resp.latency_ms),
                user_id, agent_name, app_id, parent_action_id, environment,
                req.system_prompt, req.temperature, req.max_tokens,
                json.dumps(req.tool_results) if req.tool_results is not None else None,
                resp.cost_usd, handoff_from, handoff_to,
            )

    async def get(self, action_id: str) -> Optional[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM llm_calls WHERE action_id = $1", uuid.UUID(action_id)
            )
        return _pg_row(row) if row else None

    async def get_session(self, session_id: str) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM llm_calls WHERE session_id = $1 ORDER BY timestamp ASC",
                uuid.UUID(session_id),
            )
        return [_pg_row(r) for r in rows]

    async def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    session_id::text,
                    COUNT(*)                    AS call_count,
                    MIN(timestamp)              AS started_at,
                    SUM(latency_ms)             AS total_latency_ms,
                    SUM(tokens_in)              AS total_tokens_in,
                    SUM(tokens_out)             AS total_tokens_out,
                    SUM(cost_usd)               AS total_cost_usd,
                    MAX(model_id)               AS model_id,
                    MAX(agent_name)             AS agent_name,
                    MAX(user_id)                AS user_id,
                    MAX(environment)            AS environment
                FROM llm_calls
                WHERE session_id IS NOT NULL
                GROUP BY session_id
                ORDER BY started_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [_pg_session_row(r) for r in rows]

    async def close(self) -> None:
        await self._pool.close()


def _pg_row(row) -> dict[str, Any]:
    d = dict(row)
    d["action_id"] = str(d["action_id"])
    d["session_id"] = str(d["session_id"]) if d["session_id"] else None
    d["parent_action_id"] = str(d["parent_action_id"]) if d.get("parent_action_id") else None
    d["timestamp"] = d["timestamp"].isoformat()
    return d


def _pg_session_row(row) -> dict[str, Any]:
    d = dict(row)
    d["started_at"] = d["started_at"].isoformat()
    return d
