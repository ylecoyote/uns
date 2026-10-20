# Notification policy lifecycle

DRAFT is editable proposal state; PREVIEW is shadow-only; ACTIVE is eligible for runtime; RETIRED is historical. The default PolicyRegistry rejects non-ACTIVE registration. SQL runtime/shadow loaders explicitly separate these roles.

Policies resolve notification routing, delivery mode, acknowledgment requirements, timeout and deduplication. Legacy explicit overrides have precedence over policy settings, then defaults. Accepted notifications snapshot their effective settings and record base policy identity, effective-settings hash, applied override values, evaluation ID and principal. Default routing has a versioned identity as well.

The YAML loader computes semantic hashes. SQL storage deduplicates identical content and links replaced versions. The reload route validates the entire candidate snapshot, persists it in one transaction, and swaps the runtime registry only after success. Reloads are serialized within one HTTP process. Multi-process operators reload each process deliberately; cross-process live registry broadcast is not implemented. Accepted work continues with its original resolved settings.

## Policy changes

PolicyDelta tracks PROPOSED -> SHADOW -> APPROVED -> APPLIED, with REJECTED terminal alternatives and attributed history. Proposal models are not an authorization boundary; use SQLAlchemyPolicyLearningStore for persisted transitions.

A proposed change binds to the baseline configuration hash/version. Shadow aggregates bind to that baseline and the exact candidate hash, identify their evaluator, and declare sample/quality criteria. Approval rejects missing, failing, or mismatched evidence. A blocking guard fails; configured required guards must be present and true. A configured numeric FieldBound enforces bounds and step size.

`apply_policy_delta` requires APPROVED state and matching baseline hash/version. It creates a new DRAFT with a new configuration hash; activation is a separate operation. External evaluators supply shadow measurements. These records do not constitute an autonomous learning or optimization loop.

The future action-policy DSL under `agsignal.governance` is experimental and does not participate in notification routing.

RETIRED versions remain terminal. Restoring an old configuration requires a new version identifier; reload rejects reactivation of an already retired semantic version and retains the current active snapshot.
