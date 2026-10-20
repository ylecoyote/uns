> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# AGSignal Security Model

This document describes AGSignal's threat model, trust boundaries, mitigations,
and explicit non-goals. It is the engineering source-of-truth for what AGSignal
defends against and what it does **not**. It complements [`SECURITY.md`](../SECURITY.md)
(vulnerability reporting policy) and [`DEPLOYMENT.md`](DEPLOYMENT.md)
(operator hardening recipe).

> **Status: v0.1.0.** This is a living document. Threats marked **roadmap**
> are not mitigated in v0.1; track them in the issue tracker.

---

## Why an audit-product needs an explicit threat model

AGSignal's central claim is that the audit trail it produces — *who knew, when
they knew, and how the system responded* — is durable and trustworthy. That
claim only holds if the seams where signals enter, are acknowledged, and are
queried back are themselves trustworthy. The threats below are the ones that
could break that central claim. Mitigations are described in terms of what is
implemented in the codebase today, not aspirational.

---

## Trust boundaries

AGSignal recognizes the following actors. Each has a different trust posture
and a different blast radius if compromised.

| Actor | Trust | Capabilities | Compromise impact |
|---|---|---|---|
| **Operator** | privileged | Owns the AGSignal process(es), configures env vars, holds API keys, has DB credentials. | Total — operator can rewrite history. AGSignal does not defend against the operator. |
| **API client (write)** | semi-trusted | Authenticates with `AGSIGNAL_API_KEY` via `Authorization: Bearer …`. Posts notifications, acknowledges, dismisses. | Limited to the audit identity attributed to the configured `AGSIGNAL_API_PRINCIPAL`. Cannot impersonate other principals (unless `AGSIGNAL_ALLOW_PRINCIPAL_OVERRIDE=true`). |
| **API client (read)** | semi-trusted | Authenticates with the same key for read endpoints (`/ui/*`). | Read-only; can enumerate audit history within its access. |
| **LLM agent (via MCP)** | untrusted | Speaks JSON-RPC over stdio to the AGSignal MCP server in the host's process tree. | By default, can only call read tools. Can call write tools only if the operator has set `MCPRuntimeConfig.read_only=False`, `operator_principal`, and (for delivery) `delivery_confirmation_token`. The agent cannot mint these — they come from outside its context. |
| **End user / acknowledger** | variable | Receives a notification through Slack / PagerDuty / email / WebSocket; acknowledges through the Console UI or API. | Their acknowledgment is identity-resolved through the API key path (`acked_by` derived from authenticated principal). |
| **MIP host application** | variable | Runs AGSignal as embedded control-plane infrastructure; configures policies, adapters, and operator principals. | Same as operator. The host owns the runtime. |
| **Public network** | hostile | Anything reachable on the wire. | AGSignal is bound to `127.0.0.1` by default; the reverse proxy is the public attack surface. |

---

## Protected assets

Ordered by sensitivity:

1. **The audit trail** (delivery audits, ack audits, transition history).
   *Why it's the crown jewel:* the entire product proposition is that this
   record is true. Loss of integrity here is catastrophic.
2. **Audit identity** (`acked_by`, `dismissed_by`, principal claims). A forged
   `acked_by` is functionally a forged signature on a governance decision.
3. **Policy registry** (routing rules, mode overrides). Mutating policies
   silently lets an attacker re-route SAFETY signals to a sink.
4. **API keys and tokens** (`AGSIGNAL_API_KEY`, `delivery_confirmation_token`).
5. **Notification content** (potentially sensitive — agent reasoning, user
   identifiers, business state). Lower sensitivity than identity but still
   protected.
6. **Operator metadata** (which channels are configured, dedup TTLs, runtime
   topology). Disclosure facilitates targeted attacks but is not itself
   sensitive.

---

## Threat catalog

Each threat: identifier, severity, attacker capability, mitigation **as
implemented**, status. Severity is product-impact, not CVSS.

### T1 — Unauthenticated write endpoint
- **Severity:** Critical
- **Vector:** Anyone reachable on the AGSignal HTTP listener can POST to
  `/api/v1/notifications/{id}/ack`.
- **Mitigation:** All write routes (`/api/v1/notifications/*/ack`,
  `/api/v1/notifications/*/dismiss`) require `Depends(require_write_principal)`.
  Without `AGSIGNAL_API_KEY` configured, every write returns 503. With it
  configured, callers must supply `Authorization: Bearer <key>` (or
  `X-AGSignal-API-Key` / `X-UNS-API-Key` headers); HMAC-compared with timing
  safety. Source: `src/agsignal/api/auth.py`.
- **Status:** ✅ Mitigated.

### T2 — Audit identity forgery
- **Severity:** Critical
- **Vector:** Authenticated client sets `acked_by` to someone else's name,
  laundering an unwanted action through someone else's identity.
- **Mitigation:** `resolve_requested_actor()` rejects any `acked_by` /
  `dismissed_by` that does not match the authenticated `WritePrincipal.subject`,
  returning 403. The override is gated by an explicit
  `AGSIGNAL_ALLOW_PRINCIPAL_OVERRIDE=true` env, which is **off by default**.
- **Status:** ✅ Mitigated when `AGSIGNAL_ALLOW_PRINCIPAL_OVERRIDE=false`
  (the default).

### T3 — Self-acknowledging agent
- **Severity:** Critical
- **Vector:** An LLM agent sends itself an escalation through MCP, then
  acknowledges it itself, satisfying the policy contract without a human ever
  looking at the signal.
- **Mitigation:** `MCPRuntimeConfig.read_only=True` by default — write tools
  are not even registered. Even with `read_only=False`, write tools require:
  - `operator_principal` set in the runtime config (server-side, not callable
    from the LLM context),
  - `acked_by` to match the operator principal (caller-asserted values are
    rejected), and
  - For `send_signal` with `deliver=True`, an `operator_confirmation_token`
    that matches a pre-shared `delivery_confirmation_token` from the runtime
    config — the LLM cannot mint this.
  Source: `src/agsignal_mcp/runtime.py`, `src/agsignal_mcp/tools.py`.
- **Status:** ✅ Mitigated.

### T4 — CSRF on Console UI
- **Severity:** High
- **Vector:** A logged-in operator visits a malicious page that triggers a
  cross-origin request to ack a notification.
- **Mitigation:** `CORSMiddleware` is installed with a closed allowlist
  (`AGSIGNAL_ALLOWED_ORIGINS`, defaulting to dev-server origins). Methods are
  restricted to `GET, POST, OPTIONS`; `allow_credentials=False`. Combined with
  Bearer-token auth (which is not automatically attached by browsers cross-
  origin), CSRF surface is minimal. Source: `src/agsignal/api/auth.py:configure_cors`.
- **Status:** ✅ Mitigated.

### T5 — Replay attack
- **Severity:** High
- **Vector:** Attacker replays a signed notification request, causing duplicate
  side effects (double-ack, duplicate signal, duplicate channel delivery).
- **Mitigation:** Producer idempotency via `IdempotencyService` (Redis SETNX
  with TTL); deduplication engine with per-policy windows; `acked_at` and
  ack lifecycle prevent double-transitions through the engine's atomic
  serialization (`RLock` per notification id).
- **Status:** ✅ Mitigated for the producer path. Note: the in-process
  `RuntimeState.idempotency_records` and `app.state.http_idempotency_records`
  in-memory dicts are not concurrency-safe; they're acceptable for single-
  process deployments with sticky sessions but multi-process deployments
  should rely on Redis-backed idempotency.

### T6 — Audit tampering
- **Severity:** Critical (for a governance product)
- **Vector:** Attacker with write access to the audit table rewrites history
  to remove an unfavorable ack or insert a fabricated one.
- **Mitigation (partial):** Audit-before-commit on every state-changing
  endpoint — the audit row is persisted before the engine state mutates;
  audit failure surfaces as 503 and the state is not advanced. DB credentials
  for AGSignal should be scoped to INSERT/SELECT on audit tables only (no
  UPDATE/DELETE). Source: `src/agsignal/api/routes_notification.py`.
- **Status:** ⚠ Partially mitigated. **Roadmap:** tamper-evident audit
  chain (Merkle log or signed audit trail) is not implemented in v0.1. An
  attacker with direct DB write privileges can rewrite history — AGSignal
  defends against API-level tampering, not against operator-level compromise.

### T7 — DoS via unbounded queries
- **Severity:** High
- **Vector:** Attacker calls `/ui/audit` or `/ui/deliveries` with permissive
  filters and an inflated cursor, forcing the process to load and sort the
  full audit history in memory.
- **Mitigation:** All read queries push `LIMIT` and `ORDER BY` into SQL
  (`agsignal/api/read_models.py`); no in-memory full-table sort. Pagination
  cursor offset is capped and validated. Combined with auth (T1), only
  authenticated callers can issue these queries. **Plus** an API-level
  rate limiter (slowapi-backed; default 1000/minute per principal or IP)
  is installed on every HTTP route at app startup; runaway clients get
  429 with `Retry-After`. Operators can tighten via
  `AGSIGNAL_RATE_LIMIT_DEFAULT` or layer per-route limits at the reverse
  proxy. Source: `src/notification/rate_limiter.py`.
- **Status:** ✅ Mitigated.

### T8 — Information disclosure via interactive docs
- **Severity:** Medium
- **Vector:** Anonymous caller hits `/docs`, `/redoc`, or `/openapi.json`
  and enumerates the full API surface, payload schemas, and parameter names
  to plan an attack.
- **Mitigation:** All three endpoints are gated behind `AGSIGNAL_ENABLE_DOCS`,
  which defaults to **off**. `DEPLOYMENT.md` also recommends an explicit
  reverse-proxy block as defense in depth. Source: `src/agsignal/api/app.py`,
  `src/notification/main.py`.
- **Status:** ✅ Mitigated by default.

### T9 — Secret exposure via logs
- **Severity:** Medium
- **Vector:** Sensitive content (API keys passed accidentally as query params,
  PII in audit search filters, tokens in headers) ends up in process logs
  and propagates to log aggregation.
- **Mitigation (partial):** Structured logging with field allowlists for
  most paths. **Gap:** raw `request.query_params` is logged at INFO in
  `agsignal/api/observability.py`. Operator must configure log-aggregator
  redaction rules (denylist any field containing `token`, `key`, `secret`,
  `auth`) until the source-side fix lands.
- **Status:** ⚠ Partially mitigated. **Roadmap:** source-side query-string
  redaction.

### T10 — Dependency vulnerability
- **Severity:** Medium-High (varies by dep)
- **Vector:** A direct or transitive dependency has a CVE.
- **Mitigation:** `pip-audit` runs in the `lint` job on every PR; failing
  audit blocks merge. GitHub Dependabot alerts are enabled. `gitleaks` is
  configured to catch credential leaks before they reach the repo.
- **Status:** ✅ Mitigated.

### T11 — Supply-chain attack on PyPI artifact
- **Severity:** Critical
- **Vector:** A compromised maintainer credential (PyPI API token, GitHub
  access) publishes a malicious `agsignal` release.
- **Mitigation:** Releases use PyPI Trusted Publishing (OIDC) — no long-lived
  PyPI tokens exist. Sigstore attestations are generated automatically for
  every published artifact (verifiable provenance). Branch protection requires
  PR + CI green on `main`. The release workflow runs in a GitHub Environment,
  permitting manual approval gates. Source:
  `.github/workflows/release.yml`.
- **Status:** ✅ Mitigated.

### T12 — SSRF via channel adapters
- **Severity:** Medium
- **Vector:** A malicious notification crafted with a controlled URL causes
  an adapter to fetch internal resources.
- **Mitigation:** Channel adapter URLs (`AGSIGNAL_SLACK_WEBHOOK_URL`,
  `AGSIGNAL_PAGERDUTY_ROUTING_KEY`, SMTP host) are configured by the operator
  via env vars. Producers and the SDK do **not** accept caller-controlled
  URLs for delivery. Adapters route by `Channel` enum, not free-form URL.
- **Status:** ✅ Mitigated by design.

### T13 — SQL injection
- **Severity:** Critical
- **Vector:** Crafted input flows into a string-built SQL query.
- **Mitigation:** All persistence is through SQLAlchemy ORM with parameterized
  queries; no raw SQL with f-strings. Verified by code review. Source: the
  `db/` package (no `text()` calls with interpolated input).
- **Status:** ✅ Mitigated.

### T14 — Migration of legacy UNS/MIP users
- **Severity:** Low (operational hygiene)
- **Vector:** A user who lifts the v0.1 release into a UNS/MIP-shaped
  environment carries forward outdated patterns (e.g., the legacy `UNS_*`
  env vars are still honored).
- **Mitigation:** All `UNS_*` env vars work as compatibility aliases in v0.1.x.
  The `notification.*` import path remains as a legacy compatibility layer.
  These will emit `DeprecationWarning` in 0.2.x and be removed in 1.0.
- **Status:** Compatibility-shimmed; documented as legacy.

---

## Explicitly NOT mitigated

The following threats are **out of scope** for v0.1.x. AGSignal does not
attempt to defend against them; operators must address them at a different
layer.

- **Operator compromise.** If the operator account or `AGSIGNAL_API_KEY` is
  stolen, the attacker has the operator's audit identity. Rotate the key
  promptly. Single-key rotation is not yet online (planned for 0.2.x).
- **Database compromise.** Audit history is not yet tamper-evident (T6).
  Direct DB write access can rewrite the audit. Restrict DB credentials at
  the platform level.
- **Network-layer attacks** (TLS interception, DNS hijacking, BGP). The
  reverse proxy terminates TLS; AGSignal trusts what arrives over the
  loopback interface.
- **Side channels** (timing, cache, branch prediction). Out of scope for v0.1.
- **Insider attacks on the LLM context.** If an attacker can inject prompts
  into the LLM that controls AGSignal MCP, they can attempt the agent
  attacks AGSignal does defend against (T3) — but defense against prompt
  injection itself is the host application's responsibility.
- **Multi-tenant isolation in a single process.** AGSignal is single-tenant
  per process. Run separate processes for separate customers/teams. See
  `DEPLOYMENT.md`.

---

## Operator assumptions

The mitigations above assume:

- A **reverse proxy terminates TLS** in front of AGSignal. AGSignal binds
  to `127.0.0.1` by default and does not speak TLS itself.
- The **database** uses access-controlled credentials scoped to the AGSignal
  application (no superuser).
- **Redis** is on a private network with `requirepass` set.
- **Logs** are shipped to a tamper-evident or write-once aggregator.
- **Operator credentials** (`AGSIGNAL_API_KEY`, DB password, Redis password)
  are managed by a secrets manager — not committed to git, not in shell
  history, not in environment dumps.
- **CI** runs `pip-audit`, `bandit`, and `gitleaks` on every PR.

If your deployment doesn't meet these assumptions, model your residual risk
accordingly.

---

## Roadmap (security work not yet shipped)

Tracked in the public issue tracker. Operators evaluating AGSignal for
high-stakes deployments should weigh these gaps:

- **Tamper-evident audit chain** — Merkle log or signed audit (gap from T6)
- **Online API key rotation** — multi-key support so rotation is online
  (gap noted under "Operator compromise")
- **Source-side query-string redaction** in `observability.py` (gap from T9)
- **Database migrations** via Alembic, removing the operator-driven SQL
  bootstrap step (operational hardening)
- **Per-route audit log redaction** for sensitive notification content

---

## Reporting and feedback

If you identify a threat not covered here — or believe a stated mitigation
does not work as described — file a private vulnerability report through
GitHub per [`SECURITY.md`](../SECURITY.md). For lower-severity threat-model
gaps (omissions, clarifications, suggestions), open a regular issue.

This document is updated whenever a new mitigation lands or a new threat
becomes mitigated. Diffs to this file should accompany the corresponding
code change in the same PR.
