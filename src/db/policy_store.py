"""SQLAlchemy-backed notification policy persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Table, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateTable

from db.models import (
    NotificationPolicyContent,
    NotificationPolicyRevision,
    NotificationPolicySnapshot,
    PersistedNotificationPolicy,
)
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


@dataclass(frozen=True)
class PolicySnapshot:
    """Immutable serialized content. Each registry is an isolated deserialization."""

    revision: int
    content_json: str
    content_hash: str

    def registry(self) -> PolicyRegistry:
        registry = PolicyRegistry()
        for content in json.loads(self.content_json):
            registry.register(NotificationPolicy.model_validate(content))
        return registry


class SQLAlchemyPolicyStore:
    """SQLAlchemy-backed store for persisted notification policies."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def ensure_snapshot_schema(self) -> None:
        """Add only new policy tables; legacy policy rows remain untouched."""
        engine = self._session_factory.kw["bind"]
        # Database-native IF NOT EXISTS avoids checkfirst's check/CREATE race
        # when multiple fresh processes upgrade an already deployed database.
        with engine.begin() as connection:
            for model in (
                NotificationPolicyRevision,
                NotificationPolicySnapshot,
                NotificationPolicyContent,
            ):
                connection.execute(CreateTable(cast(Table, model.__table__), if_not_exists=True))

    def load_snapshot(self, session: Session | None = None) -> PolicySnapshot:
        """Lock the revision until caller commit, then read its immutable content.

        Activation takes the same row lock. The no-op UPDATE is deliberate: it
        reserves SQLite's writer before any policy read, and row-locks PostgreSQL.
        A cache check outside the acceptance transaction is not sufficient.
        """
        if session is None:
            with self._session_factory.begin() as transaction:
                return self.load_snapshot(transaction)
        changed = (
            session.connection()
            .execute(
                update(NotificationPolicyRevision)
                .where(NotificationPolicyRevision.singleton == 1)
                .values(revision=NotificationPolicyRevision.revision)
            )
            .rowcount
        )
        if not changed:
            # A concurrent first initializer can win on PostgreSQL; a savepoint
            # preserves our outer transaction when its singleton insert wins.
            try:
                with session.begin_nested():
                    session.execute(
                        insert(NotificationPolicyRevision).values(singleton=1, revision=-1)
                    )
            except IntegrityError:
                pass
            session.execute(
                update(NotificationPolicyRevision)
                .where(NotificationPolicyRevision.singleton == 1)
                .values(revision=NotificationPolicyRevision.revision)
            )
        revision = session.execute(
            select(NotificationPolicyRevision.revision).where(
                NotificationPolicyRevision.singleton == 1
            )
        ).scalar_one()
        if revision == -1:
            # One-time migration of already deployed policy rows. This is done
            # under the same lock, so another process cannot accept an empty
            # snapshot while the legacy ACTIVE policies are being hydrated.
            rows = session.execute(
                select(PersistedNotificationPolicy).where(
                    PersistedNotificationPolicy.status == PolicyStatus.ACTIVE.value
                )
            ).scalars()
            policies = [self._hydrate_policy(session, row) for row in rows]
            if len({policy.notification_type for policy in policies}) != len(policies):
                raise ValueError("Legacy storage contains multiple ACTIVE policies for one type")
            snapshot = self._write_snapshot(session, 1 if policies else 0, policies)
        else:
            row = session.execute(
                select(NotificationPolicySnapshot).where(
                    NotificationPolicySnapshot.revision == revision
                )
            ).scalar_one()
            snapshot = PolicySnapshot(
                revision, json.dumps(row.content, sort_keys=True), row.content_hash
            )
        return snapshot

    def _write_snapshot(
        self, session: Session, revision: int, policies: list[NotificationPolicy]
    ) -> PolicySnapshot:
        content = [
            policy.model_dump(mode="json")
            for policy in sorted(policies, key=lambda policy: policy.notification_type)
        ]
        content_hash = compute_policy_content_hash({"policies": content})
        session.add(
            NotificationPolicySnapshot(
                revision=revision, content=content, content_hash=content_hash
            )
        )
        session.execute(
            update(NotificationPolicyRevision)
            .where(NotificationPolicyRevision.singleton == 1)
            .values(revision=revision)
        )
        session.flush()
        return PolicySnapshot(revision, json.dumps(content, sort_keys=True), content_hash)

    def _activate(
        self, session: Session, previous: PolicySnapshot, policies: list[NotificationPolicy]
    ) -> None:
        content = [
            policy.model_dump(mode="json")
            for policy in sorted(policies, key=lambda policy: policy.notification_type)
        ]
        if compute_policy_content_hash({"policies": content}) != previous.content_hash:
            self._write_snapshot(session, previous.revision + 1, policies)

    def _get_session(self) -> Session:
        return self._session_factory()

    @staticmethod
    def _hydrate_policy(session: Session, row: PersistedNotificationPolicy) -> NotificationPolicy:
        saved = session.get(NotificationPolicyContent, row.policy_id)
        if saved is None:
            return _row_to_policy(row)
        # Never resurrect serialized ACTIVE status from a subsequently retired
        # version. The compatibility row owns the version's lifecycle state.
        return NotificationPolicy.model_validate(saved.content).model_copy(
            update={
                "status": PolicyStatus(row.status),
                "config_id": row.policy_id,
                "config_hash": row.content_hash,
            }
        )

    def save_policy(self, policy: NotificationPolicy) -> PolicySaveResult:
        """Persist and activate one policy atomically with its runtime revision."""
        self.ensure_snapshot_schema()
        with self._session_factory.begin() as session:
            previous = self.load_snapshot(session)
            result = self._save_policy(session, policy)
            if policy.status == PolicyStatus.ACTIVE:
                current = previous.registry().get_all()
                current[policy.notification_type] = policy.model_copy(
                    update={"config_id": result.policy_id, "config_hash": result.content_hash}
                )
                self._activate(session, previous, list(current.values()))
            return result

    def save_snapshot(self, policies: list[NotificationPolicy]) -> int:
        """Atomically replace ACTIVE authority; retain immutable revision history."""
        identities = [(policy.notification_type, policy.status) for policy in policies]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate notification type/status in policy snapshot")
        self.ensure_snapshot_schema()
        with self._session_factory.begin() as session:
            previous = self.load_snapshot(session)
            results = [self._save_policy(session, policy) for policy in policies]
            active = [
                policy.model_copy(
                    update={"config_id": result.policy_id, "config_hash": result.content_hash}
                )
                for policy, result in zip(policies, results)
                if policy.status == PolicyStatus.ACTIVE
            ]
            session.execute(
                update(PersistedNotificationPolicy)
                .where(
                    PersistedNotificationPolicy.status == PolicyStatus.ACTIVE.value,
                    PersistedNotificationPolicy.notification_type.not_in(
                        [p.notification_type for p in active]
                    ),
                )
                .values(
                    status=PolicyStatus.RETIRED.value, is_active=False, retired_at=datetime.now(UTC)
                )
            )
            self._activate(session, previous, active)
            return sum(result.created for result in results)

    def _save_policy(self, session: Session, policy: NotificationPolicy) -> PolicySaveResult:
        content = _policy_to_persisted_content(policy)
        content_hash = compute_policy_content_hash(
            policy.model_dump(mode="json", exclude={"config_id", "config_hash"})
        )
        duplicate = session.execute(
            select(PersistedNotificationPolicy).where(
                PersistedNotificationPolicy.content_hash == content_hash
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            if (
                duplicate.status == PolicyStatus.RETIRED.value
                and policy.status != PolicyStatus.RETIRED
            ):
                raise ValueError(
                    "A retired policy version cannot be reactivated; publish a new version"
                )
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
        session.flush()
        session.add(
            NotificationPolicyContent(
                policy_id=row.policy_id,
                content=policy.model_dump(mode="json", exclude={"config_id", "config_hash"}),
            )
        )
        session.flush()
        return PolicySaveResult(
            policy_id=row.policy_id,
            content_hash=content_hash,
            created=True,
            previous_version_id=previous_version_id,
        )

    def load_registry(
        self,
        statuses: tuple[PolicyStatus, ...] = (PolicyStatus.PREVIEW, PolicyStatus.ACTIVE),
    ) -> PolicyRegistry:
        """Load persisted runtime policies into an in-memory registry."""
        self.ensure_snapshot_schema()
        session = self._get_session()
        try:
            rows = (
                session.execute(
                    select(PersistedNotificationPolicy).where(
                        PersistedNotificationPolicy.status.in_(
                            [status.value for status in statuses]
                        )
                    )
                )
                .scalars()
                .all()
            )
            registry = PolicyRegistry(runtime_only=statuses == (PolicyStatus.ACTIVE,))
            for row in sorted(rows, key=lambda item: _status_sort_key(item.status)):
                if row.status != PolicyStatus.ACTIVE.value:
                    registry.register(self._hydrate_policy(session, row))
            if PolicyStatus.ACTIVE in statuses:
                for policy in self.load_runtime_registry().get_all().values():
                    registry.register(policy)
            return registry
        finally:
            session.close()

    def load_runtime_registry(self) -> PolicyRegistry:
        """Load only ACTIVE policies eligible for runtime enforcement."""
        self.ensure_snapshot_schema()
        return self.load_snapshot().registry()

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
        if override is None and not policy.channels_by_mode:
            continue
        override = override or ModeOverride()
        mode_payload: dict[str, Any] = {}
        if override.channels is not None:
            channel_values = [channel.value for channel in override.channels]
            channels[mode.value] = channel_values
            mode_payload["channels"] = channel_values
        elif policy.channels_by_mode and mode in policy.channels_by_mode:
            channel_values = [channel.value for channel in policy.channels_by_mode[mode]]
            channels[mode.value] = channel_values
            mode_payload["channels"] = channel_values
        if override.ack_timeout_minutes is not None:
            mode_payload["ack_timeout_minutes"] = override.ack_timeout_minutes
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
        update: dict[str, Any] = dict((row.mode_overrides or {}).get(mode.value, {}))
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
