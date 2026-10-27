"""Tests for UNS-branded public import aliases."""

from __future__ import annotations


def test_signal_client_aliases_notification_sdk() -> None:
    from notification.sdk import NotificationSDK
    from uns.sdk import SignalClient

    assert SignalClient is NotificationSDK


def test_governance_signal_aliases_notification_model() -> None:
    from notification.models import Notification, NotificationIntent
    from uns.models import GovernanceSignal, SignalIntent

    assert GovernanceSignal is Notification
    assert SignalIntent is NotificationIntent


def test_uns_root_exports_public_aliases() -> None:
    import uns
    from notification.interfaces import LoggingAcknowledgmentCallback
    from notification.models import Notification, NotificationIntent
    from notification.policies import NotificationPolicy, PolicyRegistry
    from notification.sdk import NotificationSDK

    assert uns.SignalClient is NotificationSDK
    assert uns.GovernanceSignal is Notification
    assert uns.SignalIntent is NotificationIntent
    assert uns.SignalPolicy is NotificationPolicy
    assert uns.PolicyRegistry is PolicyRegistry
    assert uns.LoggingAcknowledgmentCallback is LoggingAcknowledgmentCallback


def test_uns_policy_aliases_cover_configuration_api() -> None:
    from notification.policies import NotificationPolicy
    from uns.policies import SignalPolicy

    assert SignalPolicy is NotificationPolicy


def test_uns_interface_aliases_cover_callbacks() -> None:
    from notification.interfaces import NotificationContextProvider
    from uns.interfaces import SignalContextProvider

    assert SignalContextProvider is NotificationContextProvider


def test_uns_adapter_aliases_cover_delivery_api() -> None:
    from notification.adapters import SlackConfig as NotificationSlackConfig
    from notification.adapters import get_adapter as notification_get_adapter
    from uns.adapters import SlackConfig, get_adapter

    assert SlackConfig is NotificationSlackConfig
    assert get_adapter is notification_get_adapter


def test_uns_runtime_helper_aliases_cover_lower_level_api() -> None:
    from notification.deduplication import RedisDeduplicationStore as NotificationRedisStore
    from notification.rate_limiting import RateLimitConfig as NotificationRateLimitConfig
    from uns.deduplication import RedisDeduplicationStore
    from uns.rate_limiting import RateLimitConfig

    assert RedisDeduplicationStore is NotificationRedisStore
    assert RateLimitConfig is NotificationRateLimitConfig


def test_uns_integrations_reexport_app_boundary() -> None:
    from notification.integrations import AppSignalAdapter as NotificationAppSignalAdapter
    from uns.integrations import AppSignalAdapter

    assert AppSignalAdapter is NotificationAppSignalAdapter


def test_historical_notification_imports_still_work() -> None:
    from notification.models import Notification, NotificationIntent
    from notification.sdk import NotificationSDK

    assert Notification.__name__ == "Notification"
    assert NotificationIntent.SAFETY.value == "SAFETY"
    assert NotificationSDK.__name__ == "NotificationSDK"


def test_uns_reexports_every_public_notification_symbol() -> None:
    """Every name in notification.__all__ must be importable from uns."""
    import notification
    import uns

    missing = [name for name in notification.__all__ if not hasattr(uns, name)]
    assert not missing, f"Missing from uns: {missing}"
