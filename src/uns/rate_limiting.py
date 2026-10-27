"""UNS-branded rate limiting aliases."""

from notification.rate_limiting import (
    DEFAULT_RATE_LIMITS,
    RateLimitConfig,
    RateLimiter,
    TokenBucket,
    acquire_rate_limit,
    configure_rate_limiter,
    get_rate_limiter,
)

__all__ = [
    "DEFAULT_RATE_LIMITS",
    "RateLimitConfig",
    "RateLimiter",
    "TokenBucket",
    "acquire_rate_limit",
    "configure_rate_limiter",
    "get_rate_limiter",
]
