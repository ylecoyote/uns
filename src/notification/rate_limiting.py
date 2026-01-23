"""Rate limiting for notification delivery channels.

This module implements token bucket rate limiting per channel to prevent
channel throttling and ensure fair resource usage.

The token bucket algorithm allows for:
- Sustained rate limiting over time
- Burst capacity for temporary spikes
- Per-channel independent limits
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Protocol

from notification.models import Channel


@dataclass
class RateLimitConfig:
    """Configuration for a channel's rate limit.

    Attributes:
        tokens_per_second: Rate at which tokens are replenished
        bucket_size: Maximum tokens that can accumulate (burst capacity)
    """

    tokens_per_second: float
    bucket_size: int

    def __post_init__(self) -> None:
        if self.tokens_per_second <= 0:
            raise ValueError("tokens_per_second must be positive")
        if self.bucket_size <= 0:
            raise ValueError("bucket_size must be positive")


# Default rate limits per channel
# These can be overridden via configuration
DEFAULT_RATE_LIMITS: dict[Channel, RateLimitConfig] = {
    Channel.SLACK: RateLimitConfig(tokens_per_second=1.0, bucket_size=10),
    Channel.EMAIL: RateLimitConfig(tokens_per_second=0.5, bucket_size=5),
    Channel.WEBSOCKET: RateLimitConfig(tokens_per_second=10.0, bucket_size=100),
    Channel.PAGERDUTY: RateLimitConfig(tokens_per_second=0.1, bucket_size=3),
}


class TimeProvider(Protocol):
    """Protocol for time providers, enabling testability."""

    def time(self) -> float:
        """Return current time as a float (seconds since epoch)."""
        ...


class SystemTimeProvider:
    """Default time provider using system time."""

    def time(self) -> float:
        return time.time()


@dataclass
class TokenBucket:
    """Token bucket implementation for rate limiting.

    Thread-safe implementation that allows for:
    - Configurable refill rate
    - Configurable bucket size (burst capacity)
    - Atomic token acquisition
    """

    config: RateLimitConfig
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: Lock = field(default_factory=Lock, repr=False)
    _time_provider: TimeProvider = field(default_factory=SystemTimeProvider, repr=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.config.bucket_size)
        self._last_refill = self._time_provider.time()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time since last refill."""
        now = self._time_provider.time()
        elapsed = now - self._last_refill
        tokens_to_add = elapsed * self.config.tokens_per_second
        self._tokens = min(self.config.bucket_size, self._tokens + tokens_to_add)
        self._last_refill = now

    def acquire(self, tokens: int = 1) -> bool:
        """Attempt to acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire (default 1)

        Returns:
            True if tokens were acquired, False if rate limit exceeded
        """
        if tokens <= 0:
            raise ValueError("tokens must be positive")

        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def get_available_tokens(self) -> float:
        """Get the current number of available tokens.

        Returns:
            Current token count (may be fractional)
        """
        with self._lock:
            self._refill()
            return self._tokens

    def time_until_available(self, tokens: int = 1) -> float:
        """Calculate time until specified tokens will be available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Seconds until tokens available, or 0.0 if already available
        """
        if tokens <= 0:
            raise ValueError("tokens must be positive")

        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                return 0.0
            tokens_needed = tokens - self._tokens
            return tokens_needed / self.config.tokens_per_second


class RateLimiter:
    """Rate limiter managing token buckets for all channels.

    Provides a simple interface for acquiring rate limits per channel,
    with support for custom configurations.
    """

    def __init__(
        self,
        config: dict[Channel, RateLimitConfig] | None = None,
        time_provider: TimeProvider | None = None,
    ) -> None:
        """Initialize rate limiter with optional custom configuration.

        Args:
            config: Optional custom rate limit configuration per channel.
                   Channels not specified use defaults.
            time_provider: Optional time provider for testing.
        """
        self._time_provider = time_provider or SystemTimeProvider()
        self._config = {**DEFAULT_RATE_LIMITS}
        if config:
            self._config.update(config)
        self._buckets: dict[Channel, TokenBucket] = {}
        self._lock = Lock()

    def _get_bucket(self, channel: Channel) -> TokenBucket:
        """Get or create a token bucket for a channel."""
        if channel not in self._buckets:
            with self._lock:
                # Double-check after acquiring lock
                if channel not in self._buckets:
                    bucket = TokenBucket(config=self._config[channel])
                    # Inject time provider for testing
                    bucket._time_provider = self._time_provider
                    # Reset last_refill to use the injected provider
                    bucket._last_refill = self._time_provider.time()
                    self._buckets[channel] = bucket
        return self._buckets[channel]

    def acquire_rate_limit(self, channel: Channel, tokens: int = 1) -> bool:
        """Attempt to acquire rate limit for a channel.

        Args:
            channel: The delivery channel to rate limit
            tokens: Number of tokens to acquire (default 1)

        Returns:
            True if rate limit acquired, False if rate limit exceeded
        """
        bucket = self._get_bucket(channel)
        return bucket.acquire(tokens)

    def get_available_tokens(self, channel: Channel) -> float:
        """Get available tokens for a channel.

        Args:
            channel: The delivery channel

        Returns:
            Number of available tokens
        """
        bucket = self._get_bucket(channel)
        return bucket.get_available_tokens()

    def time_until_available(self, channel: Channel, tokens: int = 1) -> float:
        """Get time until tokens are available for a channel.

        Args:
            channel: The delivery channel
            tokens: Number of tokens needed

        Returns:
            Seconds until tokens available
        """
        bucket = self._get_bucket(channel)
        return bucket.time_until_available(tokens)

    def reset(self, channel: Channel | None = None) -> None:
        """Reset rate limit state.

        Args:
            channel: Specific channel to reset, or None to reset all
        """
        with self._lock:
            if channel is None:
                self._buckets.clear()
            elif channel in self._buckets:
                del self._buckets[channel]


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance.

    Returns:
        The singleton RateLimiter instance
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def configure_rate_limiter(
    config: dict[Channel, RateLimitConfig] | None = None,
    time_provider: TimeProvider | None = None,
) -> RateLimiter:
    """Configure and return the global rate limiter.

    Args:
        config: Custom rate limit configuration
        time_provider: Custom time provider (for testing)

    Returns:
        The configured RateLimiter instance
    """
    global _rate_limiter
    _rate_limiter = RateLimiter(config=config, time_provider=time_provider)
    return _rate_limiter


def acquire_rate_limit(channel: Channel, tokens: int = 1) -> bool:
    """Acquire rate limit for a channel using the global rate limiter.

    This is the primary interface for rate limiting as specified in the PRD.

    Args:
        channel: The delivery channel to rate limit
        tokens: Number of tokens to acquire (default 1)

    Returns:
        True if rate limit acquired, False if rate limit exceeded
    """
    return get_rate_limiter().acquire_rate_limit(channel, tokens)
