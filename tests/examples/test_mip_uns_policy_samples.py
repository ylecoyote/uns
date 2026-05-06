from pathlib import Path

from notification.models import AutonomyMode, Channel, DeliveryMode, NotificationIntent
from notification.policies import PolicyRegistry
from notification.policy_loader import load_policies_from_directory

SAMPLE_DIR = Path("examples/policies/mip-uns")


def load_sample_registry() -> PolicyRegistry:
    registry = PolicyRegistry()
    loaded_count = load_policies_from_directory(SAMPLE_DIR, registry=registry)
    assert loaded_count == 3
    return registry


def test_mip_uns_sample_pack_loads_all_policies() -> None:
    registry = load_sample_registry()

    assert registry.get("safety.kill_switch") is not None
    assert registry.get("governance.approval_required") is not None
    assert registry.get("execution.slippage") is not None


def test_safety_kill_switch_demonstrates_live_guaranteed_ack_escalation() -> None:
    registry = load_sample_registry()
    policy = registry.get("safety.kill_switch")

    assert policy is not None
    assert policy.delivery_mode == DeliveryMode.GUARANTEED
    assert (
        policy.get_delivery_mode_for_mode(AutonomyMode.PREVIEW, NotificationIntent.SAFETY)
        == DeliveryMode.BEST_EFFORT
    )
    assert (
        policy.get_delivery_mode_for_mode(AutonomyMode.LIVE, NotificationIntent.SAFETY)
        == DeliveryMode.GUARANTEED
    )
    assert policy.get_require_ack_for_mode(AutonomyMode.LIVE) is True
    assert policy.get_channels_for_mode(AutonomyMode.LIVE) == [
        Channel.SLACK,
        Channel.WEBSOCKET,
    ]


def test_execution_slippage_demonstrates_best_effort_dedup() -> None:
    registry = load_sample_registry()
    policy = registry.get("execution.slippage")

    assert policy is not None
    assert policy.delivery_mode == DeliveryMode.BEST_EFFORT
    assert policy.dedup_window_seconds == 300
    assert policy.get_require_ack_for_mode(AutonomyMode.LIVE) is False
    assert policy.get_channels_for_mode(AutonomyMode.LIVE) == [Channel.SLACK]
