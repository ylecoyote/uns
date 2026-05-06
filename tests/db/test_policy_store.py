"""Tests for DB-backed notification policy persistence."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, PersistedNotificationPolicy
from db.policy_store import SQLAlchemyPolicyStore
from notification.models import AutonomyMode, Channel, DeliveryMode
from notification.policies import NotificationPolicy, PolicyRegistry, PolicyStatus


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _policy(
    version: str = "1.0.0",
    status: PolicyStatus = PolicyStatus.ACTIVE,
    live_channels: list[str] | None = None,
) -> NotificationPolicy:
    return NotificationPolicy.from_dict(
        {
            "notification_type": "safety.kill_switch",
            "version": version,
            "status": status.value,
            "delivery_mode": "GUARANTEED",
            "channels": {
                "LIVE": live_channels or ["SLACK", "WEBSOCKET"],
                "PREVIEW": ["WEBSOCKET"],
            },
            "require_ack": {
                "LIVE": True,
                "PREVIEW": False,
            },
            "dedup_window_seconds": 600,
        }
    )


def test_policy_model_supports_lifecycle_columns_without_atp_schema() -> None:
    table = PersistedNotificationPolicy.__table__

    assert table.schema is None
    assert "policy_id" in table.columns
    assert "version" in table.columns
    assert "status" in table.columns
    assert "content_hash" in table.columns
    assert "previous_version_id" in table.columns
    assert "activated_at" in table.columns
    assert "retired_at" in table.columns


def test_standalone_policy_migration_has_no_atp_schema_reference() -> None:
    migration = Path("src/db/migrations/001_notification_policy.sql").read_text()

    assert "notification_policies" in migration
    assert "atp." not in migration.lower()
    assert "schema atp" not in migration.lower()


def test_save_policy_skips_duplicate_content_hash() -> None:
    store = SQLAlchemyPolicyStore(_session_factory())
    policy = _policy()

    first = store.save_policy(policy)
    second = store.save_policy(policy)

    assert first.created is True
    assert second.created is False
    assert second.policy_id == first.policy_id
    assert store.count_rows() == 1


def test_replacing_active_policy_retires_previous_and_links_history() -> None:
    session_factory = _session_factory()
    store = SQLAlchemyPolicyStore(session_factory)

    first = store.save_policy(_policy(version="1.0.0"))
    second = store.save_policy(
        _policy(version="2.0.0", live_channels=["SLACK", "WEBSOCKET", "PAGERDUTY"])
    )

    assert second.created is True
    assert second.previous_version_id == first.policy_id

    session = session_factory()
    try:
        rows = session.query(PersistedNotificationPolicy).all()
        active = [row for row in rows if row.status == PolicyStatus.ACTIVE.value]
        retired = [row for row in rows if row.status == PolicyStatus.RETIRED.value]
        assert len(active) == 1
        assert len(retired) == 1
        assert retired[0].policy_id == first.policy_id
        assert retired[0].retired_at is not None
    finally:
        session.close()


def test_load_registry_includes_active_and_preview_policies_only() -> None:
    store = SQLAlchemyPolicyStore(_session_factory())
    store.save_policy(_policy(status=PolicyStatus.DRAFT, version="0.1.0"))
    store.save_policy(_policy(status=PolicyStatus.PREVIEW, version="0.9.0"))
    store.save_policy(_policy(status=PolicyStatus.ACTIVE, version="1.0.0"))

    registry = store.load_registry()
    policy = registry.get_sync("safety.kill_switch")

    assert isinstance(registry, PolicyRegistry)
    assert policy is not None
    assert policy.status == PolicyStatus.ACTIVE
    assert policy.version == "1.0.0"
    assert policy.delivery_mode == DeliveryMode.GUARANTEED
    assert policy.get_channels_for_mode(AutonomyMode.LIVE) == [
        Channel.SLACK,
        Channel.WEBSOCKET,
    ]
    assert policy.get_require_ack_for_mode(AutonomyMode.LIVE) is True


def test_load_runtime_registry_excludes_preview_draft_and_retired_edits() -> None:
    store = SQLAlchemyPolicyStore(_session_factory())
    store.save_policy(_policy(status=PolicyStatus.DRAFT, version="0.1.0"))
    store.save_policy(_policy(status=PolicyStatus.PREVIEW, version="0.9.0"))
    store.save_policy(_policy(status=PolicyStatus.ACTIVE, version="1.0.0"))
    store.save_policy(
        _policy(
            status=PolicyStatus.RETIRED,
            version="2.0.0",
            live_channels=["PAGERDUTY"],
        )
    )

    registry = store.load_runtime_registry()
    policy = registry.get_sync("safety.kill_switch")

    assert policy is not None
    assert policy.status == PolicyStatus.ACTIVE
    assert policy.version == "1.0.0"


def test_load_shadow_registry_loads_preview_without_runtime_enforcement() -> None:
    store = SQLAlchemyPolicyStore(_session_factory())
    store.save_policy(_policy(status=PolicyStatus.PREVIEW, version="0.9.0"))
    store.save_policy(_policy(status=PolicyStatus.ACTIVE, version="1.0.0"))

    registry = store.load_shadow_registry()
    policy = registry.get_sync("safety.kill_switch")

    assert policy is not None
    assert policy.status == PolicyStatus.PREVIEW
    assert policy.is_shadow_evaluated is True
    assert policy.is_runtime_enforced is False
