# MIP-254B Policy Delta Core Design

Date: 2026-05-06

Linear: [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package)

## Scope

This slice ports the MIP policy-delta lifecycle into AGSignal as
domain-neutral learning primitives.

It does not add database persistence or policy application. Those remain later
MIP-254 slices after the in-memory state contract is stable.

## Donor Parity Checkpoint

| Donor behavior | AGSignal decision |
|---|---|
| `learning_schemas.py` defines `DeltaState`: `PROPOSED -> SHADOW -> APPROVED -> APPLIED`, with `REJECTED` terminal | Ported as `DeltaState` and `PolicyDelta.VALID_TRANSITIONS` |
| Deltas are immutable once `APPLIED` or `REJECTED` | Ported through frozen Pydantic models plus transition-by-copy; terminal states have no outgoing transitions |
| Every delta tracks its full state transition history | Ported as append-only `transition_history` entries on every `transition_to()` call |
| Guard stages are explicit | Ported as `GuardStage`; stored on transition history entries |
| MIP policy payloads and ATP table names are trading-specific | Excluded; `policy_type`, `field_path`, and values are domain-neutral |

## Implemented Behavior

- `PolicyDelta` starts in `PROPOSED`.
- `PolicyDelta.can_transition_to()` exposes allowed next states.
- `PolicyDelta.transition_to()` validates transitions and raises on invalid moves.
- `PolicyDelta.transition_to()` returns a new immutable copy, leaving the source unchanged.
- Each transition appends `PolicyDeltaTransition` with actor, reason, guard stage, and timestamp.
- Approval, rejection, shadow evaluation, and apply metadata are recorded on the returned copy.

## Verification

- `pytest tests/notification/test_policy_learning.py -q`

## Remaining MIP-254 Work

- Persistent delta repository and transition-history storage.
- Shadow evaluation result and aggregate models.
- Guard result models and approval preconditions.
- Policy-envelope/evaluation hash records.
- Wiring deltas into policy application and rollout.
