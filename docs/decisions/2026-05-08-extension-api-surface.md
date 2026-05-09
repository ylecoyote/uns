# Plugin Extension API Surface

Date: 2026-05-08

Status: Accepted

Linear: TBD

## Context

PRD §2.6 and M8 lock the two-tier extension model: three stable Protocols
(`OverrideAuthority`, `AuditHook`, `WorkflowOrchestrator`) plus one callable
hook (`IdentityProvider`). PRD M8.5 defers exact signatures, plugin lifecycle,
discovery model, and versioning to this ADR. ADR-001 specifies the
`WorkflowOrchestrator` *behavioral* contract (retry, timeout, escalation,
restart-recovery); this ADR locks the *type-level* contract every plugin
author writes against. ADR-007 fixes the `decide()`/`evaluate()` boundary;
ADR-008 fixes the fail-mode envelope; both are upstream of this surface.
Plugin Trust Model (sandboxing, signing, capability scoping) is ADR-005's
job and runs in parallel; this ADR specifies only what plugins look like at
the type and lifecycle level, not how they are sandboxed.

The v0.2 stack is async FastAPI + Pydantic v2 (HARD-04, §9.5). All extension
methods are defined async-first to match the runtime; the signing of method
shapes here is what unblocks parallel commercial-plugin development.

## Decision

### 1. Method signatures

All Protocols are `typing.Protocol` (structural). Plugins implementing the
hook tier are bare callables or single-method ABCs.

```python
# agsignal.contracts (the public boundary; see decision 7)
from typing import Protocol, Literal, runtime_checkable
from agsignal.contracts import (
    DecisionRecord, Identity, OverrideResult, AuditEntry,
    ApprovalContext, WaitHandle, ApprovalStatus, AuditEvent,
)

@runtime_checkable
class OverrideAuthority(Protocol):
    async def should_override(
        self, decision: DecisionRecord, context: dict
    ) -> OverrideResult: ...
    # OverrideResult = {applied: bool, new_decision: DecisionRecord | None,
    #                   reason: str, override_id: str}

@runtime_checkable
class AuditHook(Protocol):
    async def record(
        self,
        stream: Literal["decision", "approval", "delivery"],
        entry: AuditEntry,
    ) -> None: ...
    # Single-method, stream-tagged. Not split per-stream — keeps the
    # Protocol minimal and lets implementations dispatch internally.

@runtime_checkable
class WorkflowOrchestrator(Protocol):
    async def createApprovalWait(self, ctx: ApprovalContext) -> WaitHandle: ...
    async def resumeApproval(
        self, handle: WaitHandle, outcome: Literal["APPROVED", "REJECTED"]
    ) -> None: ...
    async def expireApproval(self, handle: WaitHandle) -> None: ...
    async def queryApproval(self, handle: WaitHandle) -> ApprovalStatus: ...
    # ApprovalStatus = PENDING | APPROVED | REJECTED | TIMED_OUT |
    #                  LOST_ON_RESTART (OSS-only, per ADR-001 §8)
    async def fetchAudit(self, correlation_id: str) -> list[AuditEvent]: ...

# IdentityProvider — hook tier (callable; not yet a Protocol per §2.6)
IdentityProvider = Callable[[str | None], Awaitable[Identity]]
# resolve_identity(token) -> Identity | raises IdentityResolutionError
```

Camel-case is preserved on `WorkflowOrchestrator` to match PRD M8.3's locked
method names; new surfaces in this ADR (`should_override`, `record`) follow
PEP 8 snake_case. `IdentityProvider` ships as a typed callable in v1; it
promotes to a Protocol per the M8.B promotion criterion.

### 2. Sync vs async: async-only at the boundary

All extension methods return `Awaitable`. PRD §9.5 fixes async FastAPI as
the runtime; a sync extension surface would force `asyncio.to_thread` on
every plugin call and re-introduce the engine-side blocking ADR-001 §5
rejected. Plugin authors needing sync internals call `asyncio.to_thread`
themselves; AGSignal core does not provide a sync facade. (This matches
ADR-001 §5: "no OSS sync wrapper ships in v1.0.")

### 3. Plugin lifecycle

Lifecycle methods live on a separate `PluginLifecycle` Protocol, optional
to implement. Plugins that omit it are loaded directly with no init.

```python
@runtime_checkable
class PluginLifecycle(Protocol):
    async def load(self, config: dict) -> None: ...    # post-import, pre-init
    async def init(self, host: PluginHost) -> None: ...  # AGSignal injects
    async def teardown(self) -> None: ...               # graceful shutdown
```

Separation rationale: most plugins (e.g., a stateless `OverrideAuthority`)
need no lifecycle; bundling lifecycle into every Protocol would force empty
implementations everywhere. `PluginHost` exposes a minimal logger and
`correlation_id` propagation utility (see decision 7).

`load` runs once at process start, before any extension call; `init`
receives the host handle; `teardown` is called on graceful shutdown only
(SIGKILL gives no teardown).

### 4. Discovery model: explicit registration only in v1.0

`agsignal.yaml` declares plugins explicitly:

```yaml
plugins:
  identity_provider:
    module: agsignal_jws_identity
    class: JWSIdentityProvider
    config: { jwks_url: "https://..." }
  audit_hooks:
    - module: agsignal_merkle_audit
      class: MerkleAuditHook
```

Entry-point auto-discovery (`setuptools` `entry_points`) is **deferred to
v1.1+ pending ADR-005** (Plugin Trust Model). PRD M9.5 explicitly ties
auto-discovery to the trust model landing first; auto-loading unsigned
third-party code by file-system presence is the primary supply-chain risk
the trust model has to address.

When ADR-005 lands, the model is **explicit-overrides-auto**: declared
plugins in `agsignal.yaml` win over discovered entry points; this is the
forward-compatible stance.

### 5. Versioning: independent semver per Protocol

Each Protocol versions independently as `agsignal.contracts.OverrideAuthority
@ 1.0`, etc., declared via a class-level `__contract_version__: str`
attribute. Plugins declare conformance:

```python
class MyAuditHook:
    __contract_version__ = "AuditHook@1.0"
    async def record(self, stream, entry): ...
```

AGSignal core validates the declared version against its loaded contract
set at plugin `load`. Mismatch is a hard failure (plugin not loaded, error
logged, OPERATIONAL notification per ADR-008 §5). Backwards compatibility:
Protocol minor version bumps add optional methods or fields only;
major bumps are breaking and require a plugin recompile. Independent
versioning lets `AuditHook@1.1` ship without touching `OverrideAuthority`.

### 6. Multiplicity per extension point

| Extension point        | Multiplicity      | Rationale |
|------------------------|-------------------|-----------|
| `OverrideAuthority`    | **1:1** (one)     | Multiple authorities introduce ordering ambiguity over decision overrides; pick one explicitly. |
| `AuditHook`            | **1:N** (many)    | Audit fan-out is the canonical case (local + Merkle + external SIEM). All hooks called per entry; failures isolated per hook (ADR-008 fail-mode applies per-call, not aggregate). |
| `WorkflowOrchestrator` | **1:1** (one)     | Two orchestrators would split pending-decision state; non-recoverable. |
| `IdentityProvider`     | **1:1** (one)     | Identity ambiguity is a security smell; one provider resolves all approver identities. |

For 1:N (`AuditHook`), call order is registration order; a hook raising does
not abort siblings. AGSignal logs the failure per ADR-008 §5 but does not
fail-mode the originating decision unless the hook is flagged
`fail_mode_on_error=true` at registration.

### 7. Plugin-side import boundary

Public API: **`agsignal.contracts`** — the only stable import surface for
plugins. It re-exports:

- Data shapes: `DecisionRecord`, `Identity`, `OverrideResult`, `AuditEntry`,
  `ApprovalContext`, `WaitHandle`, `ApprovalStatus`, `AuditEvent`
- Protocols: `OverrideAuthority`, `AuditHook`, `WorkflowOrchestrator`,
  `PluginLifecycle`, `IdentityProvider`
- Errors: `PluginError`, `PluginTimeout`, `PluginConfigError`,
  `IdentityResolutionError`, `ContractVersionMismatch`
- Host utilities: `PluginHost` (logger + `correlation_id` propagator)

Anything outside `agsignal.contracts` (e.g., `agsignal.engine.internals`,
`agsignal.workflow.lightweight`) is **internal**; plugins importing it
break across minor versions without warning. Static checkers SHOULD flag
deep imports from plugin packages.

### 8. Error handling at the boundary

Plugins raise typed errors from `agsignal.contracts`:

- `PluginError` — generic plugin failure (base class)
- `PluginTimeout` — bounded wall-clock cap exceeded (default 5 s for
  `OverrideAuthority` / `AuditHook`; per-call configurable)
- `PluginConfigError` — raised at `load`/`init`; prevents plugin activation
- `ContractVersionMismatch` — raised at `load`; prevents plugin activation

Plugin failures cascade per ADR-008 §3:

- `OverrideAuthority` raises → `engine_failure_internal` (fail-mode applies)
- `AuditHook` raises → logged; decision not fail-moded unless registered
  with `fail_mode_on_error=true` (audit-loss tolerance is per-deployment)
- `WorkflowOrchestrator` raises → `engine_failure_internal`; pending
  decisions in flight follow ADR-001 §8 (`LOST_ON_RESTART` for OSS, durable
  recovery for commercial)
- `IdentityProvider` raises → `engine_failure_attribute_source` (ADR-008 §3)

Untyped exceptions from plugins are wrapped in `PluginError(cause=...)` at
the boundary; the engine never receives a raw third-party exception type.

## Rejected

### Single mega-Protocol covering all extension points

Rejected. A unified `AGSignalPlugin` Protocol would force every plugin
(audit-only, identity-only, override-only) to stub out methods it does not
care about. The two-tier model (§2.6) explicitly avoids this; per-Protocol
shapes match the matrix-validated abstractions and stay minimal.

### Sync method signatures

Rejected. Async-FastAPI is the locked runtime (PRD §9.5, HARD-04). Sync
extension methods would impose `to_thread` overhead on every call and
contradict ADR-001 §5's "engine never blocks" commitment.

### Auto-discovery via `setuptools` entry points in v1.0

Rejected for v1.0. PRD M9.5 ties auto-discovery to the Plugin Trust Model
(ADR-005, parallel). Loading third-party code by file-system presence
without signing/capability-scoping is the supply-chain risk the trust
model has to address; shipping it first inverts the dependency. Reopens in
v1.1 once ADR-005 lands.

### Lifecycle methods on every Protocol

Rejected. Most plugins are stateless (a single-function `OverrideAuthority`
needs no `load`/`teardown`). Bundling lifecycle into the contract Protocols
forces empty implementations across the ecosystem. The optional
`PluginLifecycle` Protocol opts plugins in only when they have state.

### Single global `__agsignal_contract_version__` at v1

Rejected. Locking all four extension points to the same semver line means
adding a method to `AuditHook` forces a major bump on `WorkflowOrchestrator`
even though its contract is unchanged. Independent per-Protocol versioning
lets each surface evolve at its own cadence; the cost (slightly more
plugin-side declaration) is small.

### Untyped `dict` for plugin error returns

Rejected. ADR-008's fail-mode reasons are a closed list; plugins raising
arbitrary string codes would break operator runbook authoring. Typed
exceptions in `agsignal.contracts` give plugins a finite vocabulary and
let static checkers flag misuse.

## Consequences

**Plugin-author DX.** A v1.0 plugin is roughly 50–150 lines: implement
one Protocol method, declare `__contract_version__`, register in
`agsignal.yaml`. No lifecycle code unless the plugin has state. No
sync/async bridging — the runtime is async end-to-end. Typed errors
from `agsignal.contracts` give IDE autocomplete on the failure surface.

**Commercial-plugin development unblocked.** With signatures locked,
JWS-Identity, SPIFFE-Auth, Merkle-Audit, Break-Glass, and DurableWorkflow
can build in parallel against a stable contract set. Each picks its
extension point per the §6 deferred-plugins table; no cross-plugin
coordination required for v1.0.

**v1 → v2 evolution path.** `IdentityProvider` is the explicit
hook-to-Protocol promotion target (M8.B): once two production identity
backends ship and a stable common contract emerges, this ADR is amended
(or superseded) to elevate the hook to a 1.0 Protocol. The independent
versioning model (decision 5) means this happens without disturbing the
other three contracts. Auto-discovery (decision 4) reopens in v1.1
following ADR-005.

**Constraints on plugin code.** Plugins MUST import only from
`agsignal.contracts`; deep imports break across minor versions. Plugins
SHOULD propagate `correlation_id` and `decision_id` through every
extension call (PRD M9.4); this is enforced at code review in v1, runtime
once ADR-005 lands. `AuditHook` 1:N fan-out means a slow audit hook
amplifies per-decision latency; deployments tune timeouts per registration.

**Operational implications.** Plugin load failures are surfaced as
OPERATIONAL notifications (ADR-008 §5) rather than crashing the process;
operators see "plugin X failed to load: contract version mismatch" instead
of a stack trace. The closed error vocabulary (§8) gives runbook authors
a finite enumeration to handle.

## References

- PRD §2.6, M8 (Plugin Extension Points), M9 (Plugin Design Principles + Trust Model), §11 (`agent_governance_control_plane_prd.md`)
- ADR-001 (Approval Workflow Semantics) — `2026-05-08-approval-workflow-semantics.md`
- ADR-007 (Decision Engine Internal Shape) — `2026-05-08-decision-engine-shape.md`
- ADR-008 (Fail-mode Semantics) — `2026-05-08-fail-mode-semantics.md`
- Stage 2 production-pattern matrix (`docs/internal/superpowers/specs/2026-05-08-stage2-production-pattern-matrix.md`) — five-method `WorkflowOrchestrator` shape derivation
- Vision B+ scope sketch (`docs/internal/superpowers/specs/2026-05-08-vision-b-plus-design.md`)
- [PEP 544 — Protocols: Structural subtyping](https://peps.python.org/pep-0544/) — `typing.Protocol` semantics; basis for the contract surface
- [setuptools entry points](https://setuptools.pypa.io/en/latest/userguide/entry_point.html) — auto-discovery mechanism deferred to v1.1
- [Pydantic v2 model contracts](https://docs.pydantic.dev/latest/) — data-shape carrier for `DecisionRecord`, `AuditEntry`, etc.
