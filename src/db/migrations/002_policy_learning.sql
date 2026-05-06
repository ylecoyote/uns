-- AGSignal policy learning persistence.
-- Standalone schema; intentionally no donor schema dependency.

CREATE TABLE IF NOT EXISTS policy_deltas (
    delta_id UUID PRIMARY KEY,
    policy_type VARCHAR(255) NOT NULL,
    field_path VARCHAR(512) NOT NULL,
    current_value JSON NOT NULL,
    proposed_value JSON NOT NULL,
    reasoning TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    state VARCHAR(50) NOT NULL DEFAULT 'PROPOSED',
    transition_history JSON NOT NULL DEFAULT '[]',
    shadow_evaluation_id UUID,
    proposed_by VARCHAR(255) NOT NULL DEFAULT 'policy_learning',
    approved_by VARCHAR(255),
    rejected_by VARCHAR(255),
    rejection_reason VARCHAR(255),
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (state IN ('PROPOSED', 'SHADOW', 'APPROVED', 'REJECTED', 'APPLIED'))
);

CREATE INDEX IF NOT EXISTS ix_policy_delta_type_state
    ON policy_deltas(policy_type, state);

CREATE INDEX IF NOT EXISTS ix_policy_deltas_state
    ON policy_deltas(state);

CREATE TABLE IF NOT EXISTS policy_shadow_results (
    result_id UUID PRIMARY KEY,
    delta_id UUID NOT NULL REFERENCES policy_deltas(delta_id),
    decision_id VARCHAR(255) NOT NULL,
    original_outcome JSON NOT NULL,
    shadow_outcome JSON NOT NULL,
    changed BOOLEAN NOT NULL DEFAULT FALSE,
    improvement_score DOUBLE PRECISION,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_policy_shadow_results_delta_id
    ON policy_shadow_results(delta_id);

CREATE INDEX IF NOT EXISTS ix_policy_shadow_results_decision_id
    ON policy_shadow_results(decision_id);

CREATE TABLE IF NOT EXISTS policy_shadow_aggregates (
    aggregate_id UUID PRIMARY KEY,
    delta_id UUID NOT NULL UNIQUE REFERENCES policy_deltas(delta_id),
    total_decisions INTEGER NOT NULL DEFAULT 0,
    improved_decisions INTEGER NOT NULL DEFAULT 0,
    degraded_decisions INTEGER NOT NULL DEFAULT 0,
    neutral_decisions INTEGER NOT NULL DEFAULT 0,
    win_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
    min_sample_met BOOLEAN NOT NULL DEFAULT FALSE,
    accuracy_threshold_met BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    computed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (status IN ('PENDING', 'PASSED', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS ix_policy_shadow_aggregates_delta_id
    ON policy_shadow_aggregates(delta_id);

CREATE INDEX IF NOT EXISTS ix_policy_shadow_aggregates_status
    ON policy_shadow_aggregates(status);
