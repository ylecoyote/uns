# MIP-254A Policy Lifecycle Runtime Boundary Design

Date: 2026-05-06

Linear: [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package)

## Scope

This slice ports the first reusable MIP policy-engine guarantee into AGSignal:
runtime enforcement must load only explicitly ACTIVE policy configs.

It does not port the full MIP policy package yet. Delta, shadow-result storage,
guard evaluation, and generic policy envelopes remain later MIP-254 slices.

## Donor Parity Checkpoint

| Donor behavior | AGSignal decision |
|---|---|
| `repository.py` loads the current `ACTIVE` config for enforcement | Add `SQLAlchemyPolicyStore.load_runtime_registry()` that filters to `ACTIVE` only |
| `schemas.py` treats `DRAFT`, `PREVIEW`, `ACTIVE`, and `RETIRED` as lifecycle states | Add lifecycle helper properties on `NotificationPolicy` |
| `PREVIEW` is shadow-only and must not silently affect live enforcement | Add `SQLAlchemyPolicyStore.load_shadow_registry()` for explicit PREVIEW-only loading |
| UI edits are not enforcement | DRAFT and RETIRED remain excluded from runtime and shadow registry loads |
| MIP uses trading-specific `PolicyName` and payload schemas | Excluded from this slice; AGSignal keeps domain-neutral notification policy models |

## Implemented Behavior

- `NotificationPolicy.is_runtime_enforced` is true only for `PolicyStatus.ACTIVE`.
- `NotificationPolicy.is_shadow_evaluated` is true only for `PolicyStatus.PREVIEW`.
- `NotificationPolicy.is_editable` is true only for `PolicyStatus.DRAFT`.
- `NotificationPolicy.is_terminal` is true only for `PolicyStatus.RETIRED`.
- `SQLAlchemyPolicyStore.load_runtime_registry()` loads ACTIVE policies only.
- `SQLAlchemyPolicyStore.load_shadow_registry()` loads PREVIEW policies only.

`SQLAlchemyPolicyStore.load_registry()` remains backward compatible and still
defaults to loading PREVIEW plus ACTIVE policies, with ACTIVE winning if both
exist for a notification type.

## Verification

- `pytest tests/db/test_policy_store.py tests/notification/test_policies.py -q`

## Remaining MIP-254 Work

- AGSignal-neutral delta state model with transition history.
- Shadow evaluation result and aggregate models.
- Guard result models and explicit approval gates.
- Policy config envelope or equivalent hash-bearing evaluation record.
- Repository/API surface for lifecycle transitions beyond save/load helpers.
