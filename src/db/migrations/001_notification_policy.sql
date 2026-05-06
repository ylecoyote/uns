-- AGSignal Core policy persistence schema.
-- This migration intentionally uses unqualified table names so standalone
-- deployments can choose their own database/schema boundary.

CREATE TABLE IF NOT EXISTS notification_policies (
    policy_id UUID PRIMARY KEY,
    notification_type VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    content_hash VARCHAR(64),
    previous_version_id UUID REFERENCES notification_policies(policy_id),
    delivery_mode VARCHAR(50),
    channels JSON,
    delivery_mode_by_autonomy JSON,
    require_ack JSON,
    channels_escalation JSON,
    ack_timeout_minutes INTEGER,
    dedup_window_seconds INTEGER,
    mode_overrides JSON,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    activated_at TIMESTAMP,
    retired_at TIMESTAMP,
    CHECK (status IN ('DRAFT', 'PREVIEW', 'ACTIVE', 'RETIRED')),
    CHECK (delivery_mode IS NULL OR delivery_mode IN ('GUARANTEED', 'BEST_EFFORT'))
);

CREATE INDEX IF NOT EXISTS ix_notification_policy_type_status
    ON notification_policies(notification_type, status);

CREATE INDEX IF NOT EXISTS ix_notification_policy_content_hash
    ON notification_policies(content_hash);

CREATE UNIQUE INDEX IF NOT EXISTS ux_notification_policy_active_preview
    ON notification_policies(notification_type, status)
    WHERE status IN ('ACTIVE', 'PREVIEW');
