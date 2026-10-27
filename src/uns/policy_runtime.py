"""Runtime-scoped policy authority shared by intake and read-only simulation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy.orm import Session, sessionmaker

from db.policy_store import SQLAlchemyPolicyStore
from notification.models import Channel, DeliveryMode, Notification
from notification.policies import PolicyOverrideError, PolicyRegistry
from notification.policy_loader import compute_policy_content_hash
from uns.responses import SendNotificationRequest
from uns.signaling import _resolve_notification

if TYPE_CHECKING:
    from notification.service import SimpleAdapterRegistry

# These fields steer adapters and are not inert producer event metadata.
_RESERVED_METADATA = frozenset(
    {"slack_channel", "email_to", "pagerduty_severity", "websocket_user_id"}
)


class PolicyRuntime:
    """Resolve immutable, persisted ACTIVE policy at the acceptance transaction.

    No process-global registry is consulted. Each request owns its immutable
    snapshot and detached registry. Intake locks the revision in the caller's
    transaction, so activation cannot commit until acceptance completes.
    Inspection and standalone simulation read a consistent committed snapshot.
    """

    def __init__(
        self, sessions: sessionmaker[Session], *, adapters: SimpleAdapterRegistry | None = None
    ) -> None:
        self._adapters = adapters
        self.store = SQLAlchemyPolicyStore(sessions)
        self.store.ensure_snapshot_schema()
        # Cold HTTP/MCP processes hydrate and migrate existing policy state here.
        self.store.load_snapshot()

    def registry(self) -> PolicyRegistry:
        """A detached view for effective-policy queries; never mutable authority."""
        return self.store.load_snapshot().registry()

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
