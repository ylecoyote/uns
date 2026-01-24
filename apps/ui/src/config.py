"""Configuration for UNS UI Dashboard.

This module provides configuration management for the UI application,
including API base URL and other environment-based settings.

Environment Variables:
    UNS_API_BASE_URL: Base URL for the UNS backend API (default: http://localhost:8000)
    UNS_UI_DEBUG: Enable debug mode (default: false)
    UNS_UI_REQUEST_TIMEOUT: Request timeout in seconds (default: 30)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any


@dataclass(frozen=True)
class UIConfig:
    """Configuration for the UNS UI Dashboard.

    This configuration is immutable (frozen) to prevent accidental modification
    after initialization.

    Attributes:
        api_base_url: Base URL for the UNS backend API.
        debug: Whether debug mode is enabled.
        request_timeout: Request timeout in seconds.
        api_version: API version prefix (default: v1).
    """

    api_base_url: str = field(default="http://localhost:8000")
    debug: bool = field(default=False)
    request_timeout: int = field(default=30)
    api_version: str = field(default="v1")

    @property
    def api_prefix(self) -> str:
        """Return the full API prefix including base URL and version."""
        return f"{self.api_base_url.rstrip('/')}/api/{self.api_version}"

    def to_dict(self) -> dict[str, Any]:
        """Return configuration as a dictionary (for debugging/logging)."""
        return {
            "api_base_url": self.api_base_url,
            "debug": self.debug,
            "request_timeout": self.request_timeout,
            "api_version": self.api_version,
            "api_prefix": self.api_prefix,
        }


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse a string value to boolean."""
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


@lru_cache(maxsize=1)
def get_config() -> UIConfig:
    """Get the UI configuration from environment variables.

    This function is cached to ensure consistent configuration across
    the application lifetime.

    Returns:
        UIConfig: The configuration instance.

    Example:
        >>> config = get_config()
        >>> print(config.api_base_url)
        http://localhost:8000
    """
    return UIConfig(
        api_base_url=os.environ.get("UNS_API_BASE_URL", "http://localhost:8000"),
        debug=_parse_bool(os.environ.get("UNS_UI_DEBUG")),
        request_timeout=int(os.environ.get("UNS_UI_REQUEST_TIMEOUT", "30")),
        api_version=os.environ.get("UNS_API_VERSION", "v1"),
    )


def reset_config() -> None:
    """Reset the cached configuration.

    This is primarily useful for testing to ensure fresh configuration
    is loaded after environment changes.
    """
    get_config.cache_clear()
