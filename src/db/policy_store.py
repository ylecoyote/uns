"""SQLAlchemy-backed notification policy persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from db.models import PersistedNotificationPolicy
from notification.models import AutonomyMode, Channel, DeliveryMode
from notification.policies import (
    ModeOverride,
    NotificationPolicy,
    PolicyRegistry,
    PolicyStatus,
)
from notification.policy_loader import compute_policy_content_hash


@dataclass(frozen=True)
class PolicySaveResult:
    """Result of saving a policy row."""

    policy_id: UUID
    content_hash: str
    created: bool
    previous_version_id: UUID | None = None


class SQLAlchemyPolicyStore:
    """SQLAlchemy-backed store for persisted notification policies."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _get_session(self) -> Session:
        return self._session_factory()

    def save_policy(self, policy: NotificationPolicy) -> PolicySaveResult:
        """Persist a policy, skipping duplicate semantic content."""
        content = _policy_to_persisted_content(policy)
        content_hash = compute_policy_content_hash(content)
        session = self._get_session()
        try:
            duplicate = session.execute(
                select(PersistedNotificationPolicy).where(
                    PersistedNotificationPolicy.content_hash == content_hash
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                return PolicySaveResult(
                    policy_id=duplicate.policy_id,
                    content_hash=content_hash,
                    created=False,
                    previous_version_id=duplicate.previous_version_id,
                )

            now = datetime.now(UTC)
            previous_version_id = self._retire_current_policy(session, policy, now)
            row = PersistedNotificationPolicy(
                notification_type=policy.notification_type,
                version=policy.version,
                status=policy.status.value,
                content_hash=content_hash,
                previous_version_id=previous_version_id,
                delivery_mode=policy.delivery_mode.value if policy.delivery_mode else None,
                channels=content["channels"],
                delivery_mode_by_autonomy=content["delivery_mode_by_autonomy"],
                require_ack=content["require_ack"],
                channels_escalation=content["channels_escalation"],
                ack_timeout_minutes=policy.ack_timeout_minutes,
                dedup_window_seconds=policy.dedup_window_seconds,
                mode_overrides=content["mode_overrides"],
                description=None,
                is_active=policy.status in (PolicyStatus.ACTIVE, PolicyStatus.PREVIEW),
                activated_at=now if policy.status == PolicyStatus.ACTIVE else None,
                retired_at=now if policy.status == PolicyStatus.RETIRED else None,
            )
            session.add(row)
            session.commit()
            return PolicySaveResult(
                policy_id=row.policy_id,
                content_hash=content_hash,
                created=True,
                previous_version_id=previous_version_id,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def load_registry(
        self,
        statuses: tuple[PolicyStatus, ...] = (PolicyStatus.PREVIEW, PolicyStatus.ACTIVE),
    ) -> PolicyRegistry:
        """Load persisted runtime policies into an in-memory registry."""
        session = self._get_session()
        try:
            rows = (
                session.execute(
                    select(PersistedNotificationPolicy).where(
                        PersistedNotificationPolicy.status.in_([status.value for status in statuses])
                    )
                )
                .scalars()
                .all()
            )
            registry = PolicyRegistry(
                runtime_only=statuses == (PolicyStatus.ACTIVE,)
            )
            for row in sorted(rows, key=lambda item: _status_sort_key(item.status)):
                registry.register(_row_to_policy(row))
            return registry
        finally:
            session.close()

    def load_runtime_registry(self) -> PolicyRegistry:
        """Load only ACTIVE policies eligible for runtime enforcement."""
        return self.load_registry(statuses=(PolicyStatus.ACTIVE,))

    def load_shadow_registry(self) -> PolicyRegistry:
        """Load only PREVIEW policies eligible for shadow evaluation."""
        return self.load_registry(statuses=(PolicyStatus.PREVIEW,))

    def count_rows(self) -> int:
        """Return the number of persisted policy rows."""
        session = self._get_session()
        try:
            return len(session.execute(select(PersistedNotificationPolicy)).scalars().all())
        finally:
            session.close()

    def _retire_current_policy(
        self,
        session: Session,
        policy: NotificationPolicy,
        now: datetime,
    ) -> UUID | None:
        if policy.status not in (PolicyStatus.ACTIVE, PolicyStatus.PREVIEW):
            return None

        current = session.execute(
            select(PersistedNotificationPolicy).where(
                PersistedNotificationPolicy.notification_type == policy.notification_type,
                PersistedNotificationPolicy.status == policy.status.value,
            )
        ).scalar_one_or_none()
        if current is None:
            return None

        current.status = PolicyStatus.RETIRED.value
        current.is_active = False
        current.retired_at = now
        current.updated_at = now
        return current.policy_id


def _status_sort_key(status: str) -> int:
    if status == PolicyStatus.PREVIEW.value:
        return 0
    if status == PolicyStatus.ACTIVE.value:
        return 1
    return 2


def _policy_to_persisted_content(policy: NotificationPolicy) -> dict[str, Any]:
    channels: dict[str, list[str]] = {}
    require_ack: dict[str, bool] = {}
    delivery_mode_by_autonomy: dict[str, str] = {}
    mode_overrides: dict[str, dict[str, Any]] = {}

    for mode in AutonomyMode:
        override = policy._get_mode_override(mode)
        if override is None:
            continue
        mode_payload: dict[str, Any] = {}
        if override.channels is not None:
            channel_values = [channel.value for channel in override.channels]
            channels[mode.value] = channel_values
            mode_payload["channels"] = channel_values
        if override.require_ack is not None:
            require_ack[mode.value] = override.require_ack
            mode_payload["require_ack"] = override.require_ack
        if override.delivery_mode is not None:
            delivery_mode_by_autonomy[mode.value] = override.delivery_mode.value
            mode_payload["delivery_mode"] = override.delivery_mode.value
        if mode_payload:
            mode_overrides[mode.value] = mode_payload

    if policy.channels:
        channels["DEFAULT"] = [channel.value for channel in policy.channels]
    if policy.require_ack is not None:
        require_ack["DEFAULT"] = policy.require_ack

    return {
        "notification_type": policy.notification_type,
        "version": policy.version,
        "status": policy.status.value,
        "delivery_mode": policy.delivery_mode.value if policy.delivery_mode else None,
        "channels": channels,
        "delivery_mode_by_autonomy": delivery_mode_by_autonomy,
        "require_ack": require_ack,
        "channels_escalation": {},
        "ack_timeout_minutes": policy.ack_timeout_minutes,
        "dedup_window_seconds": policy.dedup_window_seconds,
        "mode_overrides": mode_overrides,
        "priority_override": policy.priority_override,
    }


def _row_to_policy(row: PersistedNotificationPolicy) -> NotificationPolicy:
    mode_overrides: dict[AutonomyMode, ModeOverride] = {}
    raw_channels: dict[str, Any] = row.channels if isinstance(row.channels, dict) else {}
    raw_require_ack: dict[str, Any] = row.require_ack if isinstance(row.require_ack, dict) else {}
    raw_delivery_mode: dict[str, Any] = (
        row.delivery_mode_by_autonomy if isinstance(row.delivery_mode_by_autonomy, dict) else {}
    )

    for mode in AutonomyMode:
        update: dict[str, Any] = {}
        if mode.value in raw_channels:
            update["channels"] = [Channel(channel) for channel in raw_channels[mode.value]]
        if mode.value in raw_require_ack:
            update["require_ack"] = bool(raw_require_ack[mode.value])
        if mode.value in raw_delivery_mode:
            update["delivery_mode"] = DeliveryMode(raw_delivery_mode[mode.value])
        if update:
            mode_overrides[mode] = ModeOverride(**update)

    base_channels: list[Channel] = []
    if isinstance(row.channels, list):
        base_channels = [Channel(channel) for channel in row.channels]
    elif isinstance(row.channels, dict) and "DEFAULT" in row.channels:
        base_channels = [Channel(channel) for channel in row.channels["DEFAULT"]]

    base_require_ack = row.require_ack if isinstance(row.require_ack, bool) else None
    if isinstance(row.require_ack, dict) and "DEFAULT" in row.require_ack:
        base_require_ack = bool(row.require_ack["DEFAULT"])

    return NotificationPolicy(
        notification_type=row.notification_type,
        version=row.version,
        status=PolicyStatus(row.status),
        delivery_mode=DeliveryMode(row.delivery_mode) if row.delivery_mode else None,
        channels=base_channels,
        require_ack=base_require_ack,
        ack_timeout_minutes=row.ack_timeout_minutes,
        dedup_window_seconds=row.dedup_window_seconds,
        config_id=row.policy_id,
        config_hash=row.content_hash,
        mode_overrides=mode_overrides or None,
    )


def create_sqlalchemy_policy_store(
    database_url: str,
    create_tables: bool = False,
) -> SQLAlchemyPolicyStore:
    """Factory function to create a SQLAlchemy policy store."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db.models import Base

    engine = create_engine(database_url)
    if create_tables:
        Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return SQLAlchemyPolicyStore(session_factory=session_factory)
