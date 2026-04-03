"""
Storage backends for AgentLedger.

Store.connect(dsn) returns the right backend based on the DSN prefix:

  sqlite:///agentledger.db   → SQLite  (zero setup, great for development)
  postgresql://...           → Postgres (recommended for production)

Schema is created automatically on first connect.
"""

import json
import uuid
from typing import Any, Optional

from .normalize import CanonicalRequest, CanonicalResponse


class Store:
    """Common interface — do not instantiate directly, use Store.connect()."""

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
        session_id: Optional[str] = None,
    ) -> None:
        raise NotImplementedError

    async def get(self, action_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    async def get_session(self, session_id: str) -> list[dict[str, Any]]:
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
        await db.commit()
        return cls(db)

    async def save(self, action_id, req, resp, session_id=None) -> None:
        await self._db.execute(
            """
            INSERT INTO llm_calls
                (action_id, session_id, timestamp, model_id, provider,
                 messages, tools, content, tool_calls, stop_reason,
                 tokens_in, tokens_out, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                session_id,
                req.timestamp,
                req.model_id,
                req.provider,
                json.dumps(req.messages),
                json.dumps(req.tools) if req.tools is not None else None,
                resp.content,
                json.dumps(resp.tool_calls) if resp.tool_calls is not None else None,
                resp.stop_reason,
                resp.tokens_in,
                resp.tokens_out,
                round(resp.latency_ms),
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

    async def close(self) -> None:
        await self._db.close()


def _sqlite_row(row) -> dict[str, Any]:
    d = dict(row)
    for field in ("messages", "tools", "tool_calls"):
        if d.get(field):
            d[field] = json.loads(d[field])
    return d


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
            await conn.execute(
                "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS session_id UUID"
            )
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS llm_calls_session_idx
                ON llm_calls (session_id) WHERE session_id IS NOT NULL
            """)
        return cls(pool)

    async def save(self, action_id, req, resp, session_id=None) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO llm_calls
                    (action_id, session_id, timestamp, model_id, provider,
                     messages, tools, content, tool_calls, stop_reason,
                     tokens_in, tokens_out, latency_ms)
                VALUES
                    ($1, $2, to_timestamp($3), $4, $5, $6::jsonb, $7::jsonb,
                     $8, $9::jsonb, $10, $11, $12, $13)
                """,
                uuid.UUID(action_id),
                uuid.UUID(session_id) if session_id else None,
                req.timestamp,
                req.model_id,
                req.provider,
                json.dumps(req.messages),
                json.dumps(req.tools) if req.tools is not None else None,
                resp.content,
                json.dumps(resp.tool_calls) if resp.tool_calls is not None else None,
                resp.stop_reason,
                resp.tokens_in,
                resp.tokens_out,
                round(resp.latency_ms),
            )

    async def get(self, action_id: str) -> Optional[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT action_id, session_id, timestamp, model_id, provider,
                          messages, tools, content, tool_calls, stop_reason,
                          tokens_in, tokens_out, latency_ms
                   FROM llm_calls WHERE action_id = $1""",
                uuid.UUID(action_id),
            )
        return _pg_row(row) if row else None

    async def get_session(self, session_id: str) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT action_id, session_id, timestamp, model_id, provider,
                          messages, tools, content, tool_calls, stop_reason,
                          tokens_in, tokens_out, latency_ms
                   FROM llm_calls WHERE session_id = $1 ORDER BY timestamp ASC""",
                uuid.UUID(session_id),
            )
        return [_pg_row(r) for r in rows]

    async def close(self) -> None:
        await self._pool.close()


def _pg_row(row) -> dict[str, Any]:
    d = dict(row)
    d["action_id"] = str(d["action_id"])
    d["session_id"] = str(d["session_id"]) if d["session_id"] else None
    d["timestamp"] = d["timestamp"].isoformat()
    return d
