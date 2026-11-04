# UNS security and functionality audit

UNS at `e9b1f11e2ba539276ae36f6af09d30d34273fe83` contains **15 actionable findings: 9 P1 and 6 P2**. Thirteen findings have executable reproductions; two document integration and documentation gaps established by source inspection and the documentation build. No P0 issue was demonstrated. The principal release risks are incomplete tenant isolation, approval identity reuse, activation of the wrong policy candidate, provider incident collisions, and unauthenticated metric allocation.

This audit applies Multi-Perspective Deep Dive v2.5 through three analytical lenses: Larrynator examines invariants and state transitions, Curlytron examines exploit chains and opportunities to simplify boundaries, and Moebot examines operational failure and counterevidence. These are analytical roles within one review, not independent external reviewers. Findings are review results and proposed remediation. No application fixes, deployments, provider messages, or public issue postings were performed.

## Scope and verification

The tracked inventory contains 603 files, including 96 source Python modules, 52 console TypeScript/TSX modules, 109 Python test files, 19 console test files, and 116 documentation Markdown files. The 55 Markdown files under `docs/archive/` were classified as historical material, rather than treated as current functionality promises. Source review concentrated on transport authorization, intake and immutable policy resolution, lease-fenced delivery, provider callbacks, governance approvals, policy evolution, persistence/retention, console contracts, packaging, and CI/deployment configuration. Inventory and automated analysis cover the repository broadly; manual inspection was risk-directed and does not assert line-by-line proof of every file.

| Check | Observed result |
| :--- | :--- |
| Existing Python suite, Python 3.12.9 | 1,908 passed, 6 PostgreSQL-dependent cases skipped; 51.02 seconds |
| Existing PostgreSQL 16 acceptance/load module, disposable container | 14 passed; 6.40 seconds. This separate run includes the PostgreSQL variants and SQLite checks. Counts are not added to the full-suite count. |
| New adversarial probes | 42 passed across SQLite and PostgreSQL; 6.51 seconds. Passing means the described defects were reproduced. |
| Console CI command | Type-check, lint, 346 tests across 19 files, and production build passed |
| Ruff | Passed for `src tests scripts apps`; audit harness separately linted and formatted |
| mypy | Passed across 96 source files |
| Bandit | Exit 0; no findings |
| UI boundary check | Passed |
| Strict MkDocs build | Exit 0, with 39 link diagnostics at INFO severity; see F15 |
| Installed-environment `pip-audit` | No known vulnerabilities reported |
| Full `npm audit`, including development dependencies | Zero advisories reported |
| Gitleaks with repository configuration | 515 commits scanned; no leaks reported |

The audit PostgreSQL containers used synthetic credentials and loopback-only published ports, and were stopped and removed. The existing localhost recording deployment and its database were not tested or modified. Hosted CI, other Python versions, container rebuilds, registry publication, real Slack/PagerDuty receipt, and production traffic were not established by these local results. Dependencies and secrets were assessed with the named tool configurations and current responses, not certified permanently safe.

The standard tests regenerated only the timestamp in `docs/ui/contracts/ui-contracts.json`; that audit-created change was restored. The only repository additions are this audit's artifacts.

## Findings and evidence

### F01 P1 Scoped credentials disclose records outside their bounds

**Failure:** A tenant A observer gets `403` on tenant B's canonical notification status endpoint, but can read that same notification through runtime inspection, delivery audit, or the audit collection. A source-restricted observer can also read a different source through console delivery lists and details when the namespace matches. Configured MCP bounds do not reach several registered read tools.

**Evidence:** `src/uns/routes.py:32` reads `source` and `notification_type` from the work row's top level, although both are under `row['notification']` (`src/uns/runtime.py:259`). Missing values cause `require_source_and_namespace` to skip those checks (`src/uns/api/auth.py:267`). `src/notification/routes.py:238` and `:279`, `src/uns/routes.py:39`, and `src/uns/api/routes_ui.py:699` have no record-level bounds. Console delivery filtering checks only namespace at `src/uns/api/routes_ui.py:213` and `:274`. MCP status/audit/DLQ helpers at `src/uns_mcp/tools.py:306`, `:334`, `:362`, `:394`, and `:507` lack a config argument; registered wrappers omit it at `src/uns_mcp/factory.py:117` and `:132`. MCP collection filtering at `src/uns_mcp/tools.py:497` ignores source.

**Contract:** `docs/SECURITY-MODEL.md:18` and `docs/ROADMAP.md:17` advertise source/namespace bounds across transports. `docs/API.md:134` still describes instance-wide observer reads, creating a conflicting older contract. The configurable bounds and canonical endpoint's denial provide the concrete expected behavior for this finding.

**Proof:** `test_scoped_http_reads_disclose_other_namespace`, `test_ui_reads_ignore_source_bounds`, and `test_registered_mcp_reads_ignore_configured_bounds` reproduce nine bypass cases per backend. DLQ and MCP source-list variants are additionally identified by source inspection. This is authenticated cross-scope disclosure, not an unauthenticated database read. MCP remains a trusted local stdio transport, but a host configuring bounds does not receive consistent restriction.

**Remediation:** Pass one verified access context to every record query and apply source plus namespace constraints before pagination, counts, and serialization. Read bounds from the actual notification envelope. Include DLQ, audit, runtime inspection, owner links, and all registered MCP helpers in the denial matrix.

### F02 P1 Governance approval identity omits tenant and action resource

**Failure:** Two decisions with identical policy, context, subject, and omitted correlation ID receive the same `decision_id` even when tenant and resource differ. Once the first obligation is approved, requesting approval for the second returns the first tenant's already approved request and notification.

**Evidence:** `_deterministic_decision_id` at `src/uns/governance/decision_engine.py:115` hashes only policy hash, context hash, subject, correlation ID, and parent decision ID. `decide()` accepts tenant/resource fields separately at `:160`. `GovernanceApprovalBridge.request_approval` returns a cached or recovered request solely by decision ID at `src/uns/governance/approval_workflow.py:178`; its durable intake key also uses that ID at `:206`.

**Proof:** `test_approval_identity_reused_across_tenant_and_resource` dispatches and approves a real synthetic obligation, then changes `tenant_id` and `resource_id`. Both SQLite and PostgreSQL return the original approved request. The gate itself still reports `REQUIRE_APPROVAL`; the flaw is in the approval object a host may consume to resume the second action. Hosts already supplying unique action identities in context/correlation reduce this exposure, but the public API does not require that invariant.

**Remediation:** Bind approval identity to a trusted action-instance identifier, tenant, resource type/ID, subject, policy hash, and context hash using canonical structured serialization. Require the action-instance identifier for approval-backed execution, and reject reuse of an explicit decision ID with different bound content. Keep retries of one action idempotent while requiring independent actions to receive independent approval.

### F03 P1 Activating an approved proposal can activate another proposal's draft

**Failure:** Approve candidate A, which changes ACK timeout from 10 to 20, then approve candidate B, which changes deduplication from 60 to 120. Activating A installs B's draft with timeout still 10, while A's audit state becomes `APPLIED`.

**Evidence:** `ShadowPolicyEvaluator.activate_draft` chooses the latest DRAFT by notification type at `src/uns/shadow_evaluator.py:908`. It does not bind the chosen revision to the requested delta's approved content. It saves that policy at `:949` and marks the requested delta APPLIED at `:967`. The retained `source_delta_id` in `PolicyConfigEnvelope` (`src/notification/policy_config.py:56`) is not used as an exact activation binding.

**Proof:** `test_activate_older_delta_activates_different_approved_candidate` reproduces the wrong configuration and false APPLIED provenance on both databases.

**Remediation:** Store the exact materialized draft revision ID and approved semantic content hash on the proposal's durable evidence binding. Activation must load that revision, compare reconstructed candidate content, and commit the exact activation plus delta transition together. A superseded draft should conflict or be explicitly rematerialized from its own approved content, never be substituted by the latest draft of the same type.

### F04 P1 PagerDuty incident keys discard intake isolation

**Failure:** Separate principals/sources with the same producer `dedup_key` have distinct durable obligations but the same PagerDuty incident key. A correctly signed callback containing that incident key resolves the latest matching event, and can acknowledge the other tenant's obligation.

**Evidence:** Intake scopes deduplication by principal, source, raw key, and effective obligation hash at `src/uns/runtime.py:369`. `PagerDutyAdapter._get_dedup_key` emits only `uns-{notification.dedup_key}` at `src/notification/adapters/pagerduty.py:521`. `Runtime.resolve_pagerduty_target` searches matching events newest first at `src/uns/runtime.py:984`. Outbound ACK/resolve reconstructs the same raw key at `:1038`.

**Proof:** `test_pagerduty_provider_key_collides_across_isolated_intake` proves the key collision. `test_signed_pagerduty_callback_settles_wrong_tenant_on_key_collision` uses the actual adapter with a synthetic local provider method and a valid HMAC to show the callback settles the second tenant's record while the first remains PENDING. This does not break HMAC verification; the authenticated event is correlated ambiguously.

**Remediation:** Allocate an immutable provider correlation key for each canonical obligation/generation, persist the association, and use it for trigger, ACK, resolve, and webhook lookup. Index the association directly. Do not reverse-match globally by a producer-controlled raw key or by a bounded newest-500 scan. Define migration behavior for existing incidents rather than changing their keys silently.

### F05 P1 Anonymous unknown URLs allocate unbounded metrics

**Failure:** Each unique anonymous request to a nonexistent URL creates a new persistent Counter child and Histogram child in process memory. Repetition can exhaust memory and inflate Prometheus scrape cost without a valid credential.

**Evidence:** `_resolve_path_template` falls back to the raw URL path at `src/notification/metrics.py:99`; `PrometheusMiddleware` allocates labeled children at `:132` and `:137`. The UI collector separately keys dictionaries by normalized URL at `src/uns/api/observability.py:134`, with normalization limited to UUID substitution at `:474`.

**Proof:** `test_anonymous_unknown_paths_allocate_permanent_metric_series` sends 20 local anonymous 404 requests and observes 20 distinct Counter and 20 Histogram children. It establishes unbounded allocation by attacker-selected paths, not a measured production OOM threshold. A per-minute limit would not bound lifetime cardinality.

**Remediation:** Label unmatched requests with one constant such as `__unmatched__`; use route templates for matched requests and a bounded HTTP method vocabulary. Apply the same route normalization to the console collector. Verify thousands of unique 404 URLs leave the number of metric children constant.

### F06 P1 Producer flag bypasses the admin SHADOW promotion endpoint

**Failure:** A producer receives `403` from `POST /api/v1/policies/proposals/{id}/shadow`, but can create a proposal directly in SHADOW and persist PREVIEW policy state by setting `promote_to_shadow: true` on proposal creation.

**Evidence:** Creation requires only producer scope at `src/notification/routes.py:460` and forwards the flag at `:479`. `ShadowPolicyEvaluator.propose_delta` calls `promote_to_shadow` directly at `src/uns/shadow_evaluator.py:738`. The separate shadow endpoint requires admin at `src/notification/routes.py:494`.

**Proof:** `test_producer_can_bypass_admin_shadow_promotion_endpoint` reproduces the asymmetric authorization and resulting PREVIEW row on both databases. This grants SHADOW/PREVIEW mutation and can retire the incumbent preview through normal policy-store behavior; it does not directly grant ACTIVE policy activation.

**Remediation:** Keep ordinary producer creation in PROPOSED. When the convenience flag is present, require the same admin authority as the dedicated endpoint before invoking the evaluator. Alternatively remove the convenience flag from producer input.

### F07 P1 Warm workers can permanently miss shadow candidates created elsewhere

**Failure:** A worker that cached "no candidates" does not evaluate a later candidate written by another runtime sharing its database, even after an explicit policy snapshot refresh. Traffic handled by that worker contributes no shadow evidence until a local write or restart invalidates the cache.

**Evidence:** `_check_has_any_candidates` at `src/uns/shadow_evaluator.py:357` keys its negative cache only to `_write_seq` counters on the local policy and learning store objects. Peer writes cannot advance those counters. The candidate check returns before querying durable state at `:362`.

**Proof:** `test_shadow_candidate_cache_misses_other_process_writes` uses two independently constructed runtimes and store instances on one database. It demonstrates the first evaluator missing a candidate that it can read from the database and that the second evaluator evaluates. This is a shared-database multi-instance reproduction, not a separate-process network test.

**Remediation:** Use a durable candidate revision or a bounded freshness check covering PREVIEW revisions and SHADOW deltas. ACTIVE snapshot revision alone is insufficient because candidate changes need not activate an ACTIVE snapshot. Any notification optimization must recover from dropped broadcasts and invalidate negative as well as positive caches.

### F08 P1 Policy lifecycle operations commit partial transitions

**Failure:** If PREVIEW persistence fails after the delta transitions to SHADOW, the request fails but SHADOW remains committed with no PREVIEW row; retrying the operation is rejected by the state machine. Approval and activation contain analogous split commits.

**Evidence:** `promote_to_shadow` calls the independently committing `transition_delta` at `src/uns/shadow_evaluator.py:789`, then `save_policy` at `:798`. Approval does the same at `:861` and `:871`. Activation saves ACTIVE first at `:949`, then transitions APPLIED at `:967`. `SQLAlchemyPolicyLearningStore.transition_delta` commits internally at `src/db/policy_learning_store.py:243`.

**Proof:** `test_failed_preview_persistence_leaves_shadow_state_committed` injects a policy-store write failure after the transition on both databases and verifies committed SHADOW, missing PREVIEW, and failed retry. The approval and activation variants are source-established instances of the same transaction-boundary flaw, not separately fault-injected here.

**Remediation:** Add transaction-scoped store operations that accept the same caller-owned SQLAlchemy session. In one transaction, lock and revalidate baseline/state, persist the policy revision and evidence, then advance the proposal state. Broadcast only after commit. Retain idempotent retry behavior after an uncertain HTTP response.

### F09 P1 Approval settlement can lose the resume callback

**Failure:** An `on_settled` exception occurs after the bridge has cached terminal approval state. Repeating resolution returns the terminal record without retrying the callback; `sync_from_runtime` also exits early for terminal cached state. A durable notification does not make this resume effect durable.

**Evidence:** `_finalize` updates `_by_decision_id` before invoking `on_settled` at `src/uns/governance/approval_workflow.py:439`. `resolve_approval` returns terminal cached records at `:394`, and `sync_from_runtime` does so at `:338`. The core runtime's separate durable callback mechanism (`src/uns/runtime.py:1221`) does not automatically own the bridge's synchronous callback.

**Proof:** `test_terminal_callback_failure_is_not_retried` dispatches a runtime-backed approval, makes its settlement callback fail, then retries resolution. The approval remains APPROVED and the callback is called only once, on both databases. A trusted host can build its own recovery around this callback, but none is supplied by this bridge.

**Remediation:** Persist a settlement callback job keyed by approval/event ID and recover it independently of the approval's terminal state. Reuse the existing durable callback pattern and define at-least-once consumption. Distinguish successful state settlement from callback delivery failure in the API.

### F10 P2 Policy conversion changes a zero deduplication window to 300 seconds

**Failure:** A valid explicit zero window becomes five minutes when converted through the policy-evolution helpers, so unrelated changes or a zero-window proposal can silently alter coalescing behavior.

**Evidence:** `config_dict_to_policy` uses `int(config.get('dedup_window_seconds') or 300)` at `src/uns/shadow_evaluator.py:203`, while proposal normalization permits zero at `:289`.

**Proof:** `test_zero_dedup_window_is_silently_replaced` proves the conversion from 0 to 300. It does not claim every runtime deduplication path treats zero as a complete disable switch; it establishes loss of an explicit supported value.

**Remediation:** Default on `None` or an absent field, never on numeric falsiness. Assert exact semantic round trips and approved-candidate equality for zero and other boundary values.

### F11 P2 The SLO receipt can certify a stalled sparse workload

**Failure:** The report returns `v1_0_certified: true` with two successful sample attempts fourteen days apart and a different accepted notification still PENDING for fourteen days. A synthetic custom adapter with no `recording_only` metadata is counted as live provider activity.

**Evidence:** Classification treats a missing recording flag as live at `src/uns/slo.py:118`. Observation span uses only first/last live attempt timestamps at `:173`. Gates at `:184` do not bound pending age, due-attempt lateness, pending callbacks, observation gaps, or minimum useful sample volume.

**Proof:** `test_slo_certifies_with_two_samples_and_two_week_stalled_backlog` creates that exact report. It demonstrates the gate's insufficiency, not forged production evidence or a claim that all custom adapters are untrusted. `tests/uns/test_slo_certification.py` already intentionally accepts sparse two-sample certification, so this is a contract-strength gap as well as a code change to consider.

**Remediation:** Define production certification criteria separately from a snapshot summary: explicit adapter/provider provenance, successful live attempts, minimum sample volume, coverage by observation bucket, and bounded delivery/callback backlog. Report "insufficient evidence" when those criteria cannot be established. Preserve configurable rehearsal reports without labeling them production certification.

### F12 P2 Channel health remains healthy during repeated delivery failures

**Failure:** Five actual synthetic Slack delivery failures create dead letters, but `/api/v1/channels/health` still reports Slack HEALTHY with zero consecutive failures. Unconfigured channels also default to healthy.

**Evidence:** The HTTP app constructs an independent tracker at `src/uns/app.py:264`. `Runtime._channel_result` at `src/uns/runtime.py:530` records durable evidence without feeding that tracker; `DeliveryService` records Prometheus counters at `src/notification/service.py:350`, not tracker outcomes. `ChannelHealthTracker.get_channel_health` returns a default HEALTHY object at `src/notification/channel_health.py:59`. MCP `RuntimeState` similarly creates a fresh tracker at `src/uns_mcp/runtime.py:51`.

**Proof:** `test_channel_health_stays_healthy_after_repeated_delivery_failures` demonstrates the misleading HTTP status after real dispatcher failure paths on both databases. Optional channel failure should remain separate from process readiness; it should still be visible accurately in the channel-health panel.

**Remediation:** Derive channel health from runtime delivery evidence or update an explicitly runtime-owned tracker from final channel results. Represent unconfigured/never-observed channels explicitly. Bind HTTP and MCP to that same state and define how status aggregates across nodes.

### F13 P2 Readiness failures return successful HTTP status

**Failure:** A storage/progress failure produces HTTP 200 with `status: not_ready`, so readiness consumers relying on HTTP status can retain an unhealthy instance in service.

**Evidence:** The exception branch returns an ordinary dictionary at `src/uns/app.py:370`; FastAPI therefore uses HTTP 200. The console already supports `503`-tolerant readiness parsing (`apps/ui/src/api/operations.ts`), and the scope document describes degraded readiness handling at `docs/ui/ui-scope.md:48`.

**Proof:** `test_readiness_failure_uses_http_200` injects an operational-progress failure and verifies the 200/not_ready combination on both databases. The provided development Compose check additionally reads the JSON status and therefore detects this case; generic HTTP readiness checks do not.

**Remediation:** Return an explicit HTTP 503 JSON response for not-ready results, preserve the diagnostic body, and test both HTTP-status-only and body-aware consumers.

### F14 P2 Cross-process reload listeners exist without daemon lifecycle integration

**Gap:** The shipped daemon does not establish a PostgreSQL policy listener, nor a Redis subscription/polling loop for policy reload messages. Constructing a handler object is insufficient to consume broadcasts.

**Evidence:** `src/uns/app.py:282` initializes the reload fields, leaves `policy_postgres_listener` unset, and constructs only a Redis handler at `:326` when WebSocket Redis is enabled. Its lifespan at `:221` owns only `runtime.worker()`. Searches for `PostgresPolicyReloadListener` and `RedisPolicyReloadSubscriber` outside their definitions find tests and construction, not an operational consuming loop. The listener classes are implemented at `src/uns/policy_runtime.py:89` and `:119`; the existing feature tests invoke handlers/polling directly.

**Contract:** `docs/API.md:269` and `docs/ROADMAP.md:15` advertise immediate cross-process warm-cache refresh. ACTIVE intake and inspection still query/refresh durable snapshots (`src/uns/policy_runtime.py:234` and `:267`), so this finding does **not** establish stale ACTIVE policy enforcement. It identifies missing advertised broadcast integration; F07 establishes a separate shadow-candidate cache defect that ACTIVE snapshot refresh alone does not repair.

**Remediation:** Either document the listener classes as embedded-host primitives and the daemon's on-demand refresh semantics, or wire consuming tasks into HTTP/MCP lifespans with reconnection, cancellation, and missed-message recovery. Verify with actual independent processes, not manual `handle_message` calls.

### F15 P2 Current documentation contradicts shipped contracts and loses published evidence links

**Gaps:**

- `README.md:31` calls action-authorization models unfinished/experimental, while `docs/PRODUCT.md:20` and `docs/API.md:333` expose a shipped opt-in gate. Integrators cannot determine the supported action boundary consistently.
- `docs/API.md:134` describes unrestricted instance-wide observer reads, while `docs/SECURITY-MODEL.md:18` and `docs/ROADMAP.md:17` advertise configured source/namespace isolation. This contradiction obscures F01.
- `docs/API.md:216` documents admin-only proposal creation with `notification_type` and `start_shadow`; the implementation accepts producers and requires `policy_type` and `promote_to_shadow` (`src/notification/routes.py:457`, `src/uns/responses.py:639`). An integrator following those field names receives validation errors, while the role statement conceals F06.
- `docs/SECURITY-MODEL.md:57` and `docs/ROADMAP.md:67` describe asynchronous shadow work, but `Runtime.accept` calls `evaluate_intake` synchronously at `src/uns/runtime.py:464`. `evaluate_intake_async` exists at `src/uns/shadow_evaluator.py:606` but is not invoked by canonical intake. The work includes database queries and aggregate recomputation. This is an implementation/latency-boundary mismatch; no production latency regression was measured here.
- The strict documentation build emits **39 INFO link diagnostics**, including out-of-tree verification receipts and excluded historical targets. `mkdocs.yml:15` downgrades missing links to INFO and `:20` excludes the archive. The generated site therefore contains links to evidence/history it does not ship. A passing strict build is not proof those links work.

**Remediation:** Publish one current capability/auth matrix and executable request examples; explicitly label historical release receipts and host-supplied primitives. Generate or test examples against canonical request models and route dependencies. Route excluded archive and verification links to repository URLs, or deliberately publish the required artifacts. Raise missing-current-link validation after resolving intentional historical links. Reconcile shadow scheduling claims with actual intake execution.

## Iteration 1: Core Analysis

### Persona contributions

**Larrynator:**

- Tenant visibility is not an invariant shared by all reads. The nested-envelope mistake in `src/uns/routes.py:32` makes optional-value authorization fail open, whereas `src/uns/api/routes_notification.py:284` correctly reads the envelope and denies. F01's same-key, same-record control establishes an inconsistent boundary.
- An approval decision must identify the action it can resume. `_deterministic_decision_id` (`src/uns/governance/decision_engine.py:115`) does not include tenant/resource, and `request_approval` (`src/uns/governance/approval_workflow.py:178`) checks no bound-content fingerprint before reuse. F02 breaks that identity invariant.
- An approved candidate hash is useful only if activation selects that candidate. The latest-DRAFT lookup (`src/uns/shadow_evaluator.py:909`) and requested-delta APPLIED transition (`:967`) can describe different content. F03 is a configuration-authority defect despite a valid baseline hash.

**Curlytron:**

- Fixing only the nested lookup leaves alternate disclosures through `/ui/audit` and registered MCP tools (`src/uns/api/routes_ui.py:699`, `src/uns_mcp/factory.py:132`). A leaked notification ID can lead to further runtime inspection under F01; one transport-specific patch cannot close the boundary.
- Intake isolates obligations, but the provider collapses them again (`src/uns/runtime.py:369` versus `src/notification/adapters/pagerduty.py:525`). F04 demonstrates how a valid provider signature can authenticate the wrong obligation correlation without compromising the signing secret.
- A producer can choose the convenience path (`src/notification/routes.py:479`) instead of the admin-only path (`:494`). F06 shows why authorization should cover the operation independently of route shape.

**Moebot:**

- Anonymous 404 traffic permanently allocates metric objects (`src/notification/metrics.py:99`, `:132`), and the attack's cost accumulates even if request rate is bounded. F05 is availability exposure below the authenticated application routes.
- Green monitoring can coexist with failure: the tracker at `src/uns/app.py:264` never receives durable dispatcher results, and the readiness exception at `:370` returns HTTP 200. F12/F13 require fault injection, not a happy-path health test.
- Strong-looking SLO output is not sustained evidence. The six gates at `src/uns/slo.py:184` accept F11's sparse samples and two-week pending backlog; the report's own gauges contradict its certification label.

### Cross-critique in the forward triangle

**Larrynator to Curlytron:** A shared access helper alone is insufficient. If `src/uns/api/routes_ui.py:213` filters after pagination, counts and page behavior still describe forbidden records. F01's query constraints must be applied before limit/cursor selection, and F04 needs a persistent correlation mapping rather than a guessed tenant prefix.

**Curlytron to Moebot:** Health hardening cannot repair wrong-object authorization. A valid HMAC at `src/uns/api/routes_webhooks.py:428` still reaches the ambiguous target resolver at `src/uns/runtime.py:961`. The highest leverage is preserving one obligation identity from intake through provider response, with health derived from those same observations.

**Moebot to Larrynator:** Hash comparisons do not make a workflow atomic. `src/uns/shadow_evaluator.py:789` commits SHADOW before PREVIEW persistence, while `src/uns/governance/approval_workflow.py:439` caches settlement before the callback. F08/F09 show that interruption can violate the promised lifecycle even when all inputs and hashes are valid.

### Round 1 Friction Lock

**Two contradictions control the next round. First, the product claims a bounded obligation/approval identity, yet transport reads, provider keys, and approval caches apply different boundaries. Second, policy and approval workflows claim recoverable state, yet candidate selection, separate commits, and process-local caches/callbacks can sever the relationship between the intended operation and its recorded outcome.**

## Iteration 2: Second-Order Deep Dive

### Persona contributions focused on the friction lock

**Larrynator:**

- F01 requires authorization on the object being returned, including canonical owner transitions and collections. A signature is authentication for the provider event, not a substitute for F04's unique incident-to-obligation binding (`src/uns/runtime.py:984`). The verified signed-callback reproduction is the counterexample to equating authenticated input with correct target authority.
- F03 and F08 compose: a request can install the wrong candidate, and a later failure at the independently committing APPLIED transition (`src/uns/shadow_evaluator.py:967`) can leave ACTIVE configuration changed despite an error response. The exact-candidate binding and baseline check must be performed inside the activation transaction, not only before it.
- F02 also requires content-conflict detection for caller-supplied decision IDs. Adding tenant/resource to default hashing alone does not protect an explicit reused ID accepted by `decide(..., decision_id=...)` (`src/uns/governance/decision_engine.py:160`). That API is trusted host code, but its retry invariant should still reject incompatible content.

**Curlytron:**

- Adding broadcast subscribers does not by itself fix F07. Candidate cache invalidation depends on local `_write_seq` values (`src/uns/shadow_evaluator.py:358`), while ACTIVE snapshot refresh covers a different revision (`src/uns/policy_runtime.py:218`). Unify candidate freshness around a durable candidate-generation marker, with broadcasts as an optimization.
- Reuse the core runtime's durable callback model (`src/uns/runtime.py:1221`) for F09 rather than inventing a second fire-and-forget resume mechanism. Signatures can be regenerated for each retry; a stable settlement event ID provides consumer deduplication.
- Candidate selection and provider target resolution have the same structural mistake: searching "latest matching type/key" instead of loading an immutable exact binding (`src/uns/shadow_evaluator.py:909`, `src/uns/runtime.py:990`). Replace both searches with durable identity associations.

**Moebot:**

- Moving shadow evaluation to `asyncio.to_thread` is not enough. F08's stores use multiple transactions, and F07's cache is process local. Correct the data invariants first; then bound queue length and recovery semantics before claiming asynchronous processing (`src/uns/runtime.py:464`, `src/uns/shadow_evaluator.py:606`).
- A callback failure must not be hidden as a repeated successful settlement. F09's terminal-state short circuit (`src/uns/governance/approval_workflow.py:394`) needs an independently visible delivery state. Restart may cause a callback to run again, so the target must deduplicate by the stable event ID.
- F11 should not be fixed by simply adding `pending_count == 0`: a healthy active service can have recent work in progress. Bound age/lateness and observation gaps instead. The report already computes those gauges, but the gates ignore them (`src/uns/slo.py:184`).

### Cross-critique in the reversed triangle

**Larrynator to Moebot:** The demonstrated F05 allocation is unbounded in distinct URLs, while the per-path sample deque in `src/uns/api/observability.py:141` bounds only samples for one key. The remedy must bound the number of keys, not shrink deque length. For F11, select explicit finite age/coverage budgets; a clean queue is neither necessary nor sufficient proof of sustained service.

**Moebot to Curlytron:** Durable mappings must survive retries, incident key migration, and callback replay. Reusing `Runtime.deliver_callbacks` (`src/uns/runtime.py:1221`) brings a bounded retry policy, not guaranteed external completion. Preserve visible exhaustion and a manual recovery path; do not replace a lost callback with an invisible exhausted callback.

**Curlytron to Larrynator:** A universal access context should carry both capabilities and object bounds. Otherwise producer flags can still invoke administrative operations through a different route (`src/notification/routes.py:479`), while collection filters can still omit source (`src/uns_mcp/tools.py:497`). Keep one explicit operation boundary without hiding policy decisions in route-specific convenience parameters.

## Iteration 3: Remediation & Proof

### Exact implementation invariants

**Larrynator defines the closure conditions:**

1. For every returned notification `n`, require `principal.allows_source(n.source) and principal.allows_namespace(n.notification_type)`. Introduce a query input such as `DeliveryFilter(access=AccessContext(...))` and equivalent audit/DLQ filters; count, cursor, and row selection must share the predicate. `require_source_and_namespace` should not silently accept a missing required record attribute. This addresses F01 at `src/uns/routes.py:32` and `src/uns/api/routes_ui.py:213`.
2. Define approval identity as a versioned canonical JSON object containing `action_instance_id`, `tenant_id`, `resource_type`, `resource_id`, `subject_id`, `policy_config_hash`, and `context_hash`. Persist its fingerprint with the decision-to-obligation association. `request_approval(record, action_instance_id=...)` must return the prior request only when the fingerprint matches; otherwise raise a typed conflict. This addresses F02 at `src/uns/governance/approval_workflow.py:178`.
3. A policy activation transaction must load the locked delta, load its exact `draft_policy_id`, verify approved candidate content and fresh baseline, write ACTIVE authority, append APPLY evidence, and commit together. Store helpers must accept `session: Session` without committing when the caller owns the transaction. This closes F03/F08 at `src/uns/shadow_evaluator.py:909` and `:949`.
4. Provider key generation must consume an immutable canonical obligation/generation ID, not the raw producer dedup key. Resolve webhooks through a unique persisted provider-key association, then resolve allowed follower lineage. The same stored key must be used by `sync_pagerduty_incident` (`src/uns/runtime.py:1038`). This closes F04 without relying on signature changes.
5. Unknown HTTP paths must map to one constant metrics label, and terminal approval state must be separate from callback delivery state. These invariants target F05 (`src/notification/metrics.py:99`) and F09 (`src/uns/governance/approval_workflow.py:439`).

**Curlytron limits the implementation:**

- Reuse existing scope matching, query adapters, policy evidence binding, SQLAlchemy sessions, and runtime callback claims. F01/F03/F08/F09 do not require another authorization framework, broker, or dependency (`src/uns/api/auth.py`, `src/db/policy_learning_store.py`, `src/uns/runtime.py`).
- Keep broadcasts optional optimizations on top of durable revision checks. Implement F07's candidate-generation freshness before wiring F14's Redis/PostgreSQL lifecycle tasks (`src/uns/shadow_evaluator.py:357`, `src/uns/app.py:326`).
- Preserve `0` exactly with an explicit `None` test in `config_dict_to_policy`; compare the final materialized candidate to the approved configuration before persistence. That small change prevents F10 from silently undermining F03's stronger hash binding (`src/uns/shadow_evaluator.py:203`).

**Moebot defines the proof:**

- Convert the audit's issue-presence probes into secure regression expectations: deny every cross-scope read, produce distinct approvals/provider keys, activate exactly A when A is selected, and allocate constant metric cardinality. Keep the current audit probes separate because they intentionally pass while defects exist (`test_audit_probes.py`).
- Inject failures between every proposed policy lifecycle write and verify rollback on both databases. Race two approvals/activations and test retry after a lost response. Extend F08 beyond the reproduced PREVIEW failure (`src/uns/shadow_evaluator.py:789`, `:861`, `:949`).
- Kill/restart callback workers after the external receiver accepts but before local completion is recorded. Verify at-least-once retry plus receiver deduplication; never claim exactly-once resume delivery (`src/uns/runtime.py:1221`).
- Exercise two real HTTP/MCP processes with missed/reconnected broadcasts; F07's current two-runtime proof already demonstrates the data flaw, while F14 needs actual lifecycle evidence (`src/uns/app.py:221`).
- Prove readiness returns HTTP 503 under storage failure and channel health degrades after failures, while synthetic/sparse data cannot satisfy production certification (`src/uns/app.py:370`, `src/uns/slo.py:184`).

## Executive Synthesis & Prioritized Action Plan

| Priority / Round | Core Dialectical Synthesis | Concrete Remediation (`file:symbol`) | Verification / Proof |
| :--- | :--- | :--- | :--- |
| **P1 / R1-3 / F01** | Tenant/source bounds are missing from alternate reads. | `uns/routes.py:inspect_notification`, `api/routes_ui.py`, `uns_mcp/tools.py`: enforce one record-aware access context in queries. | Nine reproduced bypass cases per backend; extend denial matrix to DLQ, counts, owners, and MCP source lists. |
| **P1 / R1-3 / F02** | One action's approval can be returned for a different tenant/resource. | `governance/decision_engine.py:_deterministic_decision_id`, `approval_workflow.py:request_approval`: bind trusted action identity and fingerprint. | Distinct tenant/resource/action identities never reuse approval; identical retries do. |
| **P1 / R1-3 / F03** | The selected proposal and activated draft can differ. | `shadow_evaluator.py:activate_draft`: persist exact draft-to-delta/content association. | Two approved candidates; activating A installs A or returns a conflict. |
| **P1 / R1-3 / F04** | External incident correlation discards intake isolation. | `adapters/pagerduty.py:_get_dedup_key`, `runtime.py:resolve_pagerduty_target`: persisted obligation-specific provider key. | Colliding producer keys remain distinct; signed callback settles only its mapped obligation. |
| **P1 / R1-3 / F05** | Unauthenticated URLs allocate permanent metric children. | `notification/metrics.py:_resolve_path_template`, `api/observability.py`: constant unmatched labels. | Large unique-404 set leaves metric key count constant. |
| **P1 / R1-3 / F06** | A convenience flag bypasses operation-level authorization. | `notification/routes.py:create_policy_proposal`: require admin for `promote_to_shadow`. | Producer stays PROPOSED or receives 403 on either promotion route. |
| **P1 / R2-3 / F07** | Local negative caches suppress peer-created shadow evidence. | `shadow_evaluator.py:_check_has_any_candidates`: durable candidate freshness. | Peer-created PREVIEW/SHADOW candidate evaluated on every warm worker; dropped messages recover. |
| **P1 / R1-3 / F08** | Multi-store lifecycle writes are partially committed. | `shadow_evaluator.py`, `db/policy_learning_store.py`, `db/policy_store.py`: caller-owned transaction. | Fault injection and concurrent operations preserve all-or-nothing lifecycle/evidence. |
| **P1 / R1-3 / F09** | Durable approval state does not recover a failed resume callback. | `governance/approval_workflow.py:_finalize`: durable independent callback job. | Failed callback retries across request retry/restart; stable receiver deduplication. |
| **P2 / R3 / F10** | Conversion changes an explicit zero policy value. | `shadow_evaluator.py:config_dict_to_policy`: default only on absence/None. | Exact round trip and full proposal-to-ACTIVE test for zero. |
| **P2 / R1-3 / F11** | Certification ignores stalled backlog and sparse observation. | `slo.py:compute_slo_report`: provenance, age/lateness, volume, coverage gates. | Sparse synthetic samples and fourteen-day pending backlog fail certification. |
| **P2 / R1-3 / F12** | Channel status is detached from dispatcher results. | `app.py:create_app`, `runtime.py:_channel_result`, `uns_mcp/runtime.py`: shared runtime-owned health. | Failure/recovery and unconfigured-channel scenarios agree across transports. |
| **P2 / R1-3 / F13** | Not-ready responses use HTTP success. | `app.py:ready`: explicit HTTP 503 with retained body. | Storage failure returns 503; normal readiness returns 200. |
| **P2 / R2-3 / F14** | Broadcast handler classes are not consuming daemon tasks. | `app.py:lifespan`, `policy_runtime.py`: wire lifecycle or narrow contract. | Two-process notification/reconnect test; retain durable fallback. |
| **P2 / R1-3 / F15** | Current docs disagree on auth, gate status, request fields, scheduling, and evidence links. | `README.md`, `docs/API.md`, `docs/SECURITY-MODEL.md`, `mkdocs.yml`: reconcile executable contracts and published links. | Request-example checks, route-auth matrix, generated-site link validation. |

## Meta-Critique: Remaining Blind Spots

- **Real provider semantics:** PagerDuty correlation and signed-callback behavior were reproduced with local provider effects. Production service/account configuration, historical incident migration, Slack message-update behavior, human receipt, and provider redelivery need an explicitly authorized live pilot. No production exploit or provider receipt is claimed.
- **Deployment and distributed operations:** PostgreSQL 16 was exercised locally and the audit defects reproduced on both databases. Actual independent-process reload subscriptions, production reverse-proxy limits, multi-node restart/failover, and representative sustained capacity remain outside this result. F14 is source-backed integration evidence, not a completed cross-process runtime experiment.
- **Remediation assurance:** Static checks and existing tests are green despite these defects. The new probes establish issue presence, not completed fixes, and this was one review using three lenses. Application remediation requires focused secure regression tests, fresh CI, and separate deployment acceptance.

**First Strike:** Close F01 before using source/namespace keys as a tenant-isolation boundary. Reproduce locally with `.venv/bin/python -m pytest verification/mpdd-2026-11-03/test_audit_probes.py -q -k 'scoped_http or ui_reads or registered_mcp'`, then change those cases into denial expectations as part of the authorization fix. Address F02-F04 before relying on governance approvals or shared-provider incident correlation for independent actions/tenants.

## Artifact use

`test_audit_probes.py` runs with temporary SQLite databases by default. Run `.venv/bin/python verification/mpdd-2026-11-03/run_postgres.py --include-acceptance` to provision a disposable container, run the existing acceptance module and the SQLite/PostgreSQL audit matrix, and remove the container. To include PostgreSQL, set `UNS_AUDIT_DATABASE_URL` to a disposable PostgreSQL database; the harness creates and removes uniquely named schemas for runtime-backed cases. No provider network calls are made. `results.json` records verification outcomes, `inventory.json` records baseline tracked-file hashes, and `logs/` retains sanitized command evidence. The existing acceptance module was run only against a separate disposable database because its fixtures reset database state.

These issue-presence probes deliberately live outside normal test discovery. Their passing result means the vulnerability/defect was observed; a fixed implementation should invalidate the corresponding issue assertion until it is converted to the desired regression expectation.
