> Historical provenance. Superseded by the current UNS product contract in `docs/PRODUCT.md`. Implementation and market claims below are not current acceptance evidence.

# Plugin Trust Model

Date: 2026-05-08

Updated: 2026-05-08 — Inline tightenings per Stage 2 plugin-trust research
(Perplexity Deep Research on OSS plugin ecosystem precedents). Four
amendments: (PATCH-L) explicit fail-closed escalation path for undeclared
capabilities under §2; (PATCH-M) sandboxing reframed as expected maturation
for sensitive-resource plugins, not reactive-only triggers, under §3;
(PATCH-N) explicit risk-acceptance language for v1 same-process trust under
§3; (PATCH-P) tightened framing of PEP 740 + Sigstore as supply-chain
provenance signal distinct from runtime trust enforcement under §1. Companion
follow-up ADR (`2026-05-08-plugin-tier-default-capabilities.md`, ADR-005a)
specifies per-tier default capability matrix that this ADR's §5 commits to
graded administrative visibility but did not initially lock at the runtime-
capability level.

Status: Accepted

Linear: TBD

## Context

PRD §M9 defines UNS's plugin ecosystem (3 Protocols + 1 hook per §M8) and
locks four design principles (read-mostly, idempotent, side-effect-free except
logging, propagate `correlation_id`/`decision_id`) as a contractual constraint
enforced at code review. PRD §M9.5 records that the formal Plugin Trust Model —
sandboxing, capability scoping, signing, version pinning, third-party policy —
is ADR-pending and **MUST be resolved before the first commercial plugin ships**
(§6: JWS-Identity, SPIFFE-Auth, Merkle-Audit, Break-Glass, DurableWorkflow,
Compliance Templates, Enterprise Dashboards). PRD §12.4 lists this gap as a High
risk; until resolved, OSS core ships explicit-registration-only loading.

Stage 2 production-pattern research (`stage2-pre-vs-post-execution.md`) flags
the **governance-as-data-plane-dependency** anti-pattern: when control logic
shares operational fate with the workload it supervises, both enforcement
quality and resilience can fail at once. UNS's pre-execution-only stance
(PRD §1.2.4) already mitigates the wire-speed variant, but the same anti-pattern
recurs at the plugin seam: a misbehaving plugin must not turn a governance
decision into a workload outage. ADR-008 (fail-mode semantics) covers engine
failure; this ADR covers the analogous plugin-failure surface.

Stage 2 production-pattern matrix research notes OPA's bundle-signing model as
the strongest documented control-plane signing precedent and Casbin's lack of a
trust model as the canonical "deceptively simple, fragments at scale" warning.
This ADR adopts an OPA-shaped signing baseline and an explicit-registration
discovery model so that the v2+ commercial-plugin marketplace inherits a
deterministic trust contract rather than retrofitting one.

## Decision

### 1. Plugin signing

**Required for commercial plugins; recommended for OSS-distributed plugins; not
required for operator-built local plugins.** UNS core verifies signatures
when a manifest declares `signed: true`; unsigned plugins are loadable in v1
provided they appear in the explicit registration list (§8) and the operator
opts in. Mixing signed and unsigned plugins is permitted but every plugin's
trust level (§5) is recorded in the load manifest exposed to administrators.

**Cryptographic scheme: Sigstore + PEP 740 attestations** for any plugin
distributed via PyPI (the canonical commercial channel). PEP 740 binds a
package distribution to its provenance via Sigstore-issued attestations and is
generally available on PyPI as of late 2024; GitHub Actions Trusted Publishing
emits attestations by default with no key management. UNS core verifies
the attestation's Sigstore bundle, the distribution's SHA-256 digest, and that
the publisher identity matches the manifest's declared `publisher_identity`
(§4). For non-PyPI distribution channels (private artifact registries,
air-gapped operator builds), the same Sigstore bundle + in-toto attestation
shape is accepted; GPG and bare wheel signatures are explicitly rejected as
weaker (PEP 740 itself documents that wheel-embedded signatures are deprecated
upstream as of 2018).

**Verification timing: install-time (operator tooling) AND load-time (UNS
core, defense in depth).** UNS does not implement an installer; operators
use `pip` or equivalent and may run `python -m pypi_attestations verify pypi`
as part of their deployment pipeline. UNS core re-verifies on every plugin
load against the manifest's recorded digest and attestation bundle reference.
Re-verification at load is bounded (target < 100 ms per plugin) and cached for
the lifetime of the process keyed by `(plugin_name, version, digest)`.

**Signing authority: plugin-author keys with attestation, with First-Party
designation reserved for UNS-team-published plugins.** UNS team does
not act as a third-party CA; the Sigstore transparency log is the trust root.
The "UNS-Verified" trust level (§5) is administrative — the UNS team
publishes a curated allowlist of `publisher_identity` strings (e.g., the
GitHub OIDC identity of a vetted commercial vendor) — not cryptographic.
Allowlist updates ship via OSS releases; operators can override locally.

**PATCH-P (2026-05-08): supply-chain provenance vs runtime trust framing.**
PEP 740 + Sigstore is **a supply-chain provenance signal**: it proves a
distribution artifact came from a specific publisher identity through a
specific build pipeline at a specific time. **It is not a complete runtime
trust model.** Trail of Bits explicitly notes that PEP 740 governs the
*index*'s handling of attestations and does not mandate or define how
installers verify them at runtime; the consuming toolchain is responsible
for runtime enforcement. UNS's runtime trust enforcement is the
combination of (a) load-time signature verification (this section), (b)
manifest-declared capability scoping with runtime enforcement (§2), (c)
trust-tier-graded default capabilities (§5 + ADR-005a), (d) failure
isolation per §6, and (e) the v2+ sandboxing maturation path per §3.
Conflating "the package is Sigstore-attested" with "the plugin is safe to
load with full host privileges" is the documented failure mode in
ecosystems with weaker runtime enforcement (e.g., npm supply-chain
incidents where compromised developer credentials produced legitimately-
signed but malicious packages). UNS treats provenance and runtime
enforcement as complementary layers, not interchangeable substitutes.

### 2. Capability scoping (declared, runtime-enforced)

**Plugins declare extension points in the manifest; UNS core enforces the
scope at runtime.** Manifest declares `extension_points: [AuditHook]`; UNS
core registers the plugin only against the declared interfaces and refuses
to call any other Protocol or hook on that plugin instance — even if the
plugin's Python class technically implements additional methods. Violation at
load time (manifest declares an extension point the plugin object does not
satisfy) is a hard refusal; violation at runtime (host code attempts to invoke
an undeclared extension on the plugin) raises `PluginCapabilityViolation` and
disables the plugin per §6.

This is a **registration-layer** enforcement, not a sandbox. Within a declared
extension point, the plugin runs with full host privileges (same process, same
imports, same memory). Capability scoping prevents accidental coupling and
provides a documented capability surface for administrative enumeration (PRD
§M9.5 AC); it does not prevent a malicious plugin from `import os` and erasing
the disk. That class of threat is addressed by signing (§1), trust levels (§5),
and the v2+ sandboxing direction (§3).

**PATCH-L (2026-05-08): explicit fail-closed escalation path for undeclared
capabilities.** When a plugin needs a capability it did not declare in its
manifest at v0.0 — e.g., a `Verified`-tier plugin originally declaring only
`AuditHook` later wants to implement `WorkflowOrchestrator` — UNS core
**fails closed**. The escalation path is:

1. **Plugin author updates the manifest** (`extension_points.implements`),
   bumps the plugin's SemVer, re-signs the distribution (Sigstore +
   attestation), and republishes through the same channel.
2. **Operator updates the registered version** in `uns.yaml` to the new
   plugin version. UNS core re-validates manifest + signature on next
   load.
3. **UNS core records** the capability change in the PluginAudit stream
   (`plugin_capability_changed` event) so administrators see the diff.

**Silent escalation is forbidden.** UNS core MUST NOT auto-grant a
plugin a capability beyond its declared scope, even if (a) the plugin's
underlying class exposes the method, (b) the operator has the plugin
loaded at the appropriate trust tier, or (c) other plugins of the same
trust tier have the capability elevated. The principle: every capability
is a documented operator decision, not a side effect of class
introspection or trust-tier inheritance.

**Dev-only override.** A development-mode flag (`UNS_DEV_PLUGIN_ESCALATION=1`,
documented as **never to be set in production**) allows an operator to
elevate a plugin's runtime capabilities without manifest update + re-sign.
The flag emits a startup-time critical-severity warning, writes a
`dev_escalation_active` event to the PluginAudit stream, and rejects any
SAFETY-intent decision flowing through an escalated extension point. The
flag is intended for plugin author iteration cycles; production deployments
that detect the flag in their config MUST treat it as a deployment
configuration error.

### 3. Sandboxing (v1: none for capability-constrained plugins; v2+ maturation for sensitive-resource plugins)

**v1 OSS: same-process, same-Python-interpreter plugin loading for plugins
operating within tightly-bounded capability scopes** (e.g., AuditHook
write-only-to-audit, IdentityProvider deterministic-resolution). No subprocess
isolation, no capability-restricted interpreter, no seccomp/restricted-import.
Operators load plugins they explicitly trust; signing + trust levels surface
that trust to administrators; the contractual M9.A design principles plus
capability scoping (§2 + §2 PATCH-L) are the runtime enforcement layer.

**PATCH-N (2026-05-08): explicit risk-acceptance language for v1 same-process
trust.** v1 same-process loading is a **deliberate risk acceptance** suitable
for OSS development and non-regulated deployments. Production deployments
that handle sensitive data, secrets, or network egress through plugins
should treat sandboxing as a **roadmap requirement, not optional hardening**.
The Stage 2 plugin-trust research is unambiguous on this point: capability
+ distribution + provenance controls are not sufficient once code is in-
process and extensible — a compromised plugin with same-process privileges
can still exfiltrate secrets or tamper with decisions. UNS v1 operators
running in regulated environments should plan for v2 sandboxing migration
as a deployment requirement, not a future luxury.

**Rationale for v1 non-isolation:** Stage 2 research validates that pre-
execution governance succeeds when the control plane is simple and reliable;
forcing subprocess IPC into every plugin call would amplify the
governance-as-data-plane-dependency anti-pattern by adding a process boundary
on the hot path of `evaluate()`. The OSS core's target audience (non-
regulated deployments and capability-constrained plugins like AuditHook)
does not justify the latency and operational cost of v1 sandboxing.

**PATCH-M (2026-05-08): sandboxing reframed as expected maturation for
sensitive-resource plugin classes.** v2+ sandboxing is **not a reactive-only
trigger** (waiting for a security incident or regulated customer demand to
force the question). It is the **expected maturation path for any plugin
class that touches network, file system, or secrets** as a normal part of
its operation. Specifically:

- **Plugins that handle secrets or identity material** (e.g., commercial
  JWS-Identity, SPIFFE-Auth, Break-Glass) — sandboxing migration is on the
  v2+ roadmap by design, not pending an incident. Same-process loading of
  these plugin classes is acceptable in v1 because the OSS-default
  IdentityProvider hook is HMAC-with-shared-secret (low blast radius if
  compromised); when commercial identity plugins ship, the v2+ subprocess-
  per-plugin model is the documented production stance.
- **Plugins that make network calls** (e.g., commercial Compliance Templates
  emitting to external regulators, Enterprise Dashboards exporting to multi-
  tenant SaaS, Stack Bridge plugins emitting to Defender / CloudTrail /
  Cloud Audit Logs) — sandboxing migration is similarly v2+ by design.
- **Plugins that touch local file system beyond audit-stream writes** —
  same.

**v2+ sandboxing triggers (any one accelerates the migration):** stronger
isolation moves from "v2+ planned" to "v2+ required" when **any** of the
following occurs:

- A regulated customer (FINRA / DORA / EU AI Act high-risk system / equivalent)
  contractually requires plugin-level fault isolation as part of their
  compliance attestation.
- UNS opens a third-party plugin marketplace (loading plugins from
  publishers outside the operator's trust boundary becomes the default
  workflow rather than an exception).
- A documented security incident traces to an in-process plugin compromising
  the host.

The likely v2+ shape is **subprocess-per-plugin with structured IPC** (msgpack
or gRPC), modeled on OPA's bundle / engine separation pattern. This ADR does
not pre-specify v2+ further; the maturation framing + trigger conditions are
sufficient to ensure (a) the question is reopened at the right time and (b)
plugin authors targeting sensitive-resource use cases plan for the migration
from v0.0 rather than treating it as an unanticipated requirement.

### 4. Plugin manifest

**Format: TOML, in a top-level `uns_plugin.toml` file at the package
root.** TOML is the Python-package-metadata standard (`pyproject.toml`
precedent), parseable without a runtime YAML dependency, and avoids the
ambiguity that mixed YAML/JSON manifests introduce. Manifest is authoritative
for UNS load decisions; setuptools/poetry metadata is informational only.

**Minimum manifest fields:**

```toml
[plugin]
name = "uns-jws-identity"        # globally unique; reverse-DNS allowed
version = "1.2.0"                     # SemVer; matches distribution version
description = "JWS-signed approval identity provider"
vendor = "Example Compliance Vendor"  # human-readable, optional

[plugin.compatibility]
uns_core = ">=1.0.0,<2.0.0"      # PEP 440 specifier; see §7
schema_version = "1"                  # manifest schema, separate from plugin SemVer

[plugin.extension_points]
# declared extension points — UNS enforces this scope at runtime (§2)
implements = ["IdentityProvider"]

[plugin.signing]
signed = true                         # if true, UNS verifies on load (§1)
publisher_identity = "https://github.com/example-vendor/uns-jws-identity/.github/workflows/release.yml@refs/tags/v1.2.0"
attestation_url = "https://pypi.org/.../provenance"

[plugin.host_capabilities]
# what the plugin needs from the host; documentation today, enforcement-hook
# for future capability-restricted interpreters
requires = ["audit_write", "identity_session_key_read"]
```

The `host_capabilities.requires` list is documentation-only in v1 (no runtime
permission system exists to honor it) but is required syntactically so that
v2+ can introduce enforcement without a manifest schema bump.

### 5. Trust levels (four tiers)

```
First-Party    : UNS-team-published; Sigstore identity matches the
                 UNS organization. Highest implicit trust.
Verified       : Third-party; Sigstore-signed AND publisher_identity matches
                 the UNS-curated allowlist (§1). Cryptographic chain to
                 a known publisher.
Community      : Third-party; Sigstore-signed but publisher_identity NOT in
                 the allowlist. Cryptographic chain to an unknown publisher.
Local          : Operator-installed; signed: false in manifest. Trust derives
                 entirely from operator's local control.
```

Trust level is **computed** at load time from the manifest, signature
verification result, and the curated allowlist; it is not a manifest field.
UNS core records the computed trust level in the load manifest (§8.3) and
in any audit entry the plugin participates in. The level is binary in failure
behavior — a plugin either loads or it does not — but **administrative
visibility is graded** (PRD §M9.5 AC: administrators can enumerate which
plugins are loaded, what they implement, and the effective trust scope of
each).

A simpler binary "loaded vs not loaded" model is rejected as failing the
administrative-enumeration AC: regulated operators need to demonstrate to
auditors that they ran only First-Party / Verified plugins, which requires the
distinction to be observable.

### 6. Failure isolation

**On unhandled plugin exception, idempotency violation detected at runtime, or
M9.A principle violation: UNS disables the failing plugin for the rest of
the process lifetime, continues with other plugins, and emits a fail-mode
audit entry.** This converts a plugin failure into a degraded-but-running
control plane rather than a halt; degradation is observable.

Specifics:

- **Unhandled exception in a plugin extension call**: caller catches it at the
  Protocol/hook invocation boundary, logs with full context, marks the plugin
  `DISABLED` for the process lifetime, and continues. The host operation that
  invoked the plugin proceeds per ADR-008 fail-mode semantics — the plugin
  failure feeds into `evaluate()`'s fail-mode pipeline as
  `engine_failure_attribute_source` (when an `IdentityProvider` plugin fails)
  or as a degraded `AuditHook` write (when an audit destination fails).
- **Idempotency violation (M9.2)**: same key/payload yielded different
  results across invocations. Detected by `AuditHook` differential checks
  when feasible; treated identically to an unhandled exception.
- **Capability scope violation (§2)**: hard refusal at load; if it surfaces
  at runtime, plugin is disabled identically.
- **Surface**: Plugin failures produce **a Decision Audit fail_mode entry per
  ADR-008** (the plugin failure is a category of engine failure when it
  participates in `evaluate()`) PLUS **a separate `PluginAudit` stream entry**
  recording the plugin lifecycle event (`loaded`, `disabled`, `verification_failed`,
  `capability_violation`). The PluginAudit stream is a fourth stream beyond
  the three M6 audit streams; it records plugin operational events distinct
  from the decision/approval/delivery surfaces. An OPERATIONAL notification
  with `dedup_key = plugin_disabled:<plugin_name>` is emitted per ADR-008's
  notification contract.

The "halt entirely" alternative is rejected as the data-plane-dependency
anti-pattern: a plugin bug must not take down the control plane. The "continue
silently with the failing plugin" alternative is rejected as masking failures
(coding-principles fail-fast guidance).

### 7. Version compatibility

**Plugins declare `uns_core` compatibility as a PEP 440 specifier;
UNS core hard-refuses to load plugins outside the declared range.**
A plugin's `[plugin.compatibility].uns_core = ">=1.0.0,<2.0.0"` reflects
the plugin author's tested range; if the running core is outside this range,
UNS logs the mismatch, emits an OPERATIONAL notification, and skips the
plugin. No "warn and load" mode in v1 — silent ABI mismatches are the most
common third-party-plugin failure mode in long-running ecosystems.

**Compatibility windows:** UNS core commits to maintaining ABI stability
across minor versions within a major release (SemVer guarantee). A plugin
declaring `>=1.0.0,<2.0.0` runs on every 1.x core. Major-version transitions
require an explicit plugin-side update; compatibility-shim plugins (a 2.x
plugin declaring `>=1.5.0,<3.0.0` because it uses no 2.x-only features) are
permitted but the burden is on the plugin author.

**`schema_version` (manifest schema) is separate from plugin SemVer and from
core SemVer.** Manifest schema bumps are UNS-core release events; any
`schema_version` mismatch is a hard refusal. v1 manifest schema is `"1"`.

### 8. Discovery and loading workflow

**End-to-end operator workflow:**

```
Step 1 : Install
         pip install uns-jws-identity==1.2.0
         (or equivalent: poetry, uv, private artifact registry, vendored
         wheel in _UNS/plugins/, operator-built local wheel)

Step 2 : Register
         Operator adds the plugin to UNS config (YAML):
         plugins:
           - name: uns-jws-identity
             version: "1.2.0"
             trust_level: required_minimum: Verified
         No auto-discovery via Python entry points or plugin directory scan
         (PRD §M9.5 v1 constraint). Explicit registration is the only load
         path until ADR-005 trust model maturity supports auto-discovery.

Step 3 : Validate at startup
         UNS core, on startup:
         (a) loads the plugin's manifest (uns_plugin.toml)
         (b) verifies signature per §1 if signed: true
         (c) computes trust level per §5 and rejects if below the operator's
             required_minimum
         (d) checks PEP 440 compatibility per §7
         (e) confirms declared extension points are implementable by the
             loaded class (capability scope check, §2)
         Failure at any sub-step: plugin not loaded, OPERATIONAL notification
         emitted, UNS core continues without the plugin (per §6 isolation).

Step 4 : Lifecycle init (per ADR-004 plugin lifecycle hooks)
         UNS calls plugin.init() with a host-capabilities-restricted
         context. Plugin registers itself against its declared extension
         points only. (Exact init/load/teardown signatures: ADR-004.)

Step 5 : Runtime invocation
         UNS core invokes the plugin only via its declared extension
         points (§2 enforcement). Every invocation propagates correlation_id
         and decision_id (M9.4). Failures route through §6.
```

**Auto-discovery (Python entry points, plugin-directory scan) is explicitly
deferred to v2+** and is one of the marketplace triggers that revisits §3
sandboxing. Until then, the operator's config file is the authoritative
plugin set.

**Load manifest exposure (PRD §M9.5 AC).** UNS core exposes a read-only
endpoint `GET /plugins` returning, for each loaded plugin: `name`, `version`,
`extension_points`, `trust_level`, `signed`, `publisher_identity` (when
applicable), `state` (`LOADED` | `DISABLED`), and `last_state_change`.
Administrators query this endpoint for compliance enumeration; the same data
is included in periodic snapshots written to the PluginAudit stream.

## Rejected

- **Full sandboxing in v1 (subprocess per plugin, capability-restricted
  interpreter).** Adds non-trivial latency to every governance hot-path
  invocation and amplifies the governance-as-data-plane-dependency anti-
  pattern by introducing an IPC boundary in `evaluate()`. Stage 2 research
  consistently identifies "simple control plane" as the strongest production
  pattern for the OSS-core target audience. Triggers in §3 reopen the
  question; v1 does not pre-pay the cost.
- **No signing requirement for any plugin.** Casbin's "trust model is the
  host's problem" stance is the documented warning case from Stage 2 matrix
  research; shipping a commercial plugin ecosystem without a signing baseline
  reproduces the same fragmentation. PEP 740 + Sigstore is mature enough in
  2026 that mandating it costs commercial vendors little.
- **Auto-discovery via Python entry points or plugin directory scan in v1.**
  PRD §M9.5 explicitly defers this. Auto-discovery without a trust model is a
  documented supply-chain attack vector; with a trust model, it remains a
  marketplace-shaped problem rather than an OSS-core-shaped one.
- **Plugin marketplace in v1.** A marketplace requires curated review, takedown
  workflow, vulnerability disclosure process, and revocation mechanics — none
  of which the OSS core can host without an organizational commitment well
  beyond v1 scope. Marketplace launch is a §3 sandboxing trigger.
- **GPG / bare wheel signatures as the signing scheme.** Wheel-embedded
  signatures are deprecated upstream as of 2018; GPG plus PyPI provides no
  index-side verifiability. PEP 740 is the stronger 2026-current option.
- **UNS team as third-party CA.** Centralizes trust on a single
  organization, creates a revocation/key-rotation burden the OSS project is
  not staffed for, and reproduces the failure mode that Sigstore's keyless
  identity model was designed to eliminate.
- **Binary "loaded vs not loaded" trust model.** Fails the §M9.5 AC for
  administrative enumeration; auditors of regulated deployments need
  documented graded trust to demonstrate plugin curation discipline.

## Consequences

**Enables:** Commercial-plugin shipping is unblocked. JWS-Identity, SPIFFE-
Auth, Merkle-Audit, Break-Glass, DurableWorkflow, Compliance Templates, and
Enterprise Dashboards (§6) can ship against a documented trust contract.
Operators have a deterministic install / register / verify workflow.
Administrators can enumerate plugins and trust levels for compliance evidence.
Plugin failures degrade gracefully (per §6) instead of taking down the control
plane.

**Constrains:** Commercial plugin authors MUST publish via Trusted Publishing
(or equivalent Sigstore-emitting CI) to qualify for the Verified trust level;
manual unsigned uploads ship as Community. Operators MUST maintain explicit
plugin registration in config; auto-discovery is not available in v1.
UNS core gains a PluginAudit stream and a `GET /plugins` surface; both
are additive to v1 scope but require schema and HTTP-API space.

**Operator-side workflow:**

1. Operator selects plugin and trust-level minimum.
2. Operator installs via `pip` (or equivalent) — SBOM and provenance
   verification at install time recommended but not enforced by UNS.
3. Operator adds plugin to `plugins:` config block with required minimum
   trust level.
4. UNS core validates at startup; failures surface as OPERATIONAL
   notifications without halting the platform.
5. Operator monitors PluginAudit stream and `GET /plugins` for state changes.

**v2+ direction:**

- **Stronger isolation (§3 triggers)**: subprocess-per-plugin or capability-
  restricted interpreter, modeled on OPA bundle / engine separation.
- **Auto-discovery + marketplace**: when sandboxing lands, entry-point
  discovery and a curated marketplace become viable; until then, explicit
  registration remains the contract.
- **Capability-restricted host context** (§4 `host_capabilities.requires`):
  manifest's `requires` list becomes a runtime permission system rather than
  documentation; revisit when sandboxing introduces an enforcement layer.

## References

- [PEP 740 - Index support for digital attestations](https://peps.python.org/pep-0740/) - canonical Sigstore-on-PyPI specification adopted by UNS as the commercial-plugin signing baseline
- [PyPI's Sigstore-powered attestations are now generally available - Sigstore Blog](https://blog.sigstore.dev/pypi-attestations-ga/) - GA announcement establishing PEP 740 readiness for production use
- [Attestations: A new generation of signatures on PyPI - Trail of Bits](https://blog.trailofbits.com/2024/11/14/attestations-a-new-generation-of-signatures-on-pypi/) - implementation rationale and threat model that informs §1 verification choices
- [pypi-attestations library](https://github.com/pypi/pypi-attestations) - reference implementation for signature verification; UNS core's load-time check uses the public Python API
- [OPA bundle signing](https://www.openpolicyagent.org/docs/latest/management-bundles/) - control-plane signing precedent; informs the "verify on load, cache by digest" pattern in §1
- ADR-001 (Approval Workflow Semantics) — referenced for callback-signing
  precedent and the plugin-contract stability framing
- ADR-008 (Fail-mode Semantics) — referenced for the plugin-failure routing
  through `engine_failure_attribute_source` and the OPERATIONAL notification
  shape in §6
- ADR-004 (Extension API surface) — defines the exact Protocol/hook lifecycle
  hooks (`load`/`init`/`teardown`) referenced in §8 Step 4; runs in parallel
  with this ADR
- Stage 2 production-pattern matrix (`docs/internal/superpowers/specs/2026-05-08-stage2-production-pattern-matrix.md`) - OPA bundle-signing precedent and Casbin trust-model warning case
- Stage 2 pre-vs-post-execution analysis (`docs/internal/superpowers/specs/2026-05-08-stage2-pre-vs-post-execution.md`) - governance-as-data-plane-dependency anti-pattern that motivates §6 failure isolation
