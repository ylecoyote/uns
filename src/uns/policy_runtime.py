"""Runtime-scoped policy authority shared by intake and read-only simulation."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from db.policy_store import (
    PG_POLICY_RELOAD_CHANNEL,
    PolicySnapshot,
    SQLAlchemyPolicyStore,
)
from notification.models import Channel, DeliveryMode, Notification
from notification.policies import PolicyOverrideError, PolicyRegistry
from notification.policy_loader import compute_policy_content_hash
from uns.responses import SendNotificationRequest
from uns.signaling import _resolve_notification

if TYPE_CHECKING:
    from notification.service import SimpleAdapterRegistry
    from notification.websocket_runtime import RedisPublisher

logger = logging.getLogger(__name__)

DEFAULT_POLICY_REDIS_CHANNEL = "uns:policies:reload"

# These fields steer adapters and are not inert producer event metadata.
_RESERVED_METADATA = frozenset(
    {"slack_channel", "email_to", "pagerduty_severity", "websocket_user_id"}
)


class PolicyReloadEnvelope(BaseModel):
    """Cross-process notification payload emitted when a policy snapshot activates."""

    revision: int = Field(description="Committed policy snapshot revision")
    content_hash: str = Field(description="SHA-256 content hash of the active policy snapshot")
    origin_id: str | None = Field(
        default=None,
        description="Identifier of the UNS worker/process that emitted the broadcast",
    )


class RedisPolicyReloadBroadcaster:
    """Publishes policy snapshot revision events to Redis pub/sub."""

    def __init__(
        self,
        redis_client: RedisPublisher,
        channel_name: str | None = None,
        instance_id: str | None = None,
    ) -> None:
        self._redis = redis_client
        self._channel = channel_name or os.environ.get(
            "UNS_POLICY_REDIS_CHANNEL", DEFAULT_POLICY_REDIS_CHANNEL
        )
        self._instance_id = instance_id or str(uuid4())

    @property
    def channel_name(self) -> str:
        return self._channel

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def publish(self, snapshot: PolicySnapshot) -> bool:
        envelope = PolicyReloadEnvelope(
            revision=snapshot.revision,
            content_hash=snapshot.content_hash,
            origin_id=self._instance_id,
        )
        try:
            self._redis.publish(self._channel, envelope.model_dump_json())
            return True
        except Exception as exc:
            logger.warning("Redis policy reload broadcast failed: %s", exc)
            return False


class RedisPolicyReloadSubscriber:
    """Handles Redis pub/sub messages to warm/refresh a peer PolicyRuntime."""

    def __init__(
        self,
        policy_runtime: PolicyRuntime,
        *,
        origin_id: str | None = None,
    ) -> None:
        self._policy_runtime = policy_runtime
        self._origin_id = origin_id

    def handle_message(self, message: object) -> PolicySnapshot | None:
        if not isinstance(message, dict) or message.get("type") != "message":
            return None
        raw_data = message.get("data")
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8")
        if not isinstance(raw_data, str):
            return None
        try:
            envelope = PolicyReloadEnvelope.model_validate_json(raw_data)
        except ValueError:
            logger.warning("Redis policy reload message had invalid JSON")
            return None
        if self._origin_id is not None and envelope.origin_id == self._origin_id:
            return None
        return self._policy_runtime.refresh_snapshot(expected_revision=envelope.revision)


class PostgresPolicyReloadListener:
    """Listens on PostgreSQL `LISTEN uns_policy_reload` and refreshes PolicyRuntime."""

    def __init__(
        self,
        engine: Engine,
        policy_runtime: PolicyRuntime,
        *,
        channel_name: str = PG_POLICY_RELOAD_CHANNEL,
    ) -> None:
        if engine.dialect.name != "postgresql":
            raise ValueError("PostgresPolicyReloadListener requires a PostgreSQL engine")
        self._engine = engine
        self._policy_runtime = policy_runtime
        self._channel = channel_name
        self._conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        self._conn.exec_driver_sql(f"LISTEN {self._channel}")

    def poll(self) -> list[PolicyReloadEnvelope]:
        """Drain pending PostgreSQL NOTIFY events and refresh PolicyRuntime."""
        from sqlalchemy import select

        # Trigger psycopg to read any buffered async notifications from the socket
        self._conn.execute(select(1))
        raw_driver_conn: Any = self._conn.connection.dbapi_connection
        envelopes: list[PolicyReloadEnvelope] = []
        pgconn = getattr(raw_driver_conn, "pgconn", None)
        if pgconn is not None and hasattr(pgconn, "notifies"):
            while True:
                notify = pgconn.notifies()
                if notify is None:
                    break
                payload_str = (
                    notify.payload.decode("utf-8")
                    if isinstance(notify.payload, bytes)
                    else str(notify.payload)
                )
                data = json.loads(payload_str)
                envelopes.append(PolicyReloadEnvelope.model_validate(data))
        elif hasattr(raw_driver_conn, "notifies"):
            notifies = raw_driver_conn.notifies
            while notifies:
                notify = notifies.pop(0)
                data = json.loads(str(notify.payload))
                envelopes.append(PolicyReloadEnvelope.model_validate(data))
        if envelopes:
            latest_rev = max(env.revision for env in envelopes)
            self._policy_runtime.refresh_snapshot(expected_revision=latest_rev)
        return envelopes

    def close(self) -> None:
        self._conn.close()


class PolicyRuntime:
    """Resolve immutable, persisted ACTIVE policy at the acceptance transaction.

    No process-global registry is consulted. Each request owns its immutable
    snapshot and detached registry. Intake locks the revision in the caller's
    transaction, so activation cannot commit until acceptance completes.
    Inspection and standalone simulation read a consistent committed snapshot.
    """

    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        adapters: SimpleAdapterRegistry | None = None,
        broadcaster: RedisPolicyReloadBroadcaster | None = None,
    ) -> None:
        self._adapters = adapters
        self._broadcaster = broadcaster
        self._reload_callbacks: list[Callable[[PolicySnapshot], None]] = []
        self.store = SQLAlchemyPolicyStore(sessions)
        self.store.ensure_snapshot_schema()
        self.store.register_activation_listener(self._on_store_activated)
        # Cold HTTP/MCP processes hydrate and migrate existing policy state here.
        self._warm_snapshot: PolicySnapshot = self.store.load_snapshot()

    @property
    def warm_snapshot(self) -> PolicySnapshot:
        """Return the warm in-process snapshot cache."""
        return self._warm_snapshot

    def set_broadcaster(self, broadcaster: RedisPolicyReloadBroadcaster | None) -> None:
        """Attach or replace a cross-process Redis reload broadcaster."""
        self._broadcaster = broadcaster

    def register_reload_callback(self, callback: Callable[[PolicySnapshot], None]) -> None:
        """Register a callback invoked when the warm snapshot advances."""
        if callback not in self._reload_callbacks:
            self._reload_callbacks.append(callback)

    def _on_store_activated(self, snapshot: PolicySnapshot) -> None:
        self._warm_snapshot = snapshot
        if self._broadcaster is not None:
            self._broadcaster.publish(snapshot)
        for callback in list(self._reload_callbacks):
            callback(snapshot)

    def refresh_snapshot(self, *, expected_revision: int | None = None) -> PolicySnapshot:
        """Reload committed snapshot from the database and notify local listeners."""
        if (
            expected_revision is not None
            and self._warm_snapshot.revision >= expected_revision
        ):
            return self._warm_snapshot
        previous_rev = self._warm_snapshot.revision
        snapshot = self.store.load_snapshot()
        self._warm_snapshot = snapshot
        if snapshot.revision != previous_rev:
            for callback in list(self._reload_callbacks):
                callback(snapshot)
        return snapshot

    def registry(self) -> PolicyRegistry:
        """A detached view for effective-policy queries; never mutable authority."""
        return self.refresh_snapshot().registry()

    def resolve(
        self,
        request: SendNotificationRequest,
        *,
        session: Session | None = None,
        principal: str,
    ) -> Notification:
        """Resolve with no delivery/audit side effects.

        Intake MUST pass its acceptance session to retain the revision lock
        until commit. Standalone simulation uses the read-only snapshot path.
        """
        if not principal:
            raise ValueError("An authenticated principal is required")
        reserved = set(_RESERVED_METADATA)
        if self._adapters is not None:
            websocket = self._adapters.get_adapter(Channel.WEBSOCKET)
            target_key = getattr(
                getattr(websocket, "config", None), "target_user_metadata_key", None
            )
            if target_key:
                reserved.add(target_key)
        rejected = sorted(reserved.intersection(request.metadata))
        if rejected:
            raise PolicyOverrideError(
                "Producer metadata cannot control adapter routing or urgency: "
                + ", ".join(rejected)
            )
        snapshot = (
            self.store.load_snapshot() if session is None else self.store.lock_snapshot(session)
        )
        registry = snapshot.registry()
        _, notification = _resolve_notification(request, policy_registry=registry)
        if not notification.channels:
            raise ValueError("A notification requires at least one delivery channel")
        if notification.delivery_mode == DeliveryMode.GUARANTEED and not any(
            channel != Channel.WEBSOCKET for channel in notification.channels
        ):
            raise ValueError(
                "GUARANTEED requires a persistent channel; choose BEST_EFFORT for WebSocket-only preview"
            )
        policy = registry.get_sync(notification.notification_type)
        policy_hash = notification.policy_config_hash or compute_policy_content_hash(
            policy.model_dump(mode="json", exclude={"config_id", "config_hash"})
            if policy
            else {"defaults_version": 1}
        )
        payload = notification.model_dump(mode="json")
        effective = {
            key: payload[key]
            for key in (
                "channels",
                "delivery_mode",
                "require_ack",
                "ack_timeout_minutes",
                "priority",
            )
        }
        effective["dedup_window_seconds"] = registry.get_dedup_window(
            notification.notification_type
        )
        provenance = {
            "policy_hash": policy_hash,
            "snapshot_revision": snapshot.revision,
            "snapshot_hash": snapshot.content_hash,
            "defaults_version": 1 if policy is None else None,
            "effective": effective,
            "effective_hash": compute_policy_content_hash(effective),
            "principal": principal,
            "overrides": {
                key: request.model_dump(mode="json").get(key)
                for key in ("delivery_mode", "require_ack", "priority")
            },
        }
        return notification.model_copy(
            update={
                "policy_config_hash": policy_hash,
                "policy_config_id": notification.policy_config_id
                or uuid5(NAMESPACE_URL, policy_hash),
                "policy_evaluation_id": notification.policy_evaluation_id or uuid4(),
                "metadata": {**notification.metadata, "uns_resolution": provenance},
            }
        )
