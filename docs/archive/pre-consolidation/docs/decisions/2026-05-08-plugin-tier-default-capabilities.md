> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Plugin Tier Default Capabilities

Date: 2026-05-08

Status: Accepted

Linear: TBD

## Context

ADR Plugin Trust Model (`2026-05-08-plugin-trust-model.md`, §5) defines four
trust tiers — First-Party, Verified, Community, Local — and explicitly notes
that administrative-enumeration grading is required for compliance evidence.
Stage 2 Plugin-trust research (Perplexity Deep Research on OSS plugin
ecosystem precedents) surfaced an unambiguous principle: **"trust tiers must
materially change default capabilities, not just labels."** Trust models that
grade administratively but treat all loaded plugins identically at the
capability level fragment at scale (Casbin's documented warning case) —
operators cannot reason about blast radius and auditors cannot distinguish
high-trust from low-trust execution paths after the fact.

ADR Plugin Trust Model commits to graded administrative visibility (`GET
/plugins` exposes computed trust level per plugin) but did not specify how
the four tiers differ in *runtime capabilities*. This follow-up ADR fills
that gap by locking per-tier default extension-point access, the operator-
elevation override mechanism, and Local-tier audit-flag semantics.

This ADR is a follow-up amendment to ADR Plugin Trust Model (PRD §M9.5);
both must be in force before the first commercial plugin ships.

## Decision

### 1. Per-tier default extension-point access

| Trust tier | Default extension points permitted | Operator opt-in required for | Auto-load on startup |
|---|---|---|---|
| **First-Party** | All M8 hooks: `OverrideAuthority`, `AuditHook`, `WorkflowOrchestrator`, `IdentityProvider` | None — full capabilities | Yes (subject to manifest + signing checks per ADR Plugin Trust Model §1, §7) |
| **Verified** | `AuditHook`, `IdentityProvider`, `WorkflowOrchestrator` | `OverrideAuthority` (see §2 elevation) | Yes |
| **Community** | `AuditHook` only (read-mostly, side-effect-free except logging — aligns with M9.A principle 3) | `OverrideAuthority`, `WorkflowOrchestrator`, `IdentityProvider` (see §2 elevation) | Yes |
| **Local** | None implicitly; operator MUST explicitly enumerate permitted extension points per plugin | All capabilities require explicit per-plugin operator declaration | **No** — never auto-loaded |

**Rationale per extension point:**

- **`OverrideAuthority`** requires Verified-or-First-Party tier by default
  because it is the equivalent of root-of-trust override — it can elevate
  decisions to ALLOW/DENY/REQUIRE_APPROVAL outcomes that bypass policy
  evaluation. A compromised `OverrideAuthority` plugin is the most-impactful
  failure mode in the Plugin Trust Model.

- **`WorkflowOrchestrator`** requires Verified-or-First-Party tier by
  default because the default OSS lightweight in-memory orchestrator (PRD
  §2.9) handles all approval workflow state; replacing it with a third-
  party implementation shifts the operational fate of pending approvals to
  the plugin. Stage 2 research's "governance-as-data-plane-dependency" anti-
  pattern applies directly: a misbehaving WorkflowOrchestrator can lose
  pending approvals, corrupt resume callbacks, or stall the entire approval
  pipeline.

- **`AuditHook`** is permitted at Community tier by default because it is
  write-only-to-audit, side-effect-free except logging (per M9.A), and
  adding an audit destination cannot lose the in-AGSignal authoritative
  audit chain (which always runs; see ADR Audit Ledger Physical Structure
  §5). A misbehaving AuditHook degrades observability for that specific
  destination but cannot corrupt the authoritative streams.

- **`IdentityProvider`** requires Verified-or-First-Party tier by default
  because incorrect identity resolution propagates into every Approval
  Audit entry; a compromised `IdentityProvider` corrupts forensic evidence
  at the source. The OSS-default HMAC IdentityProvider hook (per PRD M8.4
  AC) is the conservative-trust baseline; commercial replacements (JWS-
  Identity, SPIFFE-Auth) ship as First-Party trust by design.

### 2. Operator elevation mechanism

For tiers below First-Party, operators may elevate a specific plugin's
capabilities beyond its tier default by adding explicit per-plugin elevation
in the plugin's `plugins:` config entry:

```yaml
plugins:
  - name: vendor-x-durable-workflow
    version: "1.2.0"
    trust_level:
      required_minimum: Community
    elevate_extension_points:
      - WorkflowOrchestrator  # required to allow Community-tier plugin to
                              # implement this Protocol
```

Elevation is **per-plugin and per-extension-point** — an operator cannot
broadly elevate "all Community plugins to all extension points." Elevation
is:

- **Recorded** in the load manifest exposed via ADR Plugin Trust Model §8
  `GET /plugins` endpoint (e.g., `effective_extension_points: [AuditHook,
  WorkflowOrchestrator]` with `elevated: [WorkflowOrchestrator]`).
- **Audited** to the PluginAudit stream at startup
  (`plugin_capability_elevated` event) and at every invocation of the
  elevated extension point (Decision Audit `elevated_capability` flag where
  the elevated extension point participated in the decision chain).
- **Required to be reviewed** in compliance attestations: the existence of
  an elevated extension point is a documented operator decision and must be
  defensible to auditors.

A future v2+ amendment may introduce a formal elevation-approval workflow
(multi-operator sign-off, expiry, scoped time-bounded elevations,
revocation); v1 ships the basic mechanism only.

### 3. Local-tier runtime semantics

Local-tier plugins (operator-built, unsigned, manifest may declare `signed:
false`) trigger additional runtime semantics on top of §1 (no implicit
extension-point access) and §2 (operator must explicitly enumerate every
permitted extension point per plugin):

**Startup warning.** AGSignal core emits a prominent operator-visible
warning at every Local-tier plugin load:

```
WARNING: Loading Local-tier plugin <name> (unsigned, no Sigstore provenance).
Local-tier plugins bypass cryptographic provenance verification. Proceed
only if you trust your local installation chain. Permitted extension
points: [<list>]. To verify the plugin source and rebuild from a trusted
base, see docs/decisions/2026-05-08-plugin-trust-model.md.
```

The warning is also written to the PluginAudit stream as a
`local_tier_loaded` event and to the OPERATIONAL audit channel.

**Per-call audit flag.** Every Decision Audit + Approval Audit + Delivery
Audit entry whose extension-call chain includes a Local-tier plugin
carries a `local_tier_plugin_invoked: true` flag with the plugin name. The
flag enables post-incident forensic reconstruction:

- *"Did this decision flow through cryptographically attested code only?"*
  — query Decision Audit for `local_tier_plugin_invoked: false`.
- *"Which decisions in the last 30 days had Local-tier plugin involvement?"*
  — query Decision Audit for `local_tier_plugin_invoked: true`.

**Explicit acknowledge required.** Local-tier plugins MUST appear in the
operator's explicit `plugins:` config block AND each Local-tier plugin
entry MUST include `acknowledge_unsigned: true`:

```yaml
plugins:
  - name: internal-custom-audit-sink
    version: "0.3.0"
    trust_level:
      required_minimum: Local
    acknowledge_unsigned: true   # required for Local-tier loads
    elevate_extension_points:
      - AuditHook
```

AGSignal core refuses to load any Local-tier plugin missing the
`acknowledge_unsigned: true` flag. This is per-startup friction by design:
every Local-tier load is a deliberate operator decision.

### 4. Tier-promotion path

A plugin's trust tier is computed at load time per ADR Plugin Trust Model
§5 from the manifest, signature verification, and the AGSignal-curated
`publisher_identity` allowlist. **The tier is not a manifest field.**

Promoting a plugin from Community to Verified requires the AGSignal team to
add the plugin's `publisher_identity` (Sigstore-issued OIDC identity) to
the curated allowlist. **Operators cannot self-promote third-party
plugins.** This is intentional: the curated allowlist is the social-trust
component that complements cryptographic provenance — without it,
"Verified" would degenerate into "anyone with a working CI pipeline can
emit attestations."

Tier promotions ship via OSS releases (allowlist change is a tracked
change in the AGSignal repo). Operators may locally override the curated
allowlist in their `agsignal.yaml` if they want to upgrade a Community-
tier plugin to Verified-equivalent in their own deployment, but the upgrade
is operator-local and recorded in the load manifest as
`tier_locally_overridden: true`.

## Rejected

### Binary "loaded vs not loaded" with administrative-only tier grading

Re-rejecting the alternative ADR Plugin Trust Model §5 already considered,
now with explicit capability rationale. Without materially-different
default capabilities per tier, "Verified" and "Community" become marketing
labels rather than operational controls. Stage 2 research explicitly
identifies this as the failure mode of light-touch plugin trust models.

### Full capabilities for Verified tier (parity with First-Party)

Rejected. `OverrideAuthority` is the Plugin Trust Model's most-impactful
extension point. Verified-tier plugins have cryptographic provenance to a
known publisher but the AGSignal team does not warrant the publisher's
operational security posture. Requiring explicit operator elevation for
`OverrideAuthority` keeps the Verified-tier blast radius bounded by default
while preserving the elevation path for trusted commercial vendors (e.g.,
Break-Glass commercial plugin, which depends on JWS-Identity per PRD §6 and
ships First-Party).

### No capabilities for Community tier (zero default)

Rejected. `AuditHook` is the read-mostly side-effect-free extension point
per M9.A; permitting Community-tier plugins to implement audit destinations
(for custom observability backends, internal SIEMs, etc.) is the lowest-
risk extensibility surface. Locking Community plugins out of all extension
points by default would disincentivize the OSS ecosystem AGSignal aims to
grow, without proportionate security gain.

### Operator-broad elevation (`elevate_all: true`)

Rejected. Per-plugin per-extension-point elevation is intentional friction
— each elevation is a documented operator decision that auditors can
review. A blanket elevation switch reproduces the Casbin "trust model is
the host's problem" anti-pattern that Stage 2 research warns against.

### Local-tier auto-load with `acknowledge_unsigned` flag

Rejected. Auto-loading unsigned plugins by default reproduces the supply-
chain attack surface that PEP 740 + Sigstore was designed to mitigate.
Requiring explicit per-startup operator action to load Local-tier plugins
keeps the operational cost low while ensuring every Local-tier load is a
deliberate choice. The `acknowledge_unsigned: true` config-level flag is
the explicit-action requirement; no auto-load shortcut is provided.

### Local-tier without per-call `local_tier_plugin_invoked` audit flag

Rejected. Without the flag, post-incident forensics cannot distinguish
"decision flowed through First-Party crypto-attested chain" from "decision
flowed through operator-built local code with no provenance." The flag is
load-bearing for compliance attestation; regulators and auditors need to
identify decisions whose extension calls flowed through unsigned code.

## Consequences

**Enables:** Verified-tier and Community-tier plugins ship with materially-
different default capabilities, addressing Stage 2's "trust tiers must
change defaults" requirement. Compliance auditors can distinguish decisions
that flowed through cryptographically-attested-and-curated chains from
those that flowed through operator-elevated or Local-tier code. The OSS
plugin ecosystem gains a low-friction Community-tier on-ramp (`AuditHook`
only) without requiring AGSignal-team curation for every contributor.

**Constrains:** Commercial plugin vendors targeting Verified-tier with
non-`AuditHook` extension points (most plugins) must request
`publisher_identity` allowlist inclusion via the AGSignal team. Operators
deploying Community-tier plugins beyond `AuditHook` must explicitly elevate
per plugin and per extension point — friction by design. Local-tier plugin
operators carry documented per-call audit-flag overhead and explicit
acknowledgment burden.

**Operational implications:**

- The `GET /plugins` endpoint (per ADR Plugin Trust Model §8) gains
  `effective_extension_points`, `elevated_extension_points`, and
  `local_tier_plugin_invoked_count` fields.
- The PluginAudit stream gains `plugin_capability_elevated` and
  `local_tier_loaded` event types.
- The Decision Audit + Approval Audit + Delivery Audit envelopes gain a
  `local_tier_plugin_invoked: bool` flag, additive to v0.4 schema (per the
  amended DecisionRecord schema's "additive minor bumps allowed" rule).

**v2+ direction:** A formal elevation-approval workflow (multi-operator
sign-off, expiry, scoped time-bounded elevations, revocation) is queued as
a v2+ amendment. The v1 mechanism (operator config + audit-flag) is
sufficient for ADR Plugin Trust Model §M9.5's "MUST be resolved before
first commercial plugin ships" gate.

## References

- ADR Plugin Trust Model (`2026-05-08-plugin-trust-model.md`) — §5 four-tier
  grading and §8 load manifest exposure that this ADR builds on
- Stage 2 Plugin-trust research (Perplexity Deep Research, May 2026) —
  "trust tiers must materially change default capabilities, not just
  labels" finding from comparison against HashiCorp Terraform providers,
  OPA bundle signing, Kubernetes admission controllers, Backstage plugins,
  and PEP 740 / Sigstore production reality
- ADR Audit Ledger Physical Structure (`2026-05-08-audit-ledger-structure.md`)
  — PluginAudit stream definition and Decision/Approval/Delivery Audit
  envelopes that gain the `local_tier_plugin_invoked` flag
- ADR Approval Workflow Semantics (`2026-05-08-approval-workflow-semantics.md`)
  — `OverrideAuthority` impact analysis; informs §1 tier-default rationale
- ADR Extension API Surface (`2026-05-08-extension-api-surface.md`) —
  multiplicity rules per Protocol that compose with elevation mechanics
