> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# MCP Transport

Date: 2026-05-08

Status: Accepted

Linear: TBD

## Context

PRD M7 locks the three governance MCP tools (`check_policy` READ-only, `request_approval`
WRITE-durable, `log_decision_reasoning` WRITE-LOG) but defers transport selection to this
ADR (M7.4, §11 ADR-006). AGSignal v1 is pre-execution-first (PRD §1.2.4); the MCP surface
is how agent runtimes consult it before side-effecting actions. AGSignal core is async
FastAPI + Pydantic v2 (PRD §9.5; HARD-04) — an HTTP-shaped transport composes cleanly.

The MCP ecosystem consolidated since the PRD landed. The 2025-03-26 spec **deprecated
HTTP+SSE** in favor of Streamable HTTP (single endpoint, no sticky-session requirement).
The 2025-06-18 spec made **OAuth 2.1 + PKCE + Resource Indicators (RFC 8707)** mandatory
for HTTP transports. The 2025-11-25 spec made Protected Resource Metadata (RFC 9728)
discovery a MUST and added Client ID Metadata Documents (CIMD) as the recommended
registration mechanism. SSE removal deadlines from major operators (Atlassian, Keboola)
land in mid-2026. Picking SSE for v1 in May 2026 would be shipping a deprecated transport.

## Decision

### 1. Default transport for v1: Streamable HTTP

Production deployments expose the three MCP tools over **Streamable HTTP only**. This is
the current MCP-spec production transport (since 2025-03-26), supports stateless
horizontal scaling, and integrates with standard HTTP load balancers / auth middleware.
SSE is rejected because the spec deprecated it; stdio is rejected as production because
it requires a client-launches-subprocess topology and precludes remote agent access.

### 2. Multi-transport: stdio (local dev) + Streamable HTTP (production)

v1 ships **two transports** with disjoint use cases. **stdio** is a developer-experience
and single-process-embedding convenience (MCP-spec semantics: client launches AGSignal
as a subprocess; OS process boundary is the trust boundary). **Streamable HTTP** is the
only supported production transport. Operators choose at startup via
`AGSIGNAL_MCP_TRANSPORT=stdio|http` (default `http`). All three tools work identically
across both transports — the tool contract (ADR-004) is transport-agnostic. No tool is
transport-restricted.

### 3. Auth model per transport

- **stdio**: implicit OS-process trust; no MCP-protocol-level auth. Approver-identity
  resolution still flows through the configured `IdentityProvider` (ADR-004 §1) when
  `request_approval` is invoked, preserving the ADR-005 trust posture at the tool layer.
- **Streamable HTTP**: **OAuth 2.1 + PKCE + Resource Indicators (RFC 8707)** per current
  MCP spec. AGSignal acts as an OAuth 2.1 Resource Server — validates bearer tokens,
  never issues them. Operators bring their own authorization server (Auth0, Okta, Azure
  AD, Keycloak, or self-hosted). A fallback **static bearer token** mode
  (`AGSIGNAL_MCP_AUTH=bearer-static`) is documented as the weakest option, intended for
  closed-network deployments only. mTLS is supported as an additive layer underneath
  OAuth 2.1 (defense-in-depth) but is not required by default.

A deployment is either local-dev stdio or production HTTP; mixing the two on one process
is not supported.

### 4. TLS requirements

- **stdio**: N/A (no network surface).
- **Streamable HTTP**: **TLS required by default**. AGSignal refuses to bind a plaintext
  listener unless `AGSIGNAL_MCP_TLS=disabled` is set explicitly (dev-only opt-out, e.g.,
  for local TLS-terminating proxy setups). The MCP spec mandates HTTPS for OAuth 2.1
  endpoints; this default matches. Cert provisioning is the operator's responsibility
  (typical: TLS termination at the ingress / sidecar).

### 5. Connection limits and rate limiting

Per-tool rate limits reflect M7 semantic separation:

- **`check_policy`** (READ-only): `1000 req/min/client`, token-bucket. High-volume
  preflight is the canonical use case.
- **`request_approval`** (WRITE-durable): `60 req/min/client`. Each call writes a
  Decision Audit entry (M6.1) and may emit notifications; abuse is more costly.
- **`log_decision_reasoning`** (WRITE-LOG): `300 req/min/client`. PRD M7.3's 64 KB
  per-call content cap bounds total ingest.

Connection cap: `100` concurrent Streamable-HTTP connections per authenticated identity
(configurable). stdio has no connection cap. Enforcement uses the existing token-bucket
rate limiter (M1.6). Limit breaches return a JSON-RPC error with MCP-standard error code;
tool-call results are never silently dropped.

### 6. Discovery

- **Streamable HTTP**: **`AGSIGNAL_MCP_URL` environment variable** is the v1 contract
  (e.g., `https://agsignal.example/mcp`). AGSignal exposes the **MCP-spec-mandated
  Protected Resource Metadata (RFC 9728)** at `/.well-known/oauth-protected-resource`
  for client auto-discovery of authorization server, scopes, and resource identifier.
  No AGSignal-specific `.well-known/mcp` manifest is added — the spec-standard PRM
  document is the contract.
- **stdio**: caller-provided launch command + args (standard MCP stdio config).

### 7. Tool authorization scope

All three tools share the OAuth 2.1 resource indicator `agsignal-mcp` but declare
distinct scopes for least-privilege tokens:

- `agsignal:policy:read` — `check_policy` only
- `agsignal:approval:write` — `request_approval` only (implies `:read`)
- `agsignal:audit:write` — `log_decision_reasoning` only

A read-only dashboard preflighting decisions gets `agsignal:policy:read`; a full agent
runtime gets all three. The 2025-11-25 spec's Step-Up Authorization flow is supported:
invoking `request_approval` with only `agsignal:policy:read` returns 403 + a
`WWW-Authenticate` challenge naming the missing scope. stdio bypasses scoping (no token
concept); the launching process has implicit access to all tools.

### 8. MCP spec version compatibility

v1.0 targets the **2025-11-25 MCP protocol revision** as canonical. AGSignal advertises
supported revisions in `InitializeResult` per spec; v1.0 declares `2025-11-25` and
accepts initialization from `2025-06-18` for backward compatibility (auth shape is
identical between the two). The 2024-11-05 HTTP+SSE transport is **not supported** —
clients pinned to that revision must update their SDK.

Forward-compat: AGSignal pins MCP-spec compatibility per minor release. Optional-feature
revisions absorb in a minor release; breaking revisions trigger a parallel-version
window (n and n-1 supported simultaneously) for one minor release. The MCP team's
2026-roadmap commitment to "no new transports this cycle, evolve the existing transport"
makes this manageable at v1.0 scope.

## Rejected

- **stdio as the v1 production default.** Local-dev / single-process-embedding transport
  only; precludes remote agent integration (the primary v1 use case). Kept as dev-loop
  convenience.
- **SSE (HTTP+SSE) as a v1 transport.** Deprecated by the MCP 2025-03-26 spec; major
  operators (Atlassian Rovo, Keboola) published mid-2026 removal deadlines. Picking it
  now ships a known-deprecated transport.
- **Multi-transport beyond stdio + Streamable HTTP** (e.g., shipping legacy SSE for
  back-compat). SSE back-compat is the spec's client-side responsibility, not the
  server's; hosting extra endpoints doubles auth/rate-limit surface for marginal gain.
- **No rate limiting / unified single rate.** `check_policy` is high-volume preflight
  while `request_approval` is durable-write expensive; a single rate either starves
  preflight or under-protects approvals.
- **TLS optional by default.** Default-off TLS makes the insecure path the easy path;
  operators opt out explicitly so the easy path stays secure. Aligned with the MCP-spec
  HTTPS mandate for OAuth 2.1 endpoints.
- **AGSignal-specific `.well-known/mcp` manifest.** The MCP spec already standardizes
  PRM at `/.well-known/oauth-protected-resource` (RFC 9728); a second AGSignal-shaped
  manifest fragments discovery.

## Consequences

**Operator deployment topology.** Production runs AGSignal behind a TLS-terminating
ingress and exposes `/mcp` as the single MCP endpoint. The OAuth authorization server
is operator-supplied; AGSignal documents reference configurations for Auth0, Okta,
Azure AD, and self-hosted Keycloak. Local-dev uses `AGSIGNAL_MCP_TRANSPORT=stdio` and
skips auth-server bring-up. Per-tool rate limits and scope tiers (§5, §7) give
operators least-privilege levers without per-client custom code.

**Agent-client integration.** Clients configure `AGSIGNAL_MCP_URL` plus an OAuth client
(CIMD-published metadata preferred per current spec; DCR acceptable as fallback). The
three tool calls and their async-at-the-boundary contracts (ADR-004) work identically
in stdio and Streamable HTTP — agent code developed against stdio in CI deploys
unchanged against production HTTP. Step-up authorization (§7) lets read-only callers
escalate write scopes on demand instead of carrying write tokens by default.

**v1.x MCP-spec-bump migration story.** The MCP 2026 roadmap defers new transports —
evolution stays within Streamable HTTP. v1.x absorbs minor revisions in minor releases;
major revisions get a one-release parallel-version window per §8. This ADR is amended
(or superseded) only if the spec adds a new transport or removes Streamable HTTP.
Plugin-side identity extension (ADR-004 `IdentityProvider`, ADR-005 trust) is unaffected
by transport choice — MCP-layer auth composes with, but does not replace, approver-
identity resolution at the tool-call layer.

## References

- [MCP Specification 2025-11-25 — Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) — current-spec transport definitions; basis for the stdio + Streamable HTTP choice in §2
- [MCP Specification — Authorization (draft / 2025-11-25)](https://modelcontextprotocol.io/specification/draft/basic/authorization) — OAuth 2.1 + PKCE + RFC 8707 mandate underpinning §3 and §7
- [Why MCP Deprecated SSE and Went with Streamable HTTP](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/) — rationale for the SSE-rejection in the Rejected section
- [MCP's Remote Revolution: Streamable HTTP, OAuth, and the Path to 18,000 Servers](https://zylos.ai/research/2026-03-08-mcp-remote-evolution-streamable-http-enterprise-adoption) — production-deployment patterns for Streamable HTTP that inform §1, §4
- [What's New In The 2025-11-25 MCP Authorization Spec](https://den.dev/blog/mcp-november-authorization-spec/) — CIMD / step-up authorization / PRM discovery details that shape §6 and §7
- [MCP Server OAuth Authentication Guide (2026)](https://mcpplaygroundonline.com/blog/mcp-server-oauth-authentication-guide) — bearer-token challenge flow and WWW-Authenticate semantics referenced in §7
- [HTTP+SSE Deprecation Notice — Atlassian Rovo](https://community.atlassian.com/forums/Atlassian-Remote-MCP-Server/HTTP-SSE-Deprecation-Notice/ba-p/3205484) — concrete mid-2026 SSE removal deadline cited in §8 / Rejected
- [The 2026 MCP Roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) — "no new transports this cycle" commitment underpinning the v1.x forward-compat plan in §8
- ADR-004 (Plugin Extension API Surface) — `2026-05-08-extension-api-surface.md`; tool-contract async-at-the-boundary commitment that this ADR's transports carry
- ADR-005 (Plugin Trust Model) — `2026-05-08-plugin-trust-model.md`; relevant for `IdentityProvider` resolution at the tool-call layer (§3)
- PRD §1.2.4, M7, M7.4, §11 ADR-006 (`agent_governance_control_plane_prd.md`) — pre-execution-first positioning + transport-pending requirement closed by this ADR
- Stage 2 production-pattern matrix (`docs/internal/superpowers/specs/2026-05-08-stage2-production-pattern-matrix.md`) — emerging MCP governance practice referenced in PRD M7
