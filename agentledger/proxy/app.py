"""
AgentLedger proxy — sits between the agent and LiteLLM (or any OpenAI-compatible
upstream).

Intercepts POST /v1/chat/completions and POST /v1/messages, assigns an action_id,
normalizes to canonical schema, stores to SQLite or Postgres, then returns the
upstream response unmodified — including full streaming support.

Caller-supplied headers (all optional):
    x-agentledger-session-id       Group calls into a run
    x-agentledger-user-id          End user who triggered this
    x-agentledger-agent-name       Which agent made this call
    x-agentledger-app-id           Which application
    x-agentledger-parent-action-id Parent in the call graph
    x-agentledger-environment      prod / staging / development (default)

Endpoints:
    GET  /                         Dashboard
    GET  /api/sessions             List recent sessions
    GET  /explain/{action_id}      Single captured call
    GET  /session/{session_id}     All calls in a run, ordered by time
    POST /mcp                      MCP tool server

Or via CLI:
    python -m agentledger.proxy
"""

import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from .dashboard import get_dashboard_html
from .mcp import handle_mcp
from .normalize import normalize_request, normalize_response
from .store import Store
from .stream import reconstruct_from_sse

_LLM_PATHS = {"v1/chat/completions", "v1/messages"}

_AL_HEADERS = {
    "x-agentledger-session-id",
    "x-agentledger-user-id",
    "x-agentledger-agent-name",
    "x-agentledger-app-id",
    "x-agentledger-parent-action-id",
    "x-agentledger-environment",
    "x-agentledger-handoff-from",
    "x-agentledger-handoff-to",
}


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

    _api_key = os.environ.get("AGENTLEDGER_API_KEY")

    def _check_auth(request: Request) -> None:
        """Raise 401 if an API key is configured and the request doesn't supply it."""
        if not _api_key:
            return
        supplied = request.headers.get("x-agentledger-api-key") or request.query_params.get("api_key")
        if supplied != _api_key:
            raise HTTPException(status_code=401, detail="Unauthorized")

    # ── Dashboard ────────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        _check_auth(request)
        return HTMLResponse(get_dashboard_html())

    # ── API ──────────────────────────────────────────────────────────────────

    @app.get("/api/sessions")
    async def api_sessions(request: Request) -> JSONResponse:
        _check_auth(request)
        sessions = await request.app.state.store.list_sessions()
        return JSONResponse(sessions)

    @app.get("/explain/{action_id}")
    async def explain(action_id: str, request: Request) -> JSONResponse:
        _check_auth(request)
        record = await request.app.state.store.get(action_id)
        if record is None:
            raise HTTPException(status_code=404, detail="action_id not found")
        return JSONResponse(record)

    @app.get("/session/{session_id}")
    async def session(session_id: str, request: Request) -> JSONResponse:
        _check_auth(request)
        records = await request.app.state.store.get_session(session_id)
        if not records:
            raise HTTPException(status_code=404, detail="session_id not found")
        return JSONResponse(records)

    # ── MCP ──────────────────────────────────────────────────────────────────

    @app.post("/mcp")
    async def mcp(request: Request) -> JSONResponse:
        return await handle_mcp(request)

    # ── Transparent proxy ────────────────────────────────────────────────────

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy(request: Request, path: str) -> Response:
        body_bytes = await request.body()

        is_llm_path = request.method == "POST" and path in _LLM_PATHS and body_bytes
        is_streaming = is_llm_path and _is_streaming(body_bytes)
        is_llm_call = is_llm_path and not is_streaming

        action_id = str(uuid.uuid4()) if is_llm_path else None
        meta = _extract_meta(request)

        forward_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length", "transfer-encoding")
            and k.lower() not in _AL_HEADERS
        }

        if is_streaming:
            return await _streaming_proxy(
                request, path, body_bytes, forward_headers, action_id, meta
            )

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
                canonical_resp = normalize_response(upstream_resp.json(), latency_ms, canonical_req.model_id)
                await request.app.state.store.save(
                    action_id, canonical_req, canonical_resp, **meta
                )
            except Exception:
                pass

        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=_response_headers(upstream_resp.headers, action_id, meta),
            media_type=upstream_resp.headers.get("content-type"),
        )

    return app


async def _streaming_proxy(
    request: Request,
    path: str,
    body_bytes: bytes,
    forward_headers: dict,
    action_id: str,
    meta: dict,
) -> StreamingResponse:
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
                    canonical_resp = reconstruct_from_sse(b"".join(chunks), latency_ms, canonical_req.model_id)
                    await store.save(action_id, canonical_req, canonical_resp, **meta)
                except Exception:
                    pass
        finally:
            await stream_ctx.__aexit__(None, None, None)

    return StreamingResponse(
        generator(),
        status_code=upstream.status_code,
        headers=_response_headers(upstream.headers, action_id, meta),
        media_type=upstream.headers.get("content-type"),
    )


def _extract_meta(request: Request) -> dict:
    h = request.headers
    return {
        "session_id":       h.get("x-agentledger-session-id"),
        "user_id":          h.get("x-agentledger-user-id"),
        "agent_name":       h.get("x-agentledger-agent-name"),
        "app_id":           h.get("x-agentledger-app-id"),
        "parent_action_id": h.get("x-agentledger-parent-action-id"),
        "environment":      h.get("x-agentledger-environment", "development"),
        "handoff_from":     h.get("x-agentledger-handoff-from"),
        "handoff_to":       h.get("x-agentledger-handoff-to"),
    }


def _response_headers(
    upstream_headers: httpx.Headers,
    action_id: str | None,
    meta: dict,
) -> dict:
    # httpx auto-decompresses responses, so strip content-encoding to prevent
    # the client from trying to decompress already-decompressed content.
    headers = {
        k: v for k, v in upstream_headers.items()
        if k.lower() not in ("content-encoding", "transfer-encoding")
    }
    if action_id:
        headers["x-agentledger-action-id"] = action_id
    if meta.get("session_id"):
        headers["x-agentledger-session-id"] = meta["session_id"]
    return headers


def _is_streaming(body_bytes: bytes) -> bool:
    try:
        return bool(json.loads(body_bytes).get("stream"))
    except Exception:
        return False
