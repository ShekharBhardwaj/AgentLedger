"""
Async Postgres storage for captured LLM calls.

One table: llm_calls.  JSONB for flexible fields (messages, tools, tool_calls).
Schema is created automatically on first connect; missing columns are added via
ALTER TABLE IF NOT EXISTS so existing deployments survive upgrades.
"""

import json
import uuid
from typing import Any, Optional

import asyncpg

from .normalize import CanonicalRequest, CanonicalResponse

_CREATE_TABLE = """
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
);
"""

# Survivable migration for deployments that have the table without session_id
_ADD_SESSION_ID = """
ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS session_id UUID;
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS llm_calls_session_id_idx ON llm_calls (session_id)
WHERE session_id IS NOT NULL;
"""

_INSERT = """
INSERT INTO llm_calls
    (action_id, session_id, timestamp, model_id, provider, messages, tools,
     content, tool_calls, stop_reason, tokens_in, tokens_out, latency_ms)
VALUES
    ($1, $2, to_timestamp($3), $4, $5, $6::jsonb, $7::jsonb,
     $8, $9::jsonb, $10, $11, $12, $13)
"""

_GET_BY_ACTION = """
SELECT action_id, session_id, timestamp, model_id, provider,
       messages, tools, content, tool_calls, stop_reason,
       tokens_in, tokens_out, latency_ms
FROM llm_calls
WHERE action_id = $1
"""

_GET_BY_SESSION = """
SELECT action_id, session_id, timestamp, model_id, provider,
       messages, tools, content, tool_calls, stop_reason,
       tokens_in, tokens_out, latency_ms
FROM llm_calls
WHERE session_id = $1
ORDER BY timestamp ASC
"""


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    d = dict(row)
    d["action_id"] = str(d["action_id"])
    d["session_id"] = str(d["session_id"]) if d["session_id"] else None
    d["timestamp"] = d["timestamp"].isoformat()
    # asyncpg returns JSONB as dicts already
    return d


class Store:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "Store":
        pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
        async with pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE)
            await conn.execute(_ADD_SESSION_ID)
            await conn.execute(_CREATE_INDEX)
        return cls(pool)

    async def save(
        self,
        action_id: str,
        req: CanonicalRequest,
        resp: CanonicalResponse,
        session_id: Optional[str] = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                _INSERT,
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
            row = await conn.fetchrow(_GET_BY_ACTION, uuid.UUID(action_id))
        return _row_to_dict(row) if row else None

    async def get_session(self, session_id: str) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_GET_BY_SESSION, uuid.UUID(session_id))
        return [_row_to_dict(r) for r in rows]

    async def close(self) -> None:
        await self._pool.close()
