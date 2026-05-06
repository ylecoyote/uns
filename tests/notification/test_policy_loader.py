from __future__ import annotations

import pytest
import yaml

from notification.models import AutonomyMode, Channel, DeliveryMode
from notification.policies import NotificationPolicy, PolicyRegistry, PolicyStatus
from notification.policy_loader import (
    compute_policy_content_hash,
    load_policies_from_directory,
    load_policy_from_yaml,
)

SAMPLE_POLICY = {
    "notification_type": "safety.kill_switch",
    "version": "1.0.0",
    "status": "ACTIVE",
    "delivery_mode": "GUARANTEED",
    "channels": {
        "PREVIEW": ["WEBSOCKET"],
        "SHADOW": ["SLACK", "WEBSOCKET"],
        "LIVE": ["SLACK", "WEBSOCKET", "PAGERDUTY"],
    },
    "require_ack": {
        "PREVIEW": False,
        "SHADOW": False,
        "LIVE": True,
    },
    "dedup_window_seconds": 600,
}


def test_load_policy_from_yaml_registers_mode_routing(tmp_path):
    policy_file = tmp_path / "safety_kill_switch.yaml"
    policy_file.write_text(yaml.safe_dump(SAMPLE_POLICY))

    registry = PolicyRegistry()
    policy = load_policy_from_yaml(policy_file, registry=registry)

    assert policy.notification_type == "safety.kill_switch"
    assert policy.version == "1.0.0"
    assert policy.status == PolicyStatus.ACTIVE
    assert policy.delivery_mode == DeliveryMode.GUARANTEED
    assert policy.get_channels_for_mode(AutonomyMode.LIVE) == [
        Channel.SLACK,
        Channel.WEBSOCKET,
        Channel.PAGERDUTY,
    ]
    assert policy.get_require_ack_for_mode(AutonomyMode.LIVE) is True
    assert registry.get_sync("safety.kill_switch") == policy


def test_load_policies_from_directory_loads_yaml_and_yml(tmp_path):
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yml"
    first.write_text(yaml.safe_dump(SAMPLE_POLICY))
    second.write_text(
        yaml.safe_dump(
            {
                **SAMPLE_POLICY,
                "notification_type": "governance.approval_required",
                "delivery_mode": "BEST_EFFORT",
            }
        )
    )

    registry = PolicyRegistry()
    count = load_policies_from_directory(tmp_path, registry=registry)

    assert count == 2
    assert registry.get_sync("safety.kill_switch") is not None
    assert registry.get_sync("governance.approval_required") is not None


def test_policy_hash_ignores_description_and_key_order():
    left = {
        "notification_type": "execution.slippage",
        "version": "1.0.0",
        "description": "human text",
        "channels": {"LIVE": ["SLACK"]},
    }
    right = {
        "channels": {"LIVE": ["SLACK"]},
        "description": "changed human text",
        "version": "1.0.0",
        "notification_type": "execution.slippage",
    }

    assert compute_policy_content_hash(left) == compute_policy_content_hash(right)


def test_notification_policy_from_dict_matches_yaml_contract():
    policy = NotificationPolicy.from_dict(SAMPLE_POLICY)

    assert policy.notification_type == "safety.kill_switch"
    assert policy.status == PolicyStatus.ACTIVE
    assert policy.get_channels_for_mode(AutonomyMode.PREVIEW) == [Channel.WEBSOCKET]
    assert policy.get_require_ack_for_mode(AutonomyMode.LIVE) is True


def test_load_policy_from_yaml_rejects_empty_file(tmp_path):
    policy_file = tmp_path / "empty.yaml"
    policy_file.write_text("")

    with pytest.raises(ValueError, match="Empty or null"):
        load_policy_from_yaml(policy_file)


def test_loads_extracted_mip_policy_directory():
    registry = PolicyRegistry()

    count = load_policies_from_directory("config/notification_policies", registry=registry)

    assert count == 3
    safety = registry.get_sync("safety.kill_switch")
    assert safety is not None
    assert safety.version == "2.0.0"
    assert safety.get_channels_for_mode(AutonomyMode.LIVE) == [
        Channel.SLACK,
        Channel.WEBSOCKET,
    ]
    assert safety.get_require_ack_for_mode(AutonomyMode.LIVE) is True
