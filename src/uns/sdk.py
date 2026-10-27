"""UNS-branded SDK aliases."""

from notification.sdk import NotificationSDK, configure_sdk, create_sdk, get_sdk

SignalClient = NotificationSDK
create_signal_client = create_sdk
get_signal_client = get_sdk
configure_signal_client = configure_sdk

__all__ = [
    "SignalClient",
    "configure_signal_client",
    "create_signal_client",
    "get_signal_client",
]
