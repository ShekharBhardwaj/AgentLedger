# AgentLedger — Claude Code Context

## What this project is
AgentLedger is a runtime observability and debugging tool for AI agents.
It instruments LLM calls transparently — without requiring developers to
change their agent code — and reconstructs full decision chains for
debugging, auditing, and compliance.

Primary market: fintech and regulated industries that need audit trails
for agent actions.

## Core architectural decision
AgentLedger works as a **proxy layer** that intercepts LLM HTTP traffic
at the network level. It does NOT wrap specific SDKs, frameworks, or
model providers.

This means:
- Works with any agent framework (OpenAI Agents SDK, custom loops, etc.)
- Works with any model (Claude, GPT, Gemini, local models)
- Works with any model gateway (LiteLLM, OpenRouter, direct provider)
- Zero code change required from the developer using it

Do NOT suggest SDK-specific or provider-specific instrumentation.
The proxy pattern is intentional and non-negotiable.

## The key primitive
`explain(action_id)` — reconstructs the full decision chain for any
agent action. Given an action ID, it returns:
- The prompt that triggered the action
- All tool calls made
- The model's reasoning at each step
- The final output

## Tech stack
- Language: Python
- API layer: FastAPI
- Proxy: intercepts LLM HTTP traffic at network level
- Tool layer: MCP (model and framework agnostic)
- Session memory: Redis
- Storage: Postgres
- Wire format: normalize all provider formats internally to a 
  canonical AgentLedger schema — do not assume any single 
  provider's format as the standard

## What "agnostic" means here
AgentLedger must work regardless of:
- Which agent framework the developer uses
- Which LLM provider they use
- Which model gateway they use
- Whether they use MCP or raw tool calling

Instrumentation happens at the HTTP/network level.
Internal normalization maps any provider format → canonical schema.
No layer of the codebase should assume a specific provider's API shape.

## Canonical internal schema
When storing or processing an LLM interaction, normalize to:
- request: { messages, tools, model_id, provider, timestamp }
- response: { content, tool_calls, stop_reason, tokens, latency }
- action_id: uuid assigned at interception time

Never store provider-native formats as the source of truth.

## Current state
- MVP codebase built
- Install via git (PyPI publish pending)
- MIT license, public GitHub repo
- Initial testing underway

## Code style preferences
- Async everywhere (asyncio)
- Type hints on all functions
- Keep abstractions thin — no unnecessary classes
- Tests alongside implementation, not in a separate tree
- Prefer explicit over magic

## Do not suggest
- LangChain or LangGraph integrations
- Framework-specific hooks as the primary instrumentation path
- Provider-specific SDK wrapping as the instrumentation strategy
- Any assumption that a specific provider's wire format is standard
- Kubernetes or complex infra (solo founder project, keep it lean)
- Separate vector DB (use pgvector if needed)

## Project constraints
- Solo founder, move fast
- Minimize dependencies
- Must run on a single VPS to start
- Prefer boring, well-understood technology
- Every abstraction must earn its place