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
    x-agentledger-handoff-from     Agent handing off control
    x-agentledger-handoff-to       Agent receiving control

Endpoints:
    GET  /                             Dashboard (live via WebSocket)
    GET  /api/sessions                 List recent sessions
    GET  /api/search?q=...             Full-text search across calls
    GET  /explain/{action_id}          Single captured call
    GET  /session/{session_id}         All calls in a run, ordered by time
    GET  /export/{session_id}          JSON compliance export
    GET  /export/{session_id}/report   Printable HTML audit report
    WS   /ws                           Live event stream (new calls as they happen)
    POST /mcp                          MCP tool server

Or via CLI:
    python -m agentledger.proxy
"""

import datetime
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from .dashboard import get_dashboard_html
from .alerts import AlertConfig, check_and_fire
from .otel import emit_span
from .ratelimit import RateLimitConfig, RateLimiter
from .export import build_export, render_html_report
from .mcp import handle_mcp
from .normalize import CanonicalRequest, CanonicalResponse, normalize_request, normalize_response
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


class _Broadcaster:
    """Fanout to all connected WebSocket clients."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, data: dict) -> None:
        dead: set[WebSocket] = set()
        for client in self._clients:
            try:
                await client.send_json(data)
            except Exception:
                dead.add(client)
        self._clients -= dead


def create_app(
    upstream_url: str,
    dsn: str,
    budget_session: Optional[float] = None,
    budget_agent: Optional[float] = None,
    budget_daily: Optional[float] = None,
    alert_config: Optional[AlertConfig] = None,
    rate_limit_config: Optional[RateLimitConfig] = None,
) -> FastAPI:

    broadcaster = _Broadcaster()
    _rate_limiter = RateLimiter(rate_limit_config or RateLimitConfig())
    _alert_config = alert_config or AlertConfig(
        webhook_url=None, cost_per_call=None,
        latency_ms=None, error_rate=None, daily_spend=None,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.store = await Store.connect(dsn)
        app.state.client = httpx.AsyncClient(
            base_url=upstream_url,
            timeout=httpx.Timeout(120.0),
        )
        app.state.broadcaster = broadcaster
        yield
        await app.state.store.close()
        await app.state.client.aclose()

    app = FastAPI(title="AgentLedger Proxy", lifespan=lifespan)

    _api_key = os.environ.get("AGENTLEDGER_API_KEY")

    def _check_auth(request: Request) -> None:
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

    # ── WebSocket (live events) ───────────────────────────────────────────────

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await broadcaster.connect(websocket)
        try:
            while True:
                await websocket.receive_text()  # keep-alive; client sends pings
        except WebSocketDisconnect:
            broadcaster.disconnect(websocket)

    # ── API ──────────────────────────────────────────────────────────────────

    @app.get("/api/sessions")
    async def api_sessions(request: Request) -> JSONResponse:
        _check_auth(request)
        sessions = await request.app.state.store.list_sessions()
        return JSONResponse(sessions)

    @app.get("/api/search")
    async def api_search(request: Request, q: str = "") -> JSONResponse:
        _check_auth(request)
        if not q.strip():
            return JSONResponse([])
        results = await request.app.state.store.search(q.strip())
        return JSONResponse(results)

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

    # ── Compliance export ─────────────────────────────────────────────────────

    @app.get("/export/{session_id}")
    async def export_json(session_id: str, request: Request) -> Response:
        _check_auth(request)
        calls = await request.app.state.store.get_session(session_id)
        if not calls:
            raise HTTPException(status_code=404, detail="session_id not found")
        export = build_export(session_id, calls)
        filename = f"agentledger-{session_id[:16]}.json"
        return Response(
            content=json.dumps(export, indent=2, default=str),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/export/{session_id}/report")
    async def export_report(session_id: str, request: Request) -> HTMLResponse:
        _check_auth(request)
        calls = await request.app.state.store.get_session(session_id)
        if not calls:
            raise HTTPException(status_code=404, detail="session_id not found")
        export = build_export(session_id, calls)
        return HTMLResponse(render_html_report(export))

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

        # ── Rate limit check ─────────────────────────────────────────────────
        if is_llm_path:
            rate_error = _rate_limiter.check(
                meta.get("session_id"), meta.get("agent_name"), meta.get("user_id")
            )
            if rate_error:
                return JSONResponse(
                    {"error": {"type": "rate_limit_exceeded", "message": rate_error}},
                    status_code=429,
                )

        # ── Budget check ─────────────────────────────────────────────────────
        if is_llm_path and (budget_session or budget_agent or budget_daily):
            budget_error = await _check_budgets(
                request.app.state.store, meta,
                budget_session, budget_agent, budget_daily,
            )
            if budget_error:
                return JSONResponse(
                    {"error": {"type": "budget_exceeded", "message": budget_error}},
                    status_code=429,
                )

        forward_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length", "transfer-encoding")
            and k.lower() not in _AL_HEADERS
        }

        if is_streaming:
            return await _streaming_proxy(
                request, path, body_bytes, forward_headers, action_id, meta,
                broadcaster, _alert_config,
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

        if is_llm_call:
            try:
                req_body = json.loads(body_bytes)
                canonical_req = normalize_request(req_body, path)
                status_code = upstream_resp.status_code
                if status_code == 200:
                    canonical_resp = normalize_response(
                        upstream_resp.json(), latency_ms, canonical_req.model_id
                    )
                    error_detail = None
                else:
                    canonical_resp = _empty_response(latency_ms)
                    error_detail = _extract_error(upstream_resp)
                await request.app.state.store.save(
                    action_id, canonical_req, canonical_resp,
                    status_code=status_code, error_detail=error_detail, **meta,
                )
                emit_span(
                    action_id, canonical_req, canonical_resp,
                    status_code=status_code, **meta,
                )
                await broadcaster.broadcast({
                    "type": "call",
                    "action_id": action_id,
                    "session_id": meta.get("session_id"),
                    "status_code": status_code,
                })
                await check_and_fire(
                    _alert_config, request.app.state.store,
                    canonical_resp, action_id,
                    meta.get("session_id"), meta.get("agent_name"), status_code,
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
    broadcaster: _Broadcaster,
    alert_config: Optional[AlertConfig] = None,
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
                    canonical_resp = reconstruct_from_sse(
                        b"".join(chunks), latency_ms, canonical_req.model_id
                    )
                    await store.save(
                        action_id, canonical_req, canonical_resp,
                        status_code=200, **meta,
                    )
                    emit_span(
                        action_id, canonical_req, canonical_resp,
                        status_code=200, **meta,
                    )
                    await broadcaster.broadcast({
                        "type": "call",
                        "action_id": action_id,
                        "session_id": meta.get("session_id"),
                        "status_code": 200,
                    })
                    if alert_config:
                        await check_and_fire(
                            alert_config, store, canonical_resp, action_id,
                            meta.get("session_id"), meta.get("agent_name"), 200,
                        )
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


async def _check_budgets(
    store: Store,
    meta: dict,
    budget_session: Optional[float],
    budget_agent: Optional[float],
    budget_daily: Optional[float],
) -> Optional[str]:
    """Return an error message if any budget is exceeded, else None."""
    session_id = meta.get("session_id")
    agent_name = meta.get("agent_name")

    if budget_session and session_id:
        spent = await store.get_session_cost(session_id)
        if spent >= budget_session:
            return (
                f"Session budget of ${budget_session:.4f} exceeded "
                f"(current spend: ${spent:.4f}). Session: {session_id}"
            )

    if budget_agent and agent_name:
        since = _today_start_ts()
        spent = await store.get_agent_cost(agent_name, since)
        if spent >= budget_agent:
            return (
                f"Agent daily budget of ${budget_agent:.4f} exceeded "
                f"(current spend: ${spent:.4f}). Agent: {agent_name}"
            )

    if budget_daily:
        since = _today_start_ts()
        spent = await store.get_period_cost(since)
        if spent >= budget_daily:
            return (
                f"Daily budget of ${budget_daily:.4f} exceeded "
                f"(current spend: ${spent:.4f})."
            )

    return None


def _today_start_ts() -> float:
    today = datetime.datetime.now(tz=datetime.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return today.timestamp()


def _empty_response(latency_ms: float) -> CanonicalResponse:
    return CanonicalResponse(
        content=None, tool_calls=None, stop_reason=None,
        tokens_in=None, tokens_out=None, latency_ms=latency_ms,
    )


def _extract_error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error", {})
        if isinstance(err, dict):
            return err.get("message") or resp.text[:300]
        return str(err)[:300]
    except Exception:
        return resp.text[:300]


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
