"""Policy authority, immutable snapshots and cross-process transaction ordering."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker

from db.models import Base, PersistedNotificationPolicy
from db.policy_store import SQLAlchemyPolicyStore
from notification.models import Channel, DeliveryMode, NotificationIntent
from notification.policies import (
    ModeOverride,
    NotificationPolicy,
    PolicyRegistry,
    configure_policy_registry,
)
from notification.sdk import NotificationSDK
from uns.responses import SendNotificationRequest


def policy(version="1", **changes):
    return NotificationPolicy(
        notification_type="policy.alarm",
        version=version,
        channels=[Channel.SLACK],
        delivery_mode=DeliveryMode.GUARANTEED,
        require_ack=True,
        **changes,
    )


def request(**changes):
    return SendNotificationRequest.model_validate(
        {
            "notification_type": "policy.alarm",
            "intent": "SAFETY",
            "title": "Alarm",
            "message": "Local test",
            "source": "test",
            "idempotency_key": str(uuid4()),
            "autonomy_context": {"agent_id": str(uuid4()), "autonomy_mode": "LIVE"},
            **changes,
        }
    )


@pytest.fixture
def database(tmp_path):
    url = f"sqlite:///{tmp_path / 'policies.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    yield url, sessions
    engine.dispose()


def service(sessions):
    from uns.policy_runtime import PolicyRuntime

    return PolicyRuntime(sessions)


@pytest.mark.parametrize(
    "override",
    [
        {"delivery_mode_override": DeliveryMode.BEST_EFFORT},
        {"require_ack_override": False},
        {"channels_override": [Channel.EMAIL]},
        {"priority_override": "LOW"},
        {"priority_override": "NORMAL"},
    ],
)
def test_sdk_rejects_every_differing_override_for_active_policy(override):
    registry = PolicyRegistry()
    registry.register(policy())
    req = request()
    with pytest.raises(ValueError, match="ACTIVE policy"):
        NotificationSDK(policy_registry=registry).send(
            notification_type=req.notification_type,
            intent=req.intent,
            title=req.title,
            message=req.message,
            source=req.source,
            autonomy_context=req.autonomy_context.to_domain(),
            **override,
        )


def test_runtime_service_rejects_payload_self_granted_override(database):
    _, sessions = database
    SQLAlchemyPolicyStore(sessions).save_snapshot([policy()])
    runtime = service(sessions)
    with pytest.raises(ValueError, match="ACTIVE policy"):
        runtime.resolve(request(require_ack=False, metadata={"admin": True}), principal="producer")
    accepted = runtime.resolve(
        request(require_ack=True, delivery_mode="GUARANTEED"), principal="producer"
    )
    assert accepted.require_ack is True
    assert accepted.metadata["uns_resolution"]["snapshot_revision"] == 1


def test_defaults_and_unconfigured_explicit_preview_remain_meaningful(database):
    _, sessions = database
    runtime = service(sessions)
    live = runtime.resolve(request(), principal="producer")
    assert live.delivery_mode == DeliveryMode.GUARANTEED and live.require_ack
    preview = runtime.resolve(
        request(
            autonomy_context={"agent_id": str(uuid4()), "autonomy_mode": "PREVIEW"},
            delivery_mode="BEST_EFFORT",
        ),
        principal="producer",
    )
    assert preview.channels == [Channel.WEBSOCKET]
    assert preview.delivery_mode == DeliveryMode.BEST_EFFORT and not preview.require_ack
    assert preview.metadata["uns_resolution"]["defaults_version"] == 1


def test_complete_policy_round_trips_and_snapshot_isolation(database):
    _, sessions = database
    store = SQLAlchemyPolicyStore(sessions)
    original = policy(
        intent=NotificationIntent.SAFETY,
        priority_override="NORMAL",
        live_override=ModeOverride(ack_timeout_minutes=2),
        dedup_window_seconds=17,
    )
    store.save_snapshot([original])
    runtime = service(sessions)
    before = runtime.resolve(request(), principal="producer")
    assert before.priority.value == "NORMAL" and before.ack_timeout_minutes == 2
    assert runtime.registry().get_sync("policy.alarm").intent == NotificationIntent.SAFETY
    # Frozen Pydantic models still contain mutable lists. Neither caller nor registry mutation
    # may rewrite the immutable persisted snapshot or a runtime's cached content.
    original.channels.append(Channel.EMAIL)
    runtime.registry().get_sync("policy.alarm").channels.append(Channel.PAGERDUTY)
    after = runtime.resolve(request(), principal="producer")
    assert after.channels == [Channel.SLACK]
    assert after.metadata["uns_resolution"]["effective"]["dedup_window_seconds"] == 17
    assert before.policy_config_hash == after.policy_config_hash


def test_revision_changes_only_on_effective_snapshot_activation_and_rolls_back(database):
    _, sessions = database
    store = SQLAlchemyPolicyStore(sessions)
    runtime = service(sessions)
    assert (
        runtime.resolve(request(), principal="p").metadata["uns_resolution"]["snapshot_revision"]
        == 0
    )
    store.save_snapshot([policy()])
    store.save_snapshot([policy()])
    assert (
        runtime.resolve(request(), principal="p").metadata["uns_resolution"]["snapshot_revision"]
        == 1
    )
    invalid = policy("2").model_copy(update={"channels": [Channel.EMAIL]})
    with pytest.raises(ValueError):
        store.save_snapshot([invalid, invalid])
    assert runtime.resolve(request(), principal="p").channels == [Channel.SLACK]
    store.save_snapshot([])
    assert (
        runtime.resolve(request(), principal="p").metadata["uns_resolution"]["snapshot_revision"]
        == 2
    )


def test_legacy_rows_migrate_without_global_registry_authority(database):
    _, sessions = database
    with sessions.begin() as session:
        session.execute(
            insert(PersistedNotificationPolicy).values(
                notification_type="policy.alarm",
                version="legacy",
                status="ACTIVE",
                channels={"DEFAULT": ["EMAIL"]},
                delivery_mode="GUARANTEED",
                require_ack={"DEFAULT": True},
                mode_overrides={},
            )
        )
    registry = PolicyRegistry()
    registry.register(policy())
    configure_policy_registry(registry)
    loaded = service(sessions).resolve(request(), principal="p")
    assert loaded.channels == [Channel.EMAIL]
    assert loaded.metadata["uns_resolution"]["snapshot_revision"] == 1
    configure_policy_registry(PolicyRegistry())


def child_environment(url):
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("UNS_")
    }
    return {
        **env,
        "PYTHONPATH": str(Path.cwd() / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "UNS_DATABASE_URL": url,
    }


def test_fresh_process_hydrates_persisted_policy(database):
    url, sessions = database
    SQLAlchemyPolicyStore(sessions).save_snapshot(
        [policy().model_copy(update={"channels": [Channel.EMAIL]})]
    )
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json, os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uns.policy_runtime import PolicyRuntime
p = PolicyRuntime(sessionmaker(create_engine(os.environ["UNS_DATABASE_URL"])))
print(json.dumps(p.registry().get_sync("policy.alarm").model_dump(mode="json")))
""",
        ],
        env=child_environment(url),
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    loaded = json.loads(child.stdout)
    assert loaded["channels"] == ["EMAIL"] and loaded["require_ack"] is True


def test_real_separate_process_refreshes_before_resolution(database):
    url, sessions = database
    store = SQLAlchemyPolicyStore(sessions)
    store.save_snapshot([policy()])
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            """
import json, os, sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uns.policy_runtime import PolicyRuntime
from uns.responses import SendNotificationRequest
p = PolicyRuntime(sessionmaker(create_engine(os.environ["UNS_DATABASE_URL"])))
print("ready", flush=True)
req = SendNotificationRequest.model_validate(json.loads(sys.stdin.readline()))
n = p.resolve(req, principal="child")
print(json.dumps(n.model_dump(mode="json")), flush=True)
""",
        ],
        env=child_environment(url),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline().strip() == "ready"
        store.save_snapshot([policy("2").model_copy(update={"channels": [Channel.EMAIL]})])
        output, errors = child.communicate(request().model_dump_json() + "\n", timeout=10)
        assert child.returncode == 0, errors
        notification = json.loads(output)
        assert notification["channels"] == ["EMAIL"]
        assert notification["metadata"]["uns_resolution"]["snapshot_revision"] == 2
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()


def test_activation_cannot_commit_between_resolution_and_acceptance_commit(database):
    url, sessions = database
    store = SQLAlchemyPolicyStore(sessions)
    store.save_snapshot([policy()])
    runtime = service(sessions)
    child = None
    try:
        with sessions.begin() as session:
            accepted = runtime.resolve(request(), session=session, principal="producer")
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    """
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from db.policy_store import SQLAlchemyPolicyStore
from notification.policies import NotificationPolicy
engine = create_engine(os.environ["UNS_DATABASE_URL"])
store = SQLAlchemyPolicyStore(sessionmaker(engine))
@event.listens_for(engine, "before_cursor_execute")
def before(conn, cursor, statement, parameters, context, executemany):
    if statement.startswith("UPDATE notification_policy_revision"):
        print("locking", flush=True)
store.save_snapshot([NotificationPolicy(notification_type="policy.alarm", version="2", channels=["EMAIL"])])
print("committed", flush=True)
""",
                ],
                env=child_environment(url),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert child.stdout.readline().strip() == "locking"
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                assert not selector.select(timeout=0.2), (
                    "activation escaped intake transaction lock"
                )
            assert accepted.metadata["uns_resolution"]["snapshot_revision"] == 1
        output, errors = child.communicate(timeout=10)
        assert child.returncode == 0, errors
        assert "committed" in output
        current = runtime.resolve(request(), principal="producer")
        assert current.channels == [Channel.EMAIL]
        assert current.metadata["uns_resolution"]["snapshot_revision"] == 2
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.communicate()


def test_partial_activation_failure_rolls_back_rows_and_revision(database):
    from sqlalchemy import select

    from db.models import NotificationPolicySnapshot

    _, sessions = database
    store = SQLAlchemyPolicyStore(sessions)
    first = policy()
    second = policy("2").model_copy(update={"channels": [Channel.EMAIL]})
    store.save_snapshot([first])
    store.save_snapshot([second])
    runtime = service(sessions)
    with sessions() as session:
        historical = session.execute(
            select(NotificationPolicySnapshot.content).where(
                NotificationPolicySnapshot.revision == 1
            )
        ).scalar_one()
    with pytest.raises(ValueError, match="retired"):
        store.save_snapshot(
            [
                policy().model_copy(update={"notification_type": "new.alarm"}),
                first,
            ]
        )
    after = runtime.resolve(request(), principal="p")
    assert after.channels == [Channel.EMAIL]
    assert after.metadata["uns_resolution"]["snapshot_revision"] == 2
    assert store.count_rows() == 2
    with sessions() as session:
        assert (
            session.execute(
                select(NotificationPolicySnapshot.content).where(
                    NotificationPolicySnapshot.revision == 1
                )
            ).scalar_one()
            == historical
        )


def test_two_database_runtimes_do_not_share_authority(database, tmp_path):
    _, first_sessions = database
    other_engine = create_engine(f"sqlite:///{tmp_path / 'other.db'}")
    Base.metadata.create_all(other_engine)
    second_sessions = sessionmaker(other_engine)
    try:
        SQLAlchemyPolicyStore(first_sessions).save_snapshot([policy()])
        SQLAlchemyPolicyStore(second_sessions).save_snapshot(
            [policy().model_copy(update={"channels": [Channel.EMAIL]})]
        )
        one, two = service(first_sessions), service(second_sessions)
        assert one.resolve(request(), principal="p").channels == [Channel.SLACK]
        assert two.resolve(request(), principal="p").channels == [Channel.EMAIL]
        assert one.resolve(request(), principal="p").channels == [Channel.SLACK]
    finally:
        other_engine.dispose()


async def test_simulation_uses_authority_without_acceptance_side_effects(database):
    from sqlalchemy import func, select

    from db.models import NotificationAuditRecord, NotificationPolicySnapshot
    from uns.signaling import simulate_signal

    _, sessions = database
    store = SQLAlchemyPolicyStore(sessions)
    store.save_snapshot([policy()])
    runtime = service(sessions)
    with pytest.raises(ValueError, match="ACTIVE policy"):
        await simulate_signal(
            request=request(require_ack=False), policy_runtime=runtime, principal="p"
        )
    result = await simulate_signal(request=request(), policy_runtime=runtime, principal="p")
    assert result.require_ack and result.delivery_mode == DeliveryMode.GUARANTEED
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(NotificationAuditRecord)) == 0
        assert session.scalar(select(func.count()).select_from(NotificationPolicySnapshot)) == 2


def test_policy_intent_cannot_be_reclassified_by_producer(database):
    _, sessions = database
    SQLAlchemyPolicyStore(sessions).save_snapshot([policy(intent=NotificationIntent.SAFETY)])
    with pytest.raises(ValueError, match="intent.*ACTIVE policy"):
        service(sessions).resolve(request(intent="INFORMATIONAL"), principal="p")


@pytest.mark.parametrize(
    "metadata",
    [
        {"slack_channel": "#attacker"},
        {"email_to": ["attacker@example.test"]},
        {"pagerduty_severity": "info"},
        {"websocket_user_id": "another-user"},
    ],
)
@pytest.mark.parametrize("active", [True, False])
def test_producer_cannot_redirect_or_downgrade_using_adapter_metadata(database, metadata, active):
    _, sessions = database
    if active:
        SQLAlchemyPolicyStore(sessions).save_snapshot([policy()])
    with pytest.raises(ValueError, match="adapter routing or urgency"):
        service(sessions).resolve(request(metadata=metadata), principal="p")


def test_custom_websocket_target_key_reserved_but_inert_metadata_preserved(database):
    from notification.adapters.websocket import (
        InMemoryConnectionManager,
        WebSocketAdapter,
        WebSocketConfig,
    )
    from notification.service import SimpleAdapterRegistry
    from uns.policy_runtime import PolicyRuntime

    _, sessions = database
    adapters = SimpleAdapterRegistry()
    # Validation inspects server configuration only and performs no adapter I/O.
    adapter = WebSocketAdapter(
        config=WebSocketConfig(target_user_metadata_key="recipient"),
        connection_manager=InMemoryConnectionManager(),
    )
    adapters.register(adapter)
    runtime = PolicyRuntime(sessions, adapters=adapters)
    with pytest.raises(ValueError, match="recipient"):
        runtime.resolve(request(metadata={"recipient": "another-user"}), principal="p")
    allowed = {"domain": "test", "details": {"recipient": "inert nested business data"}}
    assert (
        runtime.resolve(request(metadata=allowed), principal="p").metadata["details"]
        == allowed["details"]
    )


async def test_effective_policy_query_matches_mode_specific_runtime_resolution(database):
    from notification.models import AutonomyMode
    from uns.queries import get_effective_policy

    _, sessions = database
    SQLAlchemyPolicyStore(sessions).save_snapshot(
        [
            policy(
                live_override=ModeOverride(
                    delivery_mode=DeliveryMode.BEST_EFFORT, ack_timeout_minutes=2
                )
            )
        ]
    )
    runtime = service(sessions)
    actual = runtime.resolve(request(), principal="p")
    preview = await get_effective_policy(
        "policy.alarm",
        NotificationIntent.SAFETY,
        AutonomyMode.LIVE,
        policy_registry=runtime.registry(),
    )
    assert preview.effective.delivery_mode == actual.delivery_mode
    assert preview.effective.ack_timeout_minutes == actual.ack_timeout_minutes
    from uns.signaling import simulate_signal

    allowed = await simulate_signal(
        request=request(delivery_mode="BEST_EFFORT", require_ack=True),
        policy_runtime=runtime,
        principal="p",
    )
    assert (
        allowed.delivery_mode == actual.delivery_mode and allowed.require_ack == actual.require_ack
    )
    for changes in ({"delivery_mode": "GUARANTEED"}, {"require_ack": False}):
        with pytest.raises(ValueError, match="ACTIVE policy"):
            await simulate_signal(request=request(**changes), policy_runtime=runtime, principal="p")
    assert any(
        step.source.value == "mode_override" and step.applied
        for step in preview.resolution["delivery_mode"]
    )


@pytest.mark.parametrize("status", ["PREVIEW", "DRAFT"])
def test_nonactive_policy_roundtrip_and_intentional_promotion_preserve_complete_content(
    database, status
):
    from notification.policies import PolicyStatus

    _, sessions = database
    store = SQLAlchemyPolicyStore(sessions)
    staged = policy(
        status=PolicyStatus(status),
        intent=NotificationIntent.SAFETY,
        priority_override="NORMAL",
        live_override=ModeOverride(ack_timeout_minutes=2),
    )
    saved = store.save_policy(staged)
    restored = store.load_registry(statuses=(PolicyStatus(status),)).get_sync("policy.alarm")
    assert restored.intent == staged.intent
    assert restored.priority_override == staged.priority_override
    assert restored.config_hash == saved.content_hash and restored.config_id == saved.policy_id
    assert restored.get_ack_timeout_minutes_for_mode("LIVE", NotificationIntent.SAFETY) == 2
    assert store.load_runtime_registry().get_sync("policy.alarm") is None
    active = restored.model_copy(update={"status": PolicyStatus.ACTIVE, "version": "2"})
    store.save_policy(active)
    accepted = service(sessions).resolve(request(), principal="p")
    assert accepted.priority.value == "NORMAL" and accepted.ack_timeout_minutes == 2
    store.save_snapshot([])
    retired = store.load_registry(statuses=(PolicyStatus.RETIRED,)).get_sync("policy.alarm")
    assert retired.status == PolicyStatus.RETIRED
    assert store.load_runtime_registry().get_sync("policy.alarm") is None
    with pytest.raises(ValueError, match="retired"):
        store.save_policy(active)


def test_concurrent_cold_schema_upgrade_is_idempotent(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(url)
    # A deployed legacy database has only pre-snapshot policy tables.
    PersistedNotificationPolicy.__table__.create(engine)
    engine.dispose()
    program = """
import os, sys
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from db.policy_store import SQLAlchemyPolicyStore
engine = create_engine(os.environ["UNS_DATABASE_URL"])
@event.listens_for(engine, "before_cursor_execute")
def gate(conn, cursor, statement, parameters, context, executemany):
    if statement.lstrip().startswith("CREATE TABLE") and "notification_policy_revision" in statement:
        print("ready", flush=True)
        sys.stdin.readline()
SQLAlchemyPolicyStore(sessionmaker(engine)).ensure_snapshot_schema()
print("complete", flush=True)
"""
    children = [
        subprocess.Popen(
            [sys.executable, "-c", program],
            env=child_environment(url),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    try:
        for child in children:
            assert child.stdout.readline().strip() == "ready"
        for child in children:
            child.stdin.write("\n")
            child.stdin.flush()
        for child in children:
            output, error = child.communicate(timeout=10)
            assert child.returncode == 0, error
            assert "complete" in output
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate()


async def test_effective_policy_unconfigured_channels_and_no_ack_match_runtime(database):
    from notification.models import AutonomyMode
    from uns.queries import get_effective_policy

    _, sessions = database
    configured = policy().model_copy(
        update={
            "channels": [],
            "require_ack": False,
            "ack_timeout_minutes": 10,
            "intent": NotificationIntent.SAFETY,
        }
    )
    SQLAlchemyPolicyStore(sessions).save_snapshot([configured])
    runtime = service(sessions)
    actual = runtime.resolve(request(irreversible=True), principal="p")
    preview = await get_effective_policy(
        "policy.alarm",
        NotificationIntent.SAFETY,
        AutonomyMode.LIVE,
        irreversible=True,
        policy_registry=runtime.registry(),
    )
    assert preview.effective.channels == actual.channels
    assert Channel.PAGERDUTY in actual.channels
    assert not preview.effective.require_ack and not actual.require_ack
    assert preview.effective.ack_timeout_minutes == actual.ack_timeout_minutes
    with pytest.raises(ValueError, match="intent.*ACTIVE policy"):
        await get_effective_policy(
            "policy.alarm",
            NotificationIntent.INFORMATIONAL,
            AutonomyMode.LIVE,
            policy_registry=runtime.registry(),
        )


def test_real_runtime_intake_and_separate_process_activation_share_commit_order(database):
    """Actual durable intake holds revision authority until its work/audit commit."""
    from uns.runtime import Runtime

    url, sessions = database
    runtime = Runtime(url, create_tables=True)
    SQLAlchemyPolicyStore(sessions).save_snapshot([policy()])
    accepting = subprocess.Popen(
        [
            sys.executable,
            "-c",
            """
import json, os, sys
from uns.responses import SendNotificationRequest
from uns.runtime import Runtime
runtime = Runtime(os.environ["UNS_DATABASE_URL"])
original = runtime.policy_runtime.resolve
def gated(request, **kwargs):
    notification = original(request, **kwargs)
    print("resolved", flush=True)
    sys.stdin.readline()
    return notification
runtime.policy_runtime.resolve = gated
request = SendNotificationRequest.model_validate(json.loads(sys.stdin.readline()))
response = runtime.accept(request, principal="producer")
row = runtime.get(response.notification_id)
print(json.dumps({"notification": row["notification"], "events": runtime.events(response.notification_id)}), flush=True)
""",
        ],
        env=child_environment(url),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    activating = None
    try:
        accepting.stdin.write(request().model_dump_json() + "\n")
        accepting.stdin.flush()
        assert accepting.stdout.readline().strip() == "resolved"
        activating = subprocess.Popen(
            [
                sys.executable,
                "-c",
                """
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from db.policy_store import SQLAlchemyPolicyStore
from notification.policies import NotificationPolicy
engine = create_engine(os.environ["UNS_DATABASE_URL"])
@event.listens_for(engine, "before_cursor_execute")
def probe(conn, cursor, statement, parameters, context, executemany):
    if statement.startswith("UPDATE notification_policy_revision"):
        print("locking", flush=True)
SQLAlchemyPolicyStore(sessionmaker(engine)).save_snapshot([
    NotificationPolicy(notification_type="policy.alarm", version="2", channels=["EMAIL"], require_ack=True)
])
print("committed", flush=True)
""",
            ],
            env=child_environment(url),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert activating.stdout.readline().strip() == "locking"
        with selectors.DefaultSelector() as selector:
            selector.register(activating.stdout, selectors.EVENT_READ)
            assert not selector.select(timeout=0.2)
        accepted_output, accepted_error = accepting.communicate("\n", timeout=10)
        assert accepting.returncode == 0, accepted_error
        activation_output, activation_error = activating.communicate(timeout=10)
        assert activating.returncode == 0, activation_error
        assert "committed" in activation_output
        accepted = json.loads(accepted_output)
        assert accepted["notification"]["channels"] == ["SLACK"]
        assert accepted["notification"]["metadata"]["uns_resolution"]["snapshot_revision"] == 1
        acceptance_event = next(
            event for event in accepted["events"] if event["kind"] == "ACCEPTED"
        )
        assert acceptance_event["payload"]["snapshot_revision"] == 1
        later = runtime.accept(request(), principal="producer")
        later_notification = runtime.get(later.notification_id)["notification"]
        assert later_notification["channels"] == ["EMAIL"]
        assert later_notification["metadata"]["uns_resolution"]["snapshot_revision"] == 2
    finally:
        for child in (accepting, activating):
            if child is not None and child.poll() is None:
                child.kill()
                child.communicate()
        runtime.engine.dispose()
