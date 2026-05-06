# MIP-254D Policy Learning Store Design

Date: 2026-05-06

Linear: [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package)

## Scope

This slice ports the repository-level persistence semantics for AGSignal policy
learning primitives.

It intentionally remains a standalone sync SQLAlchemy store because AGSignal's
current DB stores use sync SQLAlchemy. The MIP donor repositories are async and
schema-qualified for the host platform; this slice adapts their behavior, not
their infrastructure.

## Donor Parity Checkpoint

| Donor behavior | AGSignal decision |
|---|---|
| `delta_repository.py` creates, fetches, lists, and transitions deltas | Ported as `SQLAlchemyPolicyLearningStore.create_delta`, `get_delta`, `list_deltas`, and `transition_delta` |
| Invalid delta transitions fail loudly | Ported; invalid transitions raise and leave persisted row unchanged |
| Terminal states are immutable through the state machine | Ported through `PolicyDelta.VALID_TRANSITIONS` and repository transition validation |
| Every mutation preserves transition history | Ported by storing append-only transition history JSON on `policy_deltas` |
| `shadow_repository.py` persists per-decision results and per-delta aggregate upserts | Ported as `persist_shadow_result`, `list_shadow_results`, `persist_shadow_aggregate`, and `get_shadow_aggregate` |
| Shadow must pass before approval | Ported at repository level: `APPROVED` transition requires a passing shadow aggregate |
| Donor tables live under the host `atp` schema | Excluded; AGSignal uses standalone tables with no donor schema dependency |

## Implemented Tables

- `policy_deltas`
- `policy_shadow_results`
- `policy_shadow_aggregates`

## Implemented Behavior

- Delta values and transition history round-trip through JSON.
- Shadow aggregate persistence is an upsert keyed by `delta_id`.
- Approved deltas can be listed oldest-first for later application.
- `APPROVED` transition is blocked until shadow status is `PASSED`, minimum sample is met, and threshold is met.

## Verification

- `pytest tests/db/test_policy_learning_store.py -q`

## Remaining MIP-254 Work

- Policy-envelope/evaluation hash records.
- Applying approved deltas into versioned policy configs.
- Admin/API lifecycle routes for propose, shadow, approve, reject, and apply.
- Host-repo validation against MIP real policy examples.
