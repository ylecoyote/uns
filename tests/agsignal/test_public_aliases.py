"""Tests for AGSignal-branded public import aliases."""

from __future__ import annotations


def test_signal_client_aliases_notification_sdk() -> None:
    from agsignal.sdk import SignalClient
    from notification.sdk import NotificationSDK

    assert SignalClient is NotificationSDK


def test_governance_signal_aliases_notification_model() -> None:
    from agsignal.models import GovernanceSignal, SignalIntent
    from notification.models import Notification, NotificationIntent

    assert GovernanceSignal is Notification
    assert SignalIntent is NotificationIntent


def test_agsignal_root_exports_public_aliases() -> None:
    import agsignal
    from notification.interfaces import LoggingAcknowledgmentCallback
    from notification.models import Notification, NotificationIntent
    from notification.policies import NotificationPolicy, PolicyRegistry
    from notification.sdk import NotificationSDK

    assert agsignal.SignalClient is NotificationSDK
    assert agsignal.GovernanceSignal is Notification
    assert agsignal.SignalIntent is NotificationIntent
    assert agsignal.SignalPolicy is NotificationPolicy
    assert agsignal.PolicyRegistry is PolicyRegistry
    assert agsignal.LoggingAcknowledgmentCallback is LoggingAcknowledgmentCallback


def test_agsignal_policy_aliases_cover_configuration_api() -> None:
    from agsignal.policies import SignalPolicy
    from notification.policies import NotificationPolicy

    assert SignalPolicy is NotificationPolicy


def test_agsignal_interface_aliases_cover_callbacks() -> None:
    from agsignal.interfaces import SignalContextProvider
    from notification.interfaces import NotificationContextProvider

    assert SignalContextProvider is NotificationContextProvider


def test_agsignal_adapter_aliases_cover_delivery_api() -> None:
    from agsignal.adapters import SlackConfig, get_adapter
    from notification.adapters import SlackConfig as NotificationSlackConfig
    from notification.adapters import get_adapter as notification_get_adapter

    assert SlackConfig is NotificationSlackConfig
    assert get_adapter is notification_get_adapter


def test_agsignal_runtime_helper_aliases_cover_lower_level_api() -> None:
    from agsignal.deduplication import RedisDeduplicationStore
    from agsignal.rate_limiting import RateLimitConfig
    from notification.deduplication import RedisDeduplicationStore as NotificationRedisStore
    from notification.rate_limiting import RateLimitConfig as NotificationRateLimitConfig

    assert RedisDeduplicationStore is NotificationRedisStore
    assert RateLimitConfig is NotificationRateLimitConfig


def test_agsignal_integrations_reexport_app_boundary() -> None:
    from agsignal.integrations import AppSignalAdapter
    from notification.integrations import AppSignalAdapter as NotificationAppSignalAdapter

    assert AppSignalAdapter is NotificationAppSignalAdapter


def test_historical_notification_imports_still_work() -> None:
    from notification.models import Notification, NotificationIntent
    from notification.sdk import NotificationSDK

    assert Notification.__name__ == "Notification"
    assert NotificationIntent.SAFETY.value == "SAFETY"
    assert NotificationSDK.__name__ == "NotificationSDK"


def test_agsignal_reexports_every_public_notification_symbol() -> None:
    """Every name in notification.__all__ must be importable from agsignal."""
    import agsignal
    import notification

    missing = [name for name in notification.__all__ if not hasattr(agsignal, name)]
    assert not missing, f"Missing from agsignal: {missing}"
