# MIP-254E Policy Config Envelope Design

Date: 2026-05-06

Linear: [MIP-254](https://linear.app/awiley-personal/issue/MIP-254/port-mip-policy-engine-concepts-into-agsignal-native-policy-package)

## Scope

This slice ports the MIP policy config envelope and evaluation-hash concepts
into AGSignal-neutral models.

It does not introduce MIP policy names, trading payload schemas, or admin/API
routes. It gives AGSignal the reusable primitives needed to produce versioned
configs from approved deltas and record which exact config hash was evaluated.

## Donor Parity Checkpoint

| Donor behavior | AGSignal decision |
|---|---|
| `schemas.py` computes a stable SHA-256 hash from canonical config JSON | Ported as `compute_config_hash()` and `canonical_config_json()` |
| `PolicyConfigEnvelope` wraps config payloads with lifecycle/version/hash metadata | Ported as AGSignal-neutral `PolicyConfigEnvelope` with `policy_type` instead of MIP `PolicyName` |
| Evaluation logs record the exact config hash used | Ported as `PolicyEvaluationRecord.from_envelope()` |
| Approved deltas create new policy config versions | Ported as `apply_policy_delta()`, producing the next DRAFT envelope from an APPROVED delta |
| MIP typed wrappers parse trading-specific config payloads | Excluded; AGSignal keeps `config_json` generic and host/domain typed wrappers can live outside Core |

## Implemented Behavior

- Config hashes are stable for equivalent dictionary ordering.
- Envelopes are immutable and compute missing hashes automatically.
- Applying a delta requires `DeltaState.APPROVED`.
- Applying a delta requires matching `policy_type`.
- Applying a delta deep-copies config JSON and returns a new DRAFT version.
- Evaluation records pin `policy_type`, `config_id`, and `config_hash`.

## Verification

- `pytest tests/notification/test_policy_config.py -q`

## Remaining MIP-254 Work

- Optional persistence for generic config envelopes/evaluation records.
- Admin/API lifecycle routes.
- Host-repo validation against MIP examples before marking MIP-254 done.
