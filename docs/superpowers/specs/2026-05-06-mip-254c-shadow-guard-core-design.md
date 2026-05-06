# MIP-254C Shadow And Guard Core Design

Date: 2026-05-06

Linear: [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package)

## Scope

This slice ports the MIP shadow-evaluation and guard-result schema concepts into
AGSignal-neutral primitives.

It does not persist shadow results or enforce guard decisions in a repository
yet. Those belong with the remaining repository/API slice.

## Donor Parity Checkpoint

| Donor behavior | AGSignal decision |
|---|---|
| `learning_schemas.py` records per-decision shadow outcomes | Ported as `ShadowEvaluationResult` with original and candidate outcomes |
| Shadow aggregate must pass before approval | Ported as `ShadowEvaluationAggregate.can_promote_to_approval` |
| Guards are explicit and auditable | Ported as `GuardResult` with stage, checks, structured reason, and timestamp |
| Bounds guard rejects out-of-range or over-large changes | Ported as `FieldBound.allows()` for numeric policy fields |
| MIP uses trading snapshots, tickers, and basis-point payload fields | Excluded; AGSignal uses domain-neutral decision IDs, outcome dictionaries, and improvement scores |

## Implemented Behavior

- `ShadowEvaluationResult` preserves original and candidate outcomes for a host decision.
- `ShadowEvaluationAggregate` records sample counts, win rate, thresholds, and status.
- `ShadowEvaluationAggregate.can_promote_to_approval` requires `PASSED`, minimum sample, and threshold flags.
- `GuardResult` records blocking or allowing guard decisions with structured reasons.
- `FieldBound` validates min/max, absolute step size, and relative step size for numeric fields.

## Verification

- `pytest tests/notification/test_policy_learning.py -q`

## Remaining MIP-254 Work

- SQLAlchemy-backed delta/shadow repositories.
- Repository-level guard enforcement before approval/apply.
- Policy-envelope/evaluation hash records.
- API/admin surface for proposing, shadowing, approving, rejecting, and applying deltas.
