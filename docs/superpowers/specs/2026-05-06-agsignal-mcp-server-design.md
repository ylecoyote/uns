# AGSignal MCP Server Design

Date: 2026-05-06

Status: Implemented for stdio v1

## Goal

Add an AGSignal-specific Model Context Protocol server so agent clients can
inspect and operate the AGSignal governance control plane without importing MIP
domain behavior.

The first implementation should expose the same control-plane concepts shown in
the product narrative: signal emission, policy preview, delivery status, ACK
state, audit history, invariants, DLQ visibility, and runtime health.

## Decision

Implement Option B for v1: a stdio MCP transport backed by a reusable MCP server
factory.

Design the module boundary so HTTP/SSE transport can be added later without
rewriting the tool registry, but do not ship HTTP/SSE in the first slice.

## Context

AGSignal already has the runtime surfaces the MCP tools should wrap:

- standalone send and simulate routes in `notification.routes`;
- delivery status, DLQ, channel health, and policy reload routes in
  `notification.routes`;
- ACK, dismiss, notification status, and ACK status routes in
  `mcp_server.routes_notification`;
- delivery, audit, effective-policy, and invariant read models in
  `mcp_server.routes_ui`;
- liveness/readiness and websocket agent delivery in `notification.main`.

The MIP donor repo has a real stdio MCP pattern using `FastMCP`, but its tools
are MIP-specific market-analysis tools. AGSignal should reuse the shape of that
entrypoint, not the MIP tool set.

## Non-Goals

- Do not port MIP stock, market-regime, ATP, or trading-service behavior.
- Do not replace AGSignal's HTTP API, console read models, or websocket agent
  delivery.
- Do not expose policy writes, policy reload, DLQ deletion, or broad admin
  mutation in v1.
- Do not claim hosted/network MCP support until HTTP/SSE is implemented and
  secured.

## Module Boundary

Use a shared factory and a thin transport wrapper:

- `agsignal_mcp.tools`: tool functions and request/response shaping.
- `agsignal_mcp.factory`: `create_mcp_server(runtime_config)` registers the v1
  tool set once.
- `agsignal_mcp.transports.stdio`: local stdio entrypoint that calls the factory
  and runs the server.

Keep domain behavior in existing `notification.*`, `agsignal.*`, and
`mcp_server.*` services. MCP code should adapt inputs and outputs; it should not
reimplement delivery, policy, ACK, audit, or read-model logic.

## V1 Tool Set

### Send and Preview

- `simulate_signal`: dry-run policy/routing preview with no delivery, replay,
  ACK, or audit side effects.
- `send_signal`: defaults to `deliver=false`, returning a routing and policy
  preview. Real delivery requires `deliver=true` plus an explicit confirmation
  field such as `operator_intent="deliver"`.

When `send_signal(deliver=true)` is confirmed, it should use the same runtime
path as normal AGSignal sends, including delivery, ACK registration, audit,
idempotency, deduplication, DLQ, and adapter side effects.

### Status and Audit

- `get_delivery_status`
- `get_notification_status`
- `get_ack_status`
- `ack_notification`
- `dismiss_notification`
- `list_deliveries`
- `get_delivery_timeline`
- `list_audit_events`

ACK and dismiss are explicit write operations and should be auditable.

### Policy and Runtime Inspection

- `get_effective_policy`
- `list_invariants`
- `get_invariants_summary`
- `list_dlq`
- `get_channel_health`
- `health`
- `ready`

Policy reload and DLQ deletion are intentionally excluded from v1. They can be
introduced later as an ops-admin capability tier.

## Runtime Modes

- `stdio-local`: default local process mode. Uses in-memory stores unless
  persistence is configured.
- `stdio-persistent`: local stdio mode backed by `DATABASE_URL` or equivalent
  configured persistence.
- `read-only`: disables send, ACK, and dismiss tools while preserving
  inspection tools.

The MCP server should report which mode is active in `ready` output so agent
clients understand whether results are ephemeral or persisted.

## Safety Rules

- `simulate_signal` must never perform delivery, ACK registration, DLQ writes,
  replay, or adapter side effects.
- `send_signal` must be non-delivering by default.
- `send_signal(deliver=true)` must require explicit confirmation.
- Mutating tools must include request IDs or correlation IDs where supported by
  the underlying runtime.
- Tool responses should preserve policy, delivery, and audit identifiers needed
  for follow-up inspection.

## Option C: stdio + HTTP/SSE

Option C adds HTTP/SSE transport in the first release while keeping the same
shared MCP server factory.

Additional modules would be:

- `agsignal_mcp.transports.http`: ASGI or FastMCP HTTP/SSE entrypoint.
- transport/session middleware for auth, CORS/origin policy, payload limits,
  request IDs, connection limits, and readiness checks.

This is worthwhile when AGSignal has a named hosted MCP consumer, multiple
remote clients, durable streaming sessions, or agent integrations that cannot
spawn a stdio process.

It is not the right v1 default because HTTP/SSE introduces network auth,
session lifecycle, deployment, rate limiting, origin policy, and operational
support before local MCP demand is proven. If added later, it should reuse
`create_mcp_server(runtime_config)` and the same tool contracts rather than
forking behavior by transport.

## Testing Strategy

- Contract-test `create_mcp_server()` so the tool registry is stable.
- Unit-test tool functions with fake adapters/stores and no real channel
  delivery.
- Add parity tests against existing HTTP route behavior for simulate, send,
  ACK, dismiss, delivery status, read models, policies, invariants, DLQ, and
  health.
- Add a stdio smoke test that starts the entrypoint and verifies tool discovery.
- Defer HTTP/SSE auth and session tests until Option C is selected for
  implementation.

## Acceptance Criteria

- AGSignal exposes a stdio MCP entrypoint with AGSignal-specific tools.
- The tool registry is created through a reusable factory.
- V1 tools map to existing AGSignal runtime/read-model behavior without
  duplicating business logic.
- Real delivery is opt-in and explicitly confirmed.
- Admin mutations remain out of v1.
- Documentation clearly states that HTTP/SSE is a deferred transport option.
