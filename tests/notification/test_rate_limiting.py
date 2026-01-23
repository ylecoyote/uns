"""Tests for the rate limiting module.

Tests cover:
- Token bucket algorithm behavior
- Per-channel rate limiting
- Configuration validation
- Thread safety (basic)
- Global rate limiter interface
"""

import pytest

from notification.models import Channel
from notification.rate_limiting import (
    DEFAULT_RATE_LIMITS,
    RateLimitConfig,
    RateLimiter,
    TokenBucket,
    acquire_rate_limit,
    configure_rate_limiter,
    get_rate_limiter,
)


class MockTimeProvider:
    """Mock time provider for deterministic testing."""

    def __init__(self, initial_time: float = 0.0) -> None:
        self._time = initial_time

    def time(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        """Advance time by the specified number of seconds."""
        self._time += seconds


class TestRateLimitConfig:
    """Tests for RateLimitConfig validation."""

    def test_valid_config(self) -> None:
        """Valid configuration should be accepted."""
        config = RateLimitConfig(tokens_per_second=1.0, bucket_size=10)
        assert config.tokens_per_second == 1.0
        assert config.bucket_size == 10

    def test_zero_tokens_per_second_raises(self) -> None:
        """Zero tokens_per_second should raise ValueError."""
        with pytest.raises(ValueError, match="tokens_per_second must be positive"):
            RateLimitConfig(tokens_per_second=0, bucket_size=10)

    def test_negative_tokens_per_second_raises(self) -> None:
        """Negative tokens_per_second should raise ValueError."""
        with pytest.raises(ValueError, match="tokens_per_second must be positive"):
            RateLimitConfig(tokens_per_second=-1.0, bucket_size=10)

    def test_zero_bucket_size_raises(self) -> None:
        """Zero bucket_size should raise ValueError."""
        with pytest.raises(ValueError, match="bucket_size must be positive"):
            RateLimitConfig(tokens_per_second=1.0, bucket_size=0)

    def test_negative_bucket_size_raises(self) -> None:
        """Negative bucket_size should raise ValueError."""
        with pytest.raises(ValueError, match="bucket_size must be positive"):
            RateLimitConfig(tokens_per_second=1.0, bucket_size=-5)


class TestTokenBucket:
    """Tests for TokenBucket implementation."""

    def test_initial_tokens_equals_bucket_size(self) -> None:
        """Bucket should start with full capacity."""
        config = RateLimitConfig(tokens_per_second=1.0, bucket_size=10)
        bucket = TokenBucket(config=config)
        assert bucket.get_available_tokens() == 10.0

    def test_acquire_reduces_tokens(self) -> None:
        """Acquiring tokens should reduce available count."""
        config = RateLimitConfig(tokens_per_second=1.0, bucket_size=10)
        time_provider = MockTimeProvider()
        bucket = TokenBucket(config=config)
        bucket._time_provider = time_provider
        bucket._last_refill = time_provider.time()

        assert bucket.acquire(3)
        assert bucket.get_available_tokens() == 7.0

    def test_acquire_returns_false_when_insufficient(self) -> None:
        """Acquire should return False when not enough tokens."""
        config = RateLimitConfig(tokens_per_second=1.0, bucket_size=5)
        time_provider = MockTimeProvider()
        bucket = TokenBucket(config=config)
        bucket._time_provider = time_provider
        bucket._last_refill = time_provider.time()

        assert bucket.acquire(5)  # Use all tokens
        assert bucket.get_available_tokens() == 0.0
        assert not bucket.acquire(1)  # Should fail

    def test_tokens_refill_over_time(self) -> None:
        """Tokens should refill based on elapsed time."""
        config = RateLimitConfig(tokens_per_second=2.0, bucket_size=10)
        time_provider = MockTimeProvider()
        bucket = TokenBucket(config=config)
        bucket._time_provider = time_provider
        bucket._last_refill = time_provider.time()

        # Use all tokens
        assert bucket.acquire(10)
        assert bucket.get_available_tokens() == 0.0

        # Advance time by 1 second, should add 2 tokens
        time_provider.advance(1.0)
        assert bucket.get_available_tokens() == 2.0

    def test_tokens_do_not_exceed_bucket_size(self) -> None:
        """Tokens should not exceed bucket capacity."""
        config = RateLimitConfig(tokens_per_second=10.0, bucket_size=5)
        time_provider = MockTimeProvider()
        bucket = TokenBucket(config=config)
        bucket._time_provider = time_provider
        bucket._last_refill = time_provider.time()

        # Advance time significantly
        time_provider.advance(100.0)
        # Should cap at bucket_size
        assert bucket.get_available_tokens() == 5.0

    def test_acquire_zero_tokens_raises(self) -> None:
        """Acquiring zero tokens should raise ValueError."""
        config = RateLimitConfig(tokens_per_second=1.0, bucket_size=10)
        bucket = TokenBucket(config=config)

        with pytest.raises(ValueError, match="tokens must be positive"):
            bucket.acquire(0)

    def test_acquire_negative_tokens_raises(self) -> None:
        """Acquiring negative tokens should raise ValueError."""
        config = RateLimitConfig(tokens_per_second=1.0, bucket_size=10)
        bucket = TokenBucket(config=config)

        with pytest.raises(ValueError, match="tokens must be positive"):
            bucket.acquire(-1)

    def test_time_until_available_when_tokens_available(self) -> None:
        """time_until_available should return 0 when tokens are available."""
        config = RateLimitConfig(tokens_per_second=1.0, bucket_size=10)
        time_provider = MockTimeProvider()
        bucket = TokenBucket(config=config)
        bucket._time_provider = time_provider
        bucket._last_refill = time_provider.time()

        assert bucket.time_until_available(5) == 0.0

    def test_time_until_available_when_tokens_needed(self) -> None:
        """time_until_available should calculate correct wait time."""
        config = RateLimitConfig(tokens_per_second=2.0, bucket_size=10)
        time_provider = MockTimeProvider()
        bucket = TokenBucket(config=config)
        bucket._time_provider = time_provider
        bucket._last_refill = time_provider.time()

        # Use all tokens
        bucket.acquire(10)

        # Need 4 tokens at 2 tokens/sec = 2 seconds wait
        assert bucket.time_until_available(4) == 2.0

    def test_time_until_available_zero_tokens_raises(self) -> None:
        """time_until_available with zero tokens should raise ValueError."""
        config = RateLimitConfig(tokens_per_second=1.0, bucket_size=10)
        bucket = TokenBucket(config=config)

        with pytest.raises(ValueError, match="tokens must be positive"):
            bucket.time_until_available(0)


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_default_config_applied(self) -> None:
        """Rate limiter should use default config when none provided."""
        limiter = RateLimiter()
        # Should be able to acquire from any default channel
        assert limiter.acquire_rate_limit(Channel.SLACK)
        assert limiter.acquire_rate_limit(Channel.WEBSOCKET)

    def test_custom_config_overrides_defaults(self) -> None:
        """Custom config should override defaults."""
        custom_config = {Channel.SLACK: RateLimitConfig(tokens_per_second=0.01, bucket_size=1)}
        time_provider = MockTimeProvider()
        limiter = RateLimiter(config=custom_config, time_provider=time_provider)

        # First acquire should succeed (bucket size = 1)
        assert limiter.acquire_rate_limit(Channel.SLACK)
        # Second should fail (no tokens left)
        assert not limiter.acquire_rate_limit(Channel.SLACK)

    def test_acquire_rate_limit_returns_false_when_exceeded(self) -> None:
        """acquire_rate_limit should return False when rate limit exceeded."""
        config = {Channel.EMAIL: RateLimitConfig(tokens_per_second=0.01, bucket_size=2)}
        time_provider = MockTimeProvider()
        limiter = RateLimiter(config=config, time_provider=time_provider)

        assert limiter.acquire_rate_limit(Channel.EMAIL)
        assert limiter.acquire_rate_limit(Channel.EMAIL)
        assert not limiter.acquire_rate_limit(Channel.EMAIL)  # Exceeded

    def test_channels_are_independent(self) -> None:
        """Each channel should have its own rate limit."""
        config = {
            Channel.SLACK: RateLimitConfig(tokens_per_second=0.01, bucket_size=1),
            Channel.EMAIL: RateLimitConfig(tokens_per_second=0.01, bucket_size=1),
        }
        time_provider = MockTimeProvider()
        limiter = RateLimiter(config=config, time_provider=time_provider)

        # Exhaust Slack
        assert limiter.acquire_rate_limit(Channel.SLACK)
        assert not limiter.acquire_rate_limit(Channel.SLACK)

        # Email should still work
        assert limiter.acquire_rate_limit(Channel.EMAIL)

    def test_get_available_tokens(self) -> None:
        """get_available_tokens should return correct count."""
        config = {Channel.SLACK: RateLimitConfig(tokens_per_second=1.0, bucket_size=10)}
        time_provider = MockTimeProvider()
        limiter = RateLimiter(config=config, time_provider=time_provider)

        limiter.acquire_rate_limit(Channel.SLACK, tokens=3)
        assert limiter.get_available_tokens(Channel.SLACK) == 7.0

    def test_time_until_available(self) -> None:
        """time_until_available should return correct wait time."""
        config = {Channel.SLACK: RateLimitConfig(tokens_per_second=2.0, bucket_size=10)}
        time_provider = MockTimeProvider()
        limiter = RateLimiter(config=config, time_provider=time_provider)

        # Use all tokens
        limiter.acquire_rate_limit(Channel.SLACK, tokens=10)

        # Need 4 tokens at 2/sec = 2 seconds
        assert limiter.time_until_available(Channel.SLACK, tokens=4) == 2.0

    def test_reset_specific_channel(self) -> None:
        """reset should reset specific channel when specified."""
        config = {
            Channel.SLACK: RateLimitConfig(tokens_per_second=0.01, bucket_size=1),
            Channel.EMAIL: RateLimitConfig(tokens_per_second=0.01, bucket_size=1),
        }
        time_provider = MockTimeProvider()
        limiter = RateLimiter(config=config, time_provider=time_provider)

        # Exhaust both
        limiter.acquire_rate_limit(Channel.SLACK)
        limiter.acquire_rate_limit(Channel.EMAIL)

        # Reset only Slack
        limiter.reset(Channel.SLACK)

        # Slack should work again
        assert limiter.acquire_rate_limit(Channel.SLACK)
        # Email should still be exhausted
        assert not limiter.acquire_rate_limit(Channel.EMAIL)

    def test_reset_all_channels(self) -> None:
        """reset without channel should reset all channels."""
        config = {
            Channel.SLACK: RateLimitConfig(tokens_per_second=0.01, bucket_size=1),
            Channel.EMAIL: RateLimitConfig(tokens_per_second=0.01, bucket_size=1),
        }
        time_provider = MockTimeProvider()
        limiter = RateLimiter(config=config, time_provider=time_provider)

        # Exhaust both
        limiter.acquire_rate_limit(Channel.SLACK)
        limiter.acquire_rate_limit(Channel.EMAIL)

        # Reset all
        limiter.reset()

        # Both should work again
        assert limiter.acquire_rate_limit(Channel.SLACK)
        assert limiter.acquire_rate_limit(Channel.EMAIL)


class TestGlobalRateLimiter:
    """Tests for global rate limiter functions."""

    def test_get_rate_limiter_returns_singleton(self) -> None:
        """get_rate_limiter should return the same instance."""
        # Configure fresh instance
        configure_rate_limiter()

        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        assert limiter1 is limiter2

    def test_configure_rate_limiter_replaces_instance(self) -> None:
        """configure_rate_limiter should replace the global instance."""
        limiter1 = get_rate_limiter()
        configure_rate_limiter()  # Create new instance
        limiter2 = get_rate_limiter()
        assert limiter1 is not limiter2

    def test_acquire_rate_limit_uses_global(self) -> None:
        """acquire_rate_limit should use global rate limiter."""
        config = {Channel.SLACK: RateLimitConfig(tokens_per_second=0.01, bucket_size=1)}
        time_provider = MockTimeProvider()
        configure_rate_limiter(config=config, time_provider=time_provider)

        assert acquire_rate_limit(Channel.SLACK)
        assert not acquire_rate_limit(Channel.SLACK)


class TestDefaultRateLimits:
    """Tests for default rate limit configuration."""

    def test_all_channels_have_defaults(self) -> None:
        """All channels should have default rate limits."""
        for channel in Channel:
            assert channel in DEFAULT_RATE_LIMITS

    def test_slack_rate_limit(self) -> None:
        """Slack should have reasonable rate limit."""
        config = DEFAULT_RATE_LIMITS[Channel.SLACK]
        assert config.tokens_per_second == 1.0
        assert config.bucket_size == 10

    def test_email_rate_limit(self) -> None:
        """Email should have conservative rate limit."""
        config = DEFAULT_RATE_LIMITS[Channel.EMAIL]
        assert config.tokens_per_second == 0.5
        assert config.bucket_size == 5

    def test_websocket_rate_limit(self) -> None:
        """WebSocket should have high rate limit."""
        config = DEFAULT_RATE_LIMITS[Channel.WEBSOCKET]
        assert config.tokens_per_second == 10.0
        assert config.bucket_size == 100

    def test_pagerduty_rate_limit(self) -> None:
        """PagerDuty should have very conservative rate limit."""
        config = DEFAULT_RATE_LIMITS[Channel.PAGERDUTY]
        assert config.tokens_per_second == 0.1
        assert config.bucket_size == 3


class TestBurstBehavior:
    """Tests for burst capacity behavior."""

    def test_burst_allows_multiple_immediate_requests(self) -> None:
        """Burst capacity should allow multiple immediate requests."""
        config = {Channel.SLACK: RateLimitConfig(tokens_per_second=1.0, bucket_size=5)}
        time_provider = MockTimeProvider()
        limiter = RateLimiter(config=config, time_provider=time_provider)

        # Should allow burst of 5
        for _ in range(5):
            assert limiter.acquire_rate_limit(Channel.SLACK)

        # 6th should fail
        assert not limiter.acquire_rate_limit(Channel.SLACK)

    def test_burst_refills_over_time(self) -> None:
        """After burst, capacity should refill."""
        config = {Channel.SLACK: RateLimitConfig(tokens_per_second=2.0, bucket_size=4)}
        time_provider = MockTimeProvider()
        limiter = RateLimiter(config=config, time_provider=time_provider)

        # Use burst capacity
        for _ in range(4):
            assert limiter.acquire_rate_limit(Channel.SLACK)

        assert not limiter.acquire_rate_limit(Channel.SLACK)

        # Wait 1 second - should add 2 tokens
        time_provider.advance(1.0)

        # Should allow 2 more
        assert limiter.acquire_rate_limit(Channel.SLACK)
        assert limiter.acquire_rate_limit(Channel.SLACK)
        assert not limiter.acquire_rate_limit(Channel.SLACK)


class TestMultiTokenAcquisition:
    """Tests for acquiring multiple tokens at once."""

    def test_acquire_multiple_tokens(self) -> None:
        """Should be able to acquire multiple tokens at once."""
        config = {Channel.SLACK: RateLimitConfig(tokens_per_second=1.0, bucket_size=10)}
        time_provider = MockTimeProvider()
        limiter = RateLimiter(config=config, time_provider=time_provider)

        assert limiter.acquire_rate_limit(Channel.SLACK, tokens=5)
        assert limiter.get_available_tokens(Channel.SLACK) == 5.0

    def test_acquire_multiple_fails_if_insufficient(self) -> None:
        """Multi-token acquire should fail if not enough tokens."""
        config = {Channel.SLACK: RateLimitConfig(tokens_per_second=1.0, bucket_size=3)}
        time_provider = MockTimeProvider()
        limiter = RateLimiter(config=config, time_provider=time_provider)

        assert not limiter.acquire_rate_limit(Channel.SLACK, tokens=5)
        # Tokens should not be consumed on failure
        assert limiter.get_available_tokens(Channel.SLACK) == 3.0
