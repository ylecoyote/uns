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
    from notification.models import Notification, NotificationIntent
    from notification.sdk import NotificationSDK

    assert agsignal.SignalClient is NotificationSDK
    assert agsignal.GovernanceSignal is Notification
    assert agsignal.SignalIntent is NotificationIntent


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
