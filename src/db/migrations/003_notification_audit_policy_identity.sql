-- Add policy evaluation identity to delivery audit records.
--
-- These nullable fields let UNS preserve the exact policy config and
-- evaluation identifier used for routing when that information is available.

ALTER TABLE notification_audit_records
    ADD COLUMN IF NOT EXISTS policy_config_id UUID;

ALTER TABLE notification_audit_records
    ADD COLUMN IF NOT EXISTS policy_config_hash VARCHAR(64);

ALTER TABLE notification_audit_records
    ADD COLUMN IF NOT EXISTS policy_evaluation_id UUID;

CREATE INDEX IF NOT EXISTS ix_notif_audit_policy_config_id
    ON notification_audit_records(policy_config_id);

CREATE INDEX IF NOT EXISTS ix_notif_audit_policy_config_hash
    ON notification_audit_records(policy_config_hash);

CREATE INDEX IF NOT EXISTS ix_notif_audit_policy_evaluation_id
    ON notification_audit_records(policy_evaluation_id);
