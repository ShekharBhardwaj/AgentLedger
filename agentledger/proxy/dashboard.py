"""
Serves the AgentLedger visual dashboard at GET /.
Single-file HTML/CSS/JS — no build step, no external dependencies.
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentLedger</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0a0a0a;
    color: #e0e0e0;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  header {
    padding: 12px 20px;
    border-bottom: 1px solid #1e1e1e;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-shrink: 0;
  }
  header h1 { font-size: 15px; font-weight: 600; color: #fff; letter-spacing: -0.3px; }
  .live-dot { width: 8px; height: 8px; border-radius: 50%; background: #555; transition: background 0.3s; flex-shrink: 0; }
  .live-dot.connected { background: #22c55e; }

  .search-wrap {
    margin-left: auto;
    position: relative;
  }
  .search-input {
    background: #141414;
    border: 1px solid #2a2a2a;
    color: #e0e0e0;
    font-size: 12px;
    padding: 5px 10px 5px 28px;
    border-radius: 6px;
    width: 220px;
    outline: none;
    transition: border-color 0.15s;
  }
  .search-input:focus { border-color: #444; }
  .search-input::placeholder { color: #444; }
  .search-icon {
    position: absolute;
    left: 8px;
    top: 50%;
    transform: translateY(-50%);
    color: #444;
    font-size: 12px;
    pointer-events: none;
  }

  .layout {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  /* Sessions panel */
  .sessions-panel {
    width: 280px;
    border-right: 1px solid #1e1e1e;
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    overflow: hidden;
  }
  .panel-header {
    padding: 12px 16px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #666;
    border-bottom: 1px solid #1a1a1a;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-shrink: 0;
  }
  .refresh-btn {
    background: none;
    border: 1px solid #333;
    color: #888;
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .refresh-btn:hover { border-color: #555; color: #ccc; }

  .sessions-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }
  .sessions-list::-webkit-scrollbar { width: 4px; }
  .sessions-list::-webkit-scrollbar-track { background: transparent; }
  .sessions-list::-webkit-scrollbar-thumb { background: #333; border-radius: 2px; }

  .session-item {
    padding: 10px 12px;
    border-radius: 6px;
    cursor: pointer;
    margin-bottom: 2px;
    transition: background 0.1s;
    border: 1px solid transparent;
  }
  .session-item:hover { background: #141414; }
  .session-item.active { background: #141414; border-color: #2a2a2a; }

  .session-id {
    font-size: 13px;
    font-weight: 500;
    color: #c8b5f5;
    font-family: "SF Mono", "Fira Code", monospace;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .session-meta {
    font-size: 11px;
    color: #555;
    margin-top: 3px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .session-meta span { display: flex; align-items: center; gap: 3px; }

  .empty-state {
    padding: 32px 16px;
    text-align: center;
    color: #444;
    font-size: 13px;
    line-height: 1.6;
  }

  /* Search results */
  .search-result-item {
    padding: 10px 12px;
    border-radius: 6px;
    cursor: pointer;
    margin-bottom: 2px;
    border: 1px solid transparent;
    transition: background 0.1s;
  }
  .search-result-item:hover { background: #141414; }
  .search-result-model {
    font-size: 12px;
    font-weight: 500;
    color: #60a5fa;
    font-family: "SF Mono", "Fira Code", monospace;
  }
  .search-result-snippet {
    font-size: 11px;
    color: #555;
    margin-top: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Detail panel */
  .detail-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .detail-header {
    padding: 12px 20px;
    border-bottom: 1px solid #1a1a1a;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 16px;
    min-height: 45px;
  }
  .detail-session-id {
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 13px;
    color: #c8b5f5;
    font-weight: 500;
  }
  .detail-stats {
    display: flex;
    gap: 16px;
    font-size: 12px;
    color: #555;
  }
  .detail-stats strong { color: #999; }

  .export-btn {
    margin-left: auto;
    display: flex;
    gap: 6px;
  }
  .export-link {
    font-size: 11px;
    color: #666;
    text-decoration: none;
    border: 1px solid #2a2a2a;
    padding: 3px 8px;
    border-radius: 4px;
    transition: all 0.15s;
  }
  .export-link:hover { border-color: #444; color: #ccc; }

  .detail-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px;
  }
  .detail-body::-webkit-scrollbar { width: 4px; }
  .detail-body::-webkit-scrollbar-track { background: transparent; }
  .detail-body::-webkit-scrollbar-thumb { background: #333; border-radius: 2px; }

  .placeholder {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #333;
    font-size: 13px;
  }

  /* Call cards */
  .call-card {
    background: #111;
    border: 1px solid #1e1e1e;
    border-radius: 8px;
    margin-bottom: 12px;
    overflow: hidden;
  }
  .call-card.call-error { border-color: #3a1a1a; }
  .call-card-header {
    padding: 10px 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    border-bottom: 1px solid #1a1a1a;
    background: #0d0d0d;
  }
  .call-card.call-error .call-card-header { background: #130808; }
  .call-number {
    font-size: 11px;
    color: #444;
    font-weight: 600;
    width: 20px;
  }
  .call-model {
    font-size: 12px;
    font-weight: 600;
    color: #60a5fa;
    font-family: "SF Mono", "Fira Code", monospace;
  }
  .call-badges {
    display: flex;
    gap: 6px;
    margin-left: auto;
    align-items: center;
    flex-wrap: wrap;
  }
  .badge {
    font-size: 11px;
    padding: 2px 7px;
    border-radius: 4px;
    font-weight: 500;
  }
  .badge-latency { background: #1a2a1a; color: #4ade80; }
  .badge-tokens  { background: #1a1a2a; color: #818cf8; }
  .badge-stop    { background: #2a1a1a; color: #f87171; }
  .badge-stop.end_turn, .badge-stop.stop { background: #1a2a1a; color: #4ade80; }
  .badge-stop.tool_calls, .badge-stop.tool_use { background: #2a2a1a; color: #fbbf24; }
  .badge-cost    { background: #1a2510; color: #86efac; }
  .badge-error   { background: #3a1010; color: #f87171; }

  .call-card-body { padding: 12px 14px; }

  .call-meta-row {
    display: flex;
    gap: 16px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }
  .meta-item { font-size: 11px; }
  .meta-label { color: #444; margin-right: 4px; }
  .meta-value { color: #888; font-family: "SF Mono", "Fira Code", monospace; }

  .section-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #444;
    margin-bottom: 6px;
    margin-top: 12px;
  }
  .section-label:first-of-type { margin-top: 0; }
  .section-label.error-label { color: #7f1d1d; }

  .message-bubble {
    background: #0d0d0d;
    border: 1px solid #1e1e1e;
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 12px;
    color: #ccc;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 160px;
    overflow-y: auto;
    margin-bottom: 4px;
    font-family: inherit;
  }
  .message-bubble.system-prompt { color: #888; font-style: italic; border-color: #252525; }
  .message-bubble.output { color: #e0e0e0; border-color: #2a2a2a; }
  .message-bubble.error-bubble { color: #f87171; border-color: #3a1a1a; background: #130808; }

  .tool-call {
    background: #0d0d0d;
    border: 1px solid #2a2510;
    border-radius: 6px;
    padding: 8px 10px;
    margin-bottom: 4px;
    font-size: 12px;
  }
  .tool-name {
    font-family: "SF Mono", "Fira Code", monospace;
    color: #fbbf24;
    font-weight: 600;
    margin-bottom: 4px;
  }
  .tool-args {
    color: #666;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 11px;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .tool-result {
    background: #0d1a0d;
    border: 1px solid #1a3a1a;
    border-radius: 6px;
    padding: 8px 10px;
    margin-bottom: 4px;
    font-size: 12px;
  }
  .tool-result-id {
    font-family: "SF Mono", "Fira Code", monospace;
    color: #4ade80;
    font-size: 10px;
    margin-bottom: 4px;
  }
  .tool-result-content {
    color: #666;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 11px;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .parent-link {
    font-size: 11px;
    color: #555;
    font-family: "SF Mono", "Fira Code", monospace;
    margin-top: 4px;
  }
  .parent-link a { color: #c8b5f5; text-decoration: none; cursor: pointer; }
  .parent-link a:hover { text-decoration: underline; }

  .handoff-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    background: #1a1225;
    border: 1px solid #3b2a5a;
    color: #c8b5f5;
    padding: 3px 8px;
    border-radius: 4px;
    margin-top: 6px;
    font-family: "SF Mono", "Fira Code", monospace;
  }
  .handoff-arrow { color: #7c3aed; }
</style>
</head>
<body>

<header>
  <div class="live-dot" id="live-dot"></div>
  <h1>AgentLedger</h1>
  <div class="search-wrap">
    <span class="search-icon">⌕</span>
    <input class="search-input" id="search-input" type="text"
           placeholder="Search prompts, outputs, agents…" autocomplete="off">
  </div>
</header>

<div class="layout">
  <div class="sessions-panel">
    <div class="panel-header">
      <span id="panel-title">Sessions</span>
      <button class="refresh-btn" onclick="loadSessions()">Refresh</button>
    </div>
    <div class="sessions-list" id="sessions-list">
      <div class="empty-state">Loading sessions…</div>
    </div>
  </div>

  <div class="detail-panel">
    <div class="detail-header" id="detail-header"></div>
    <div class="detail-body" id="detail-body">
      <div class="placeholder">Select a session to inspect</div>
    </div>
  </div>
</div>

<script>
let activeSessionId = null;
let sessionRefreshTimer = null;
let searchDebounce = null;

// ── Utilities ────────────────────────────────────────────────────────────────

function timeAgo(isoStr) {
  const diff = Date.now() - new Date(isoStr).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)   return s + 's ago';
  if (s < 3600) return Math.floor(s / 60) + 'm ago';
  if (s < 86400) return Math.floor(s / 3600) + 'h ago';
  return Math.floor(s / 86400) + 'd ago';
}

function ms(val) {
  if (val == null) return '—';
  return val >= 1000 ? (val / 1000).toFixed(1) + 's' : Math.round(val) + 'ms';
}

function cost(val) {
  if (val == null || val === 0) return null;
  if (val < 0.001) return '<$0.001';
  return '$' + val.toFixed(4);
}

function shortId(id) {
  if (!id) return '—';
  return id.length > 12 ? id.slice(0, 8) + '…' : id;
}

function formatArgs(args) {
  if (!args) return '';
  if (typeof args === 'object') return JSON.stringify(args, null, 2);
  try { return JSON.stringify(JSON.parse(args), null, 2); }
  catch { return args; }
}

function lastUserMessage(messages) {
  if (!Array.isArray(messages)) return null;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === 'user') {
      if (typeof m.content === 'string') return m.content;
      if (Array.isArray(m.content)) {
        const text = m.content.find(b => b.type === 'text');
        if (text) return text.text;
      }
    }
  }
  return null;
}

function escHtml(str) {
  if (str == null) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── WebSocket (live updates) ──────────────────────────────────────────────────

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  const dot = document.getElementById('live-dot');

  ws.onopen = () => dot.classList.add('connected');
  ws.onclose = () => {
    dot.classList.remove('connected');
    setTimeout(connectWS, 3000); // reconnect
  };
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'call') {
      // Refresh session list silently
      loadSessions(true);
      // If the new call belongs to the active session, refresh it too
      if (data.session_id && data.session_id === activeSessionId) {
        loadSession(activeSessionId, true);
      }
    }
  };

  // Keep-alive ping every 25s
  setInterval(() => { if (ws.readyState === 1) ws.send('ping'); }, 25000);
}

// ── Search ───────────────────────────────────────────────────────────────────

document.getElementById('search-input').addEventListener('input', (e) => {
  clearTimeout(searchDebounce);
  const q = e.target.value.trim();
  if (!q) {
    document.getElementById('panel-title').textContent = 'Sessions';
    loadSessions();
    return;
  }
  searchDebounce = setTimeout(() => doSearch(q), 300);
});

async function doSearch(q) {
  document.getElementById('panel-title').textContent = 'Search results';
  const el = document.getElementById('sessions-list');
  el.innerHTML = '<div class="empty-state">Searching…</div>';
  try {
    const res = await fetch('/api/search?q=' + encodeURIComponent(q));
    const results = await res.json();
    if (!results.length) {
      el.innerHTML = '<div class="empty-state">No results.</div>';
      return;
    }
    el.innerHTML = results.map(r => {
      const snippet = r.content || lastUserMessage(r.messages) || '';
      return `
        <div class="search-result-item" onclick="showSearchResult('${escHtml(r.action_id)}', '${escHtml(r.session_id || '')}')">
          <div class="search-result-model">${escHtml(r.model_id)}</div>
          <div class="search-result-snippet">${escHtml(snippet.slice(0, 80))}</div>
          <div class="session-meta"><span>${escHtml(r.agent_name || '')}</span><span>${timeAgo(r.timestamp)}</span></div>
        </div>
      `;
    }).join('');
  } catch(e) {
    el.innerHTML = '<div class="empty-state">Search failed.</div>';
  }
}

async function showSearchResult(actionId, sessionId) {
  if (sessionId) {
    await loadSession(sessionId);
    // Scroll to the specific call card
    setTimeout(() => {
      const el = document.getElementById('call-' + actionId);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 300);
  } else {
    // No session — fetch and show the single call
    const res = await fetch('/explain/' + actionId);
    if (!res.ok) return;
    const call = await res.json();
    document.getElementById('detail-header').innerHTML =
      `<span class="detail-session-id">${escHtml(call.model_id)}</span>`;
    document.getElementById('detail-body').innerHTML = renderCall(call, 1);
  }
}

// ── Sessions list ────────────────────────────────────────────────────────────

async function loadSessions(silent = false) {
  const el = document.getElementById('sessions-list');
  try {
    const res = await fetch('/api/sessions');
    const sessions = await res.json();
    if (!sessions.length) {
      if (!silent) el.innerHTML = '<div class="empty-state">No sessions yet.<br>Make an LLM call through the proxy to get started.</div>';
      return;
    }
    el.innerHTML = sessions.map(s => {
      const c = cost(s.total_cost_usd);
      return `
      <div class="session-item ${s.session_id === activeSessionId ? 'active' : ''}"
           onclick="loadSession('${escHtml(s.session_id)}')">
        <div class="session-id">${escHtml(s.session_id)}</div>
        <div class="session-meta">
          <span>${s.call_count} call${s.call_count !== 1 ? 's' : ''}</span>
          <span>${ms(s.total_latency_ms)}</span>
          ${c ? `<span>${c}</span>` : ''}
          <span>${timeAgo(s.started_at)}</span>
        </div>
        ${s.agent_name ? `<div class="session-meta"><span>${escHtml(s.agent_name)}</span></div>` : ''}
      </div>
      `;
    }).join('');
  } catch(e) {
    if (!silent) el.innerHTML = '<div class="empty-state">Failed to load sessions.</div>';
  }
}

// ── Session detail ───────────────────────────────────────────────────────────

async function loadSession(sessionId, silent = false) {
  if (sessionId !== activeSessionId) {
    if (sessionRefreshTimer) { clearInterval(sessionRefreshTimer); sessionRefreshTimer = null; }
    activeSessionId = sessionId;
    document.querySelectorAll('.session-item').forEach(el => {
      el.classList.toggle('active', el.querySelector('.session-id').textContent === sessionId);
    });
    const body = document.getElementById('detail-body');
    body.innerHTML = '<div class="placeholder">Loading…</div>';
    document.getElementById('detail-header').innerHTML =
      `<span class="detail-session-id">${escHtml(sessionId)}</span>`;
    sessionRefreshTimer = setInterval(() => loadSession(activeSessionId, true), 5000);
  }

  const header = document.getElementById('detail-header');
  const body = document.getElementById('detail-body');

  try {
    const res = await fetch('/session/' + encodeURIComponent(sessionId));
    if (!res.ok) { body.innerHTML = '<div class="placeholder">Session not found.</div>'; return; }
    const calls = await res.json();

    const totalMs = calls.reduce((s, c) => s + (c.latency_ms || 0), 0);
    const totalIn = calls.reduce((s, c) => s + (c.tokens_in || 0), 0);
    const totalOut = calls.reduce((s, c) => s + (c.tokens_out || 0), 0);
    const totalCost = calls.reduce((s, c) => s + (c.cost_usd || 0), 0);
    const errorCount = calls.filter(c => (c.status_code || 200) !== 200).length;
    const c = cost(totalCost || null);

    header.innerHTML = `
      <span class="detail-session-id">${escHtml(sessionId)}</span>
      <div class="detail-stats">
        <span><strong>${calls.length}</strong> calls${errorCount ? ` <span style="color:#f87171">(${errorCount} error${errorCount>1?'s':''})</span>` : ''}</span>
        <span><strong>${ms(totalMs)}</strong> total</span>
        <span><strong>${totalIn}</strong> / <strong>${totalOut}</strong> tokens</span>
        ${c ? `<span><strong>${c}</strong></span>` : ''}
      </div>
      <div class="export-btn">
        <a class="export-link" href="/export/${encodeURIComponent(sessionId)}" download>↓ JSON</a>
        <a class="export-link" href="/export/${encodeURIComponent(sessionId)}/report" target="_blank">Report</a>
      </div>
    `;

    const scrollTop = silent ? body.scrollTop : 0;
    body.innerHTML = calls.map((call, i) => renderCall(call, i + 1)).join('');
    body.scrollTop = scrollTop;
  } catch(e) {
    if (!silent) body.innerHTML = '<div class="placeholder">Failed to load session.</div>';
  }
}

function renderCall(call, n) {
  const isError = (call.status_code || 200) !== 200;
  const stopClass = (call.stop_reason || '').replace('_', '-');
  const input = lastUserMessage(call.messages);
  const hasTools = call.tool_calls && call.tool_calls.length > 0;
  const callCost = cost(call.cost_usd);

  const metaItems = [
    call.agent_name ? `<div class="meta-item"><span class="meta-label">Agent</span><span class="meta-value">${escHtml(call.agent_name)}</span></div>` : '',
    call.user_id    ? `<div class="meta-item"><span class="meta-label">User</span><span class="meta-value">${escHtml(call.user_id)}</span></div>` : '',
    call.app_id     ? `<div class="meta-item"><span class="meta-label">App</span><span class="meta-value">${escHtml(call.app_id)}</span></div>` : '',
    call.environment && call.environment !== 'development' ? `<div class="meta-item"><span class="meta-label">Env</span><span class="meta-value">${escHtml(call.environment)}</span></div>` : '',
    call.temperature != null ? `<div class="meta-item"><span class="meta-label">Temp</span><span class="meta-value">${call.temperature}</span></div>` : '',
    call.max_tokens  != null ? `<div class="meta-item"><span class="meta-label">Max tokens</span><span class="meta-value">${call.max_tokens}</span></div>` : '',
  ].filter(Boolean).join('');

  const systemSection = call.system_prompt ? `
    <div class="section-label">System prompt</div>
    <div class="message-bubble system-prompt">${escHtml(call.system_prompt)}</div>
  ` : '';

  const inputSection = input ? `
    <div class="section-label">Input</div>
    <div class="message-bubble">${escHtml(input)}</div>
  ` : '';

  const toolResultsSection = (call.tool_results && call.tool_results.length > 0) ? `
    <div class="section-label">Tool results</div>
    ${call.tool_results.map(tr => `
      <div class="tool-result">
        <div class="tool-result-id">${escHtml(tr.tool_call_id || tr.tool_use_id || '?')}</div>
        <div class="tool-result-content">${escHtml(
          typeof tr.content === 'string' ? tr.content :
          tr.content ? JSON.stringify(tr.content, null, 2) : ''
        )}</div>
      </div>
    `).join('')}
  ` : '';

  const toolSection = hasTools ? `
    <div class="section-label">Tool calls</div>
    ${call.tool_calls.map(tc => `
      <div class="tool-call">
        <div class="tool-name">${escHtml(tc.name || '?')}</div>
        <div class="tool-args">${escHtml(formatArgs(tc.arguments))}</div>
      </div>
    `).join('')}
  ` : '';

  const outputSection = call.content ? `
    <div class="section-label">Output</div>
    <div class="message-bubble output">${escHtml(call.content)}</div>
  ` : '';

  const errorSection = isError ? `
    <div class="section-label error-label">Error — HTTP ${escHtml(call.status_code)}</div>
    <div class="message-bubble error-bubble">${escHtml(call.error_detail || 'No details captured.')}</div>
  ` : '';

  const parentSection = call.parent_action_id ? `
    <div class="parent-link">
      Triggered by <a onclick="scrollToAction('${escHtml(call.parent_action_id)}')">${shortId(call.parent_action_id)}</a>
    </div>
  ` : '';

  const handoffSection = (call.handoff_from || call.handoff_to) ? `
    <div class="handoff-badge">
      ${call.handoff_from ? escHtml(call.handoff_from) : ''}
      ${call.handoff_from && call.handoff_to ? '<span class="handoff-arrow">→</span>' : ''}
      ${call.handoff_to ? escHtml(call.handoff_to) : ''}
    </div>
  ` : '';

  return `
    <div class="call-card ${isError ? 'call-error' : ''}" id="call-${escHtml(call.action_id)}">
      <div class="call-card-header">
        <span class="call-number">${n}</span>
        <span class="call-model">${escHtml(call.model_id)}</span>
        <div class="call-badges">
          ${call.latency_ms != null ? `<span class="badge badge-latency">${ms(call.latency_ms)}</span>` : ''}
          ${(call.tokens_in != null && call.tokens_out != null) ? `<span class="badge badge-tokens">${call.tokens_in} / ${call.tokens_out}</span>` : ''}
          ${callCost ? `<span class="badge badge-cost">${callCost}</span>` : ''}
          ${isError ? `<span class="badge badge-error">HTTP ${escHtml(call.status_code)}</span>` : ''}
          ${!isError && call.stop_reason ? `<span class="badge badge-stop ${stopClass}">${escHtml(call.stop_reason)}</span>` : ''}
        </div>
      </div>
      <div class="call-card-body">
        ${metaItems ? `<div class="call-meta-row">${metaItems}</div>` : ''}
        ${handoffSection}
        ${systemSection}
        ${inputSection}
        ${toolResultsSection}
        ${toolSection}
        ${outputSection}
        ${errorSection}
        ${parentSection}
      </div>
    </div>
  `;
}

function scrollToAction(actionId) {
  const el = document.getElementById('call-' + actionId);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Init ─────────────────────────────────────────────────────────────────────

loadSessions();
setInterval(loadSessions, 10000);
connectWS();
</script>
</body>
</html>"""


def get_dashboard_html() -> str:
    return DASHBOARD_HTML
