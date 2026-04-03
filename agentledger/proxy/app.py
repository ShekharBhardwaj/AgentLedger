"""
AgentLedger proxy — sits between the agent and LiteLLM (or any OpenAI-compatible
upstream).

Intercepts POST /v1/chat/completions and POST /v1/messages, assigns an action_id,
normalizes to canonical schema, stores to SQLite or Postgres, then returns the
upstream response unmodified — including full streaming support.

Session grouping:
    Pass x-agentledger-session-id in the request to group related calls.
    The proxy echoes it back in the response alongside the action_id.

Retrieval:
    GET  /explain/{action_id}      single captured call
    GET  /session/{session_id}     all calls in a run, ordered by time
    POST /mcp                      MCP tool server (explain + get_session)

Usage:
    import uvicorn
    from agentledger.proxy.app import create_app

    app = create_app(
        upstream_url="https://api.openai.com",
        dsn="sqlite:///agentledger.db",
    )
    uvicorn.run(app, host="0.0.0.0", port=8000)

Or via CLI:
    python -m agentledger.proxy
"""

import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .mcp import handle_mcp
from .normalize import normalize_request, normalize_response
from .store import Store
from .stream import reconstruct_from_sse

_LLM_PATHS = {"v1/chat/completions", "v1/messages"}


def create_app(upstream_url: str, dsn: str) -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.store = await Store.connect(dsn)
        app.state.client = httpx.AsyncClient(
            base_url=upstream_url,
            timeout=httpx.Timeout(120.0),
        )
        yield
        await app.state.store.close()
        await app.state.client.aclose()

    app = FastAPI(title="AgentLedger Proxy", lifespan=lifespan)

    # ── MCP tool server ──────────────────────────────────────────────────────

    @app.post("/mcp")
    async def mcp(request: Request) -> JSONResponse:
        return await handle_mcp(request)

    # ── Retrieval endpoints ──────────────────────────────────────────────────

    @app.get("/explain/{action_id}")
    async def explain(action_id: str, request: Request) -> JSONResponse:
        record = await request.app.state.store.get(action_id)
        if record is None:
            raise HTTPException(status_code=404, detail="action_id not found")
        return JSONResponse(record)

    @app.get("/session/{session_id}")
    async def session(session_id: str, request: Request) -> JSONResponse:
        records = await request.app.state.store.get_session(session_id)
        if not records:
            raise HTTPException(status_code=404, detail="session_id not found")
        return JSONResponse(records)

    # ── Transparent proxy ────────────────────────────────────────────────────

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy(request: Request, path: str) -> Response:
        body_bytes = await request.body()

        is_llm_path = request.method == "POST" and path in _LLM_PATHS and body_bytes
        is_streaming = is_llm_path and _is_streaming(body_bytes)
        is_llm_call = is_llm_path and not is_streaming

        action_id = str(uuid.uuid4()) if is_llm_path else None
        session_id = request.headers.get("x-agentledger-session-id")

        forward_headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length", "transfer-encoding",
                                  "x-agentledger-session-id")
        }

        if is_streaming:
            return await _streaming_proxy(
                request, path, body_bytes, forward_headers,
                action_id, session_id,
            )

        # ── Non-streaming ────────────────────────────────────────────────────
        start = time.monotonic()
        upstream_resp = await request.app.state.client.request(
            method=request.method,
            url=f"/{path}",
            content=body_bytes,
            headers=forward_headers,
            params=dict(request.query_params),
        )
        latency_ms = (time.monotonic() - start) * 1000

        if is_llm_call and upstream_resp.status_code == 200:
            try:
                req_body = json.loads(body_bytes)
                canonical_req = normalize_request(req_body, path)
                canonical_resp = normalize_response(upstream_resp.json(), latency_ms)
                await request.app.state.store.save(
                    action_id, canonical_req, canonical_resp, session_id
                )
            except Exception:
                pass

        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=_response_headers(upstream_resp.headers, action_id, session_id),
            media_type=upstream_resp.headers.get("content-type"),
        )

    return app


async def _streaming_proxy(
    request: Request,
    path: str,
    body_bytes: bytes,
    forward_headers: dict,
    action_id: str,
    session_id: str | None,
) -> StreamingResponse:
    """
    Forward a streaming (SSE) request, capturing chunks as they pass through.

    httpx's stream context manager is entered here and kept alive inside the
    async generator — it closes automatically when the generator is exhausted
    or the client disconnects.
    """
    client: httpx.AsyncClient = request.app.state.client
    store: Store = request.app.state.store

    stream_ctx = client.stream(
        method=request.method,
        url=f"/{path}",
        content=body_bytes,
        headers=forward_headers,
        params=dict(request.query_params),
    )

    upstream = await stream_ctx.__aenter__()
    start = time.monotonic()

    should_capture = upstream.status_code == 200
    canonical_req = None
    if should_capture:
        try:
            canonical_req = normalize_request(json.loads(body_bytes), path)
        except Exception:
            should_capture = False

    async def generator() -> AsyncIterator[bytes]:
        chunks: list[bytes] = []
        try:
            async for chunk in upstream.aiter_bytes():
                if should_capture:
                    chunks.append(chunk)
                yield chunk

            if should_capture and canonical_req and chunks:
                latency_ms = (time.monotonic() - start) * 1000
                try:
                    canonical_resp = reconstruct_from_sse(b"".join(chunks), latency_ms)
                    await store.save(action_id, canonical_req, canonical_resp, session_id)
                except Exception:
                    pass
        finally:
            await stream_ctx.__aexit__(None, None, None)

    return StreamingResponse(
        generator(),
        status_code=upstream.status_code,
        headers=_response_headers(upstream.headers, action_id, session_id),
        media_type=upstream.headers.get("content-type"),
    )


def _response_headers(
    upstream_headers: httpx.Headers,
    action_id: str | None,
    session_id: str | None,
) -> dict:
    headers = dict(upstream_headers)
    if action_id:
        headers["x-agentledger-action-id"] = action_id
    if session_id:
        headers["x-agentledger-session-id"] = session_id
    return headers


def _is_streaming(body_bytes: bytes) -> bool:
    try:
        return bool(json.loads(body_bytes).get("stream"))
    except Exception:
        return False
