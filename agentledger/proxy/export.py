"""
Compliance export — generates a signed audit trail for a session.

GET /export/{session_id}             → JSON (machine-readable, with SHA-256 hash)
GET /export/{session_id}/report      → Printable HTML report

The JSON export includes a SHA-256 hash of the calls array so the recipient
can verify the export has not been tampered with after generation.
"""

import datetime
import hashlib
import html
import json
from typing import Any


def build_export(session_id: str, calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a structured compliance export for a session."""
    calls_json = json.dumps(calls, sort_keys=True, default=str)
    integrity_hash = hashlib.sha256(calls_json.encode()).hexdigest()

    total_cost = sum(c.get("cost_usd") or 0 for c in calls)
    total_tokens_in = sum(c.get("tokens_in") or 0 for c in calls)
    total_tokens_out = sum(c.get("tokens_out") or 0 for c in calls)
    total_latency_ms = sum(c.get("latency_ms") or 0 for c in calls)
    models = sorted({c["model_id"] for c in calls if c.get("model_id")})
    agents = sorted({c["agent_name"] for c in calls if c.get("agent_name")})
    errors = [c for c in calls if (c.get("status_code") or 200) != 200]

    return {
        "export": {
            "generated_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            "generator":    "AgentLedger",
            "integrity":    f"sha256:{integrity_hash}",
        },
        "session": {
            "session_id":      session_id,
            "started_at":      calls[0]["timestamp"] if calls else None,
            "ended_at":        calls[-1]["timestamp"] if calls else None,
            "call_count":      len(calls),
            "error_count":     len(errors),
            "models":          models,
            "agents":          agents,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_latency_ms": round(total_latency_ms),
            "total_cost_usd":  round(total_cost, 8) if total_cost else None,
        },
        "calls": calls,
    }


def render_html_report(export: dict[str, Any]) -> str:
    """Render the compliance export as a printable HTML page."""
    session = export["session"]
    meta = export["export"]
    calls = export["calls"]

    def esc(v: Any) -> str:
        return html.escape(str(v)) if v is not None else "—"

    def fmt_cost(v: Any) -> str:
        if v is None:
            return "—"
        return f"${float(v):.6f}"

    def fmt_ms(v: Any) -> str:
        if v is None:
            return "—"
        ms = float(v)
        return f"{ms / 1000:.1f}s" if ms >= 1000 else f"{ms:.0f}ms"

    def render_call(call: dict, n: int) -> str:
        is_error = (call.get("status_code") or 200) != 200
        status_style = "color:#ef4444" if is_error else "color:#22c55e"
        status_text = f"HTTP {call.get('status_code', 200)}"
        if is_error and call.get("error_detail"):
            status_text += f" — {call['error_detail'][:120]}"

        msgs = call.get("messages") or []
        last_user = next(
            (m.get("content", "") for m in reversed(msgs) if m.get("role") == "user"),
            None,
        )
        if isinstance(last_user, list):
            last_user = next((b.get("text") for b in last_user if b.get("type") == "text"), None)

        tool_calls_html = ""
        if call.get("tool_calls"):
            items = "".join(
                f"<li><code>{esc(tc.get('name','?'))}</code> — "
                f"<span style='color:#888;font-size:11px'>{esc(str(tc.get('arguments',''))[:200])}</span></li>"
                for tc in call["tool_calls"]
            )
            tool_calls_html = f"<p class='label'>Tool calls</p><ul>{items}</ul>"

        tool_results_html = ""
        if call.get("tool_results"):
            items = "".join(
                f"<li><code>{esc(tr.get('tool_call_id') or tr.get('tool_use_id','?'))}</code> — "
                f"<span style='color:#888;font-size:11px'>{esc(str(tr.get('content',''))[:200])}</span></li>"
                for tr in call["tool_results"]
            )
            tool_results_html = f"<p class='label'>Tool results</p><ul>{items}</ul>"

        handoff_html = ""
        if call.get("handoff_from") or call.get("handoff_to"):
            handoff_html = (
                f"<p class='label'>Handoff</p>"
                f"<p>{esc(call.get('handoff_from',''))} → {esc(call.get('handoff_to',''))}</p>"
            )

        return f"""
        <div class="call {'call-error' if is_error else ''}">
          <div class="call-header">
            <span class="call-n">#{n}</span>
            <span class="call-model">{esc(call.get('model_id',''))}</span>
            <span style="{status_style};font-size:12px;margin-left:auto">{esc(status_text)}</span>
          </div>
          <table class="meta">
            <tr><td>Action ID</td><td><code>{esc(call.get('action_id',''))}</code></td>
                <td>Timestamp</td><td>{esc(call.get('timestamp',''))}</td></tr>
            <tr><td>Agent</td><td>{esc(call.get('agent_name',''))}</td>
                <td>User</td><td>{esc(call.get('user_id',''))}</td></tr>
            <tr><td>Environment</td><td>{esc(call.get('environment',''))}</td>
                <td>Stop reason</td><td>{esc(call.get('stop_reason',''))}</td></tr>
            <tr><td>Tokens in / out</td><td>{esc(call.get('tokens_in',''))} / {esc(call.get('tokens_out',''))}</td>
                <td>Cost</td><td>{fmt_cost(call.get('cost_usd'))}</td></tr>
            <tr><td>Latency</td><td>{fmt_ms(call.get('latency_ms'))}</td>
                <td>Temperature</td><td>{esc(call.get('temperature',''))}</td></tr>
          </table>
          {f'<p class="label">System prompt</p><pre>{esc(call.get("system_prompt",""))}</pre>' if call.get("system_prompt") else ""}
          {f'<p class="label">Input (last user message)</p><pre>{esc(last_user)}</pre>' if last_user else ""}
          {tool_results_html}
          {tool_calls_html}
          {f'<p class="label">Output</p><pre>{esc(call.get("content",""))}</pre>' if call.get("content") else ""}
          {handoff_html}
          {f'<p class="label" style="color:#ef4444">Error</p><pre>{esc(call.get("error_detail",""))}</pre>' if is_error and call.get("error_detail") else ""}
        </div>
        """

    calls_html = "".join(render_call(c, i + 1) for i, c in enumerate(calls))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>AgentLedger Export — {esc(session['session_id'])}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 13px;
          color: #111; background: #fff; padding: 40px; max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  h2 {{ font-size: 14px; font-weight: 600; margin: 24px 0 8px; color: #333; border-bottom: 1px solid #e5e5e5; padding-bottom: 4px; }}
  .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; margin-bottom: 16px; }}
  .meta-grid div {{ font-size: 12px; color: #555; }}
  .meta-grid strong {{ color: #111; }}
  .integrity {{ font-family: monospace; font-size: 11px; color: #666; background: #f5f5f5;
                padding: 8px 12px; border-radius: 4px; margin-bottom: 24px; word-break: break-all; }}
  .call {{ border: 1px solid #e5e5e5; border-radius: 6px; margin-bottom: 16px; overflow: hidden; page-break-inside: avoid; }}
  .call-error {{ border-color: #fca5a5; }}
  .call-header {{ background: #f9f9f9; padding: 8px 12px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid #e5e5e5; }}
  .call-error .call-header {{ background: #fff5f5; }}
  .call-n {{ font-size: 11px; color: #999; font-weight: 600; width: 24px; }}
  .call-model {{ font-family: monospace; font-size: 12px; font-weight: 600; color: #1d4ed8; }}
  table.meta {{ width: 100%; border-collapse: collapse; font-size: 11px; margin: 10px 12px; width: calc(100% - 24px); }}
  table.meta td {{ padding: 2px 8px 2px 0; color: #555; vertical-align: top; }}
  table.meta td:nth-child(odd) {{ color: #999; width: 120px; }}
  .label {{ font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
             color: #999; margin: 10px 12px 4px; }}
  pre {{ margin: 0 12px 10px; background: #f9f9f9; padding: 8px 10px; border-radius: 4px;
         font-size: 11px; white-space: pre-wrap; word-break: break-word; color: #333; max-height: 200px; overflow: auto; }}
  ul {{ margin: 0 12px 10px 24px; }}
  ul li {{ font-size: 12px; margin-bottom: 2px; color: #333; }}
  code {{ font-family: monospace; font-size: 11px; background: #f0f0f0; padding: 1px 4px; border-radius: 3px; }}
  .footer {{ margin-top: 40px; font-size: 11px; color: #999; border-top: 1px solid #e5e5e5; padding-top: 16px; }}
  @media print {{
    body {{ padding: 20px; }}
    .call {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>

<h1>AgentLedger — Session Audit Report</h1>
<p style="color:#666;font-size:12px;margin:4px 0 20px">Generated {esc(meta['generated_at'])}</p>

<h2>Session Summary</h2>
<div class="meta-grid">
  <div><strong>Session ID:</strong> {esc(session['session_id'])}</div>
  <div><strong>Call count:</strong> {esc(session['call_count'])} ({esc(session['error_count'])} errors)</div>
  <div><strong>Started:</strong> {esc(session['started_at'])}</div>
  <div><strong>Ended:</strong> {esc(session['ended_at'])}</div>
  <div><strong>Models:</strong> {esc(', '.join(session['models']))}</div>
  <div><strong>Agents:</strong> {esc(', '.join(session['agents']) if session['agents'] else '—')}</div>
  <div><strong>Tokens in / out:</strong> {esc(session['total_tokens_in'])} / {esc(session['total_tokens_out'])}</div>
  <div><strong>Total cost:</strong> {fmt_cost(session['total_cost_usd'])}</div>
  <div><strong>Total latency:</strong> {fmt_ms(session['total_latency_ms'])}</div>
</div>

<div class="integrity">Integrity: {esc(meta['integrity'])}</div>

<h2>Calls ({esc(session['call_count'])})</h2>
{calls_html}

<div class="footer">
  Generated by AgentLedger &mdash; {esc(meta['generated_at'])}<br>
  Verify integrity: <code>echo -n '&lt;calls_array_json&gt;' | sha256sum</code>
</div>

</body>
</html>"""
