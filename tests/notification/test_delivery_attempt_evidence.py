"""Provider results survive lease loss; SMTP timeout does not admit a later send."""

import asyncio
import contextlib
import smtplib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from notification.adapters.base import (
    AdapterStatus,
    BaseAdapter,
    DeliveryLeaseLostError,
    DeliveryResult,
    HealthCheckResult,
)
from notification.adapters.email import EmailAdapter, EmailConfig
from notification.models import Channel, DeliveryMode, Notification
from notification.policies import PolicyRegistry, configure_policy_registry
from notification.rate_limiting import configure_rate_limiter
from notification.service import DeliveryEvidenceError, DeliveryService, SimpleAdapterRegistry


class Adapter(BaseAdapter):
    def __init__(self, channel, effect=None):
        self._channel, self.effect = channel, effect
        self.calls = 0

    @property
    def channel(self):
        return self._channel

    async def deliver(self, notification):
        self.calls += 1
        if self.effect:
            await self.effect()
        return DeliveryResult(True, self.channel, message_id="accepted")

    async def health_check(self):
        return HealthCheckResult(AdapterStatus.HEALTHY, "test")


@pytest.fixture
def notification():
    configure_policy_registry(registry=PolicyRegistry())
    configure_rate_limiter({})
    return Notification(
        notification_type="test.attempt-evidence",
        intent="SAFETY",
        title="Alarm",
        message="Alarm",
        source="test",
        autonomy_context={
            "agent_id": "00000000-0000-0000-0000-000000000001",
            "autonomy_mode": "LIVE",
        },
        channels=[Channel.EMAIL, Channel.PAGERDUTY],
        delivery_mode=DeliveryMode.GUARANTEED,
        require_ack=False,
    )


def email_adapter(timeout=1, *, tls=False):
    return EmailAdapter(
        EmailConfig(
            "test.invalid",
            25,
            "user",
            "password",
            "sender@example.invalid",
            ["recipient@example.invalid"],
            use_tls=tls,
            timeout_seconds=timeout,
            retry_attempts=3,
        )
    )


def service(*adapters, timeout=0.05):
    registry = SimpleAdapterRegistry()
    for adapter in adapters:
        registry.register(adapter)
    return DeliveryService(registry, check_deduplication=False, adapter_timeout_seconds=timeout)


async def wait_event(event):
    async with asyncio.timeout(2):
        while not event.is_set():
            await asyncio.sleep(0.001)


class SMTPBarrier:
    def __init__(self, stage=None, *, cleanup_fails=False):
        self.stage = stage
        self.cleanup_fails = cleanup_fails
        self.entered, self.release, self.closed = (threading.Event() for _ in range(3))
        self.operations, self.timeouts = [], []
        self.sock = self

    def block(self, stage):
        self.operations.append(stage)
        if stage == self.stage:
            self.entered.set()
            assert self.release.wait(3), "test did not release SMTP barrier"

    def connect(self, *args, **kwargs):
        self.timeouts.append(kwargs["timeout"])
        self.block("connect")
        return self

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def starttls(self, **kwargs):
        self.block("tls")

    def login(self, *args):
        self.block("login")

    def sendmail(self, *args):
        self.block("send")

    def close(self):
        self.closed.set()
        if self.cleanup_fails:
            raise OSError("cleanup failed after acceptance")


@pytest.mark.asyncio
async def test_smtp_lease_recheck_is_not_an_extra_send_attempt(notification, monkeypatch):
    smtp = SMTPBarrier(cleanup_fails=True)
    monkeypatch.setattr(smtplib, "SMTP", smtp.connect)
    starts, checks, results = [], [], []
    delivered = await service(email_adapter(), timeout=1).deliver(
        notification,
        before_attempt=starts.append,
        check_lease=checks.append,
        after_attempt=results.append,
    )
    assert delivered.channels_succeeded == [Channel.EMAIL]
    assert starts == checks == [Channel.EMAIL]
    assert smtp.operations.count("send") == 1
    assert len(results) == 1 and results[0].success
    assert results[0].metadata["provider_outcome"] == "SUCCEEDED"


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["connect", "tls", "login"])
async def test_outer_timeout_prevents_send_after_smtp_preparation(notification, monkeypatch, stage):
    smtp = SMTPBarrier(stage)
    monkeypatch.setattr(smtplib, "SMTP", smtp.connect)
    fallback = Adapter(Channel.PAGERDUTY)
    starts, results = [], []
    task = asyncio.create_task(
        service(email_adapter(tls=stage == "tls"), fallback).deliver(
            notification,
            before_attempt=starts.append,
            after_attempt=results.append,
        )
    )
    try:
        await wait_event(smtp.entered)
        delivered = await asyncio.wait_for(task, 1)
        assert delivered.channels_succeeded == [Channel.PAGERDUTY]
        assert fallback.calls == 1
        email_result = next(r for r in results if r.channel == Channel.EMAIL)
        assert email_result.metadata == {
            "provider_outcome": "NOT_STARTED",
            "provider_effect_may_have_occurred": False,
        }
        assert Channel.EMAIL not in starts
    finally:
        smtp.release.set()
        await wait_event(smtp.closed)
    assert "send" not in smtp.operations
    assert all(0 < value <= 0.05 for value in smtp.timeouts)


@pytest.mark.asyncio
@pytest.mark.parametrize("inner_timeout", [False, True])
async def test_timeout_of_admitted_smtp_send_stays_unknown_after_late_success(
    notification, monkeypatch, inner_timeout
):
    smtp = SMTPBarrier("send")
    monkeypatch.setattr(smtplib, "SMTP", smtp.connect)
    fallback = Adapter(Channel.PAGERDUTY)
    starts, results = [], []
    delivery = service(
        email_adapter(timeout=0.05 if inner_timeout else 1),
        fallback,
        timeout=0.5 if inner_timeout else 0.05,
    )
    task = asyncio.create_task(
        delivery.deliver(
            notification,
            before_attempt=starts.append,
            after_attempt=results.append,
        )
    )
    try:
        await wait_event(smtp.entered)
        delivered = await asyncio.wait_for(task, 1)
        assert delivered.channels_succeeded == [Channel.PAGERDUTY]
        email_result = next(r for r in results if r.channel == Channel.EMAIL)
        assert not email_result.success
        assert email_result.metadata == {
            "provider_outcome": "UNKNOWN",
            "provider_effect_may_have_occurred": True,
        }
        assert starts.count(Channel.EMAIL) == 1
        assert smtp.operations.count("send") == 1
        evidence_count = len(results)
    finally:
        smtp.release.set()
        await wait_event(smtp.closed)
    assert len(results) == evidence_count
    assert email_result.metadata["provider_outcome"] == "UNKNOWN"
    assert smtp.operations.count("send") == 1


@pytest.mark.asyncio
async def test_disconnect_during_smtp_send_is_unknown_without_internal_retry(
    notification, monkeypatch
):
    smtp = SMTPBarrier()
    monkeypatch.setattr(smtplib, "SMTP", smtp.connect)

    def disconnected(*args):
        smtp.operations.append("send")
        raise smtplib.SMTPServerDisconnected("connection lost during DATA response")

    monkeypatch.setattr(smtp, "sendmail", disconnected)
    results, starts = [], []
    delivered = await service(email_adapter(), Adapter(Channel.PAGERDUTY), timeout=1).deliver(
        notification,
        before_attempt=starts.append,
        after_attempt=results.append,
    )
    assert delivered.channels_succeeded == [Channel.PAGERDUTY]
    assert smtp.operations.count("send") == starts.count(Channel.EMAIL) == 1
    assert smtp.closed.is_set()
    email_result = next(r for r in results if r.channel == Channel.EMAIL)
    assert not email_result.success
    assert email_result.metadata["provider_outcome"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_queued_executor_timeout_does_not_connect(notification, monkeypatch):
    smtp = SMTPBarrier()
    monkeypatch.setattr(smtplib, "SMTP", smtp.connect)
    fallback = Adapter(Channel.PAGERDUTY)
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original = loop.run_in_executor
    results = []
    with ThreadPoolExecutor(max_workers=1) as executor:
        blocker = executor.submit(release.wait, 3)
        monkeypatch.setattr(
            loop, "run_in_executor", lambda _pool, fn, *args: original(executor, fn, *args)
        )
        try:
            delivered = await service(email_adapter(), fallback).deliver(
                notification, after_attempt=results.append
            )
            assert delivered.channels_succeeded == [Channel.PAGERDUTY]
        finally:
            release.set()
            blocker.result(timeout=1)
    assert not smtp.operations
    assert results[0].metadata["provider_outcome"] == "NOT_STARTED"


@pytest.mark.asyncio
async def test_cancel_during_blocking_start_guard_does_not_admit_send(notification, monkeypatch):
    smtp = SMTPBarrier()
    monkeypatch.setattr(smtplib, "SMTP", smtp.connect)
    entered, release = threading.Event(), threading.Event()
    results = []

    def before_attempt(channel):
        if channel == Channel.EMAIL:
            entered.set()
            assert release.wait(3)

    task = asyncio.create_task(
        service(email_adapter(), Adapter(Channel.PAGERDUTY)).deliver(
            notification,
            before_attempt=before_attempt,
            after_attempt=results.append,
        )
    )
    try:
        await wait_event(entered)
        delivered = await asyncio.wait_for(task, 1)
        assert delivered.channels_succeeded == [Channel.PAGERDUTY]
    finally:
        release.set()
        await wait_event(smtp.closed)
    assert "send" not in smtp.operations
    assert results[0].metadata["provider_outcome"] == "NOT_STARTED"


@pytest.mark.asyncio
@pytest.mark.parametrize("observer_fails", [False, True])
async def test_external_cancellation_propagates_without_fallback(
    notification, monkeypatch, observer_fails
):
    smtp = SMTPBarrier("send")
    monkeypatch.setattr(smtplib, "SMTP", smtp.connect)
    fallback = Adapter(Channel.PAGERDUTY)
    results = []

    def observe(result):
        results.append(result)
        if observer_fails:
            raise OSError("audit storage unavailable")

    task = asyncio.create_task(
        service(email_adapter(), fallback, timeout=1).deliver(
            notification,
            after_attempt=observe,
        )
    )
    try:
        await wait_event(smtp.entered)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert fallback.calls == 0
        assert results[0].metadata["provider_outcome"] == "UNKNOWN"
    finally:
        smtp.release.set()
        await wait_event(smtp.closed)
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_first", [False, True])
async def test_completed_best_effort_outcome_survives_other_channel_lease_loss(
    notification, blocked_first
):
    notification = notification.model_copy(
        update={
            "delivery_mode": DeliveryMode.BEST_EFFORT,
            "channels": (
                [Channel.EMAIL, Channel.SLACK] if blocked_first else [Channel.SLACK, Channel.EMAIL]
            ),
        }
    )
    results = []

    def before_attempt(channel):
        if channel == Channel.EMAIL:
            raise DeliveryLeaseLostError("takeover")

    async def finish_later():
        await asyncio.sleep(0)

    delivery = service(Adapter(Channel.EMAIL), Adapter(Channel.SLACK, finish_later))
    with pytest.raises(DeliveryLeaseLostError):
        await delivery.deliver(
            notification,
            before_attempt=before_attempt,
            after_attempt=results.append,
        )
    assert len(results) == 1
    assert results[0].channel == Channel.SLACK and results[0].success
    assert results[0].message_id == "accepted"


@pytest.mark.asyncio
async def test_websocket_completion_survives_persistent_lease_loss(notification):
    notification = notification.model_copy(update={"channels": [Channel.WEBSOCKET, Channel.SLACK]})
    results = []

    def before_attempt(channel):
        if channel == Channel.SLACK:
            raise DeliveryLeaseLostError("takeover")

    with pytest.raises(DeliveryLeaseLostError):
        await service(Adapter(Channel.WEBSOCKET), Adapter(Channel.SLACK)).deliver(
            notification,
            before_attempt=before_attempt,
            after_attempt=results.append,
        )
    assert len(results) == 1
    assert results[0].channel == Channel.WEBSOCKET and results[0].success


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [DeliveryMode.GUARANTEED, DeliveryMode.BEST_EFFORT])
async def test_success_evidence_storage_failure_cannot_become_provider_failure(notification, mode):
    notification = notification.model_copy(update={"delivery_mode": mode})
    email, fallback = Adapter(Channel.EMAIL), Adapter(Channel.PAGERDUTY)

    def fail_observer(result):
        if result.channel == Channel.EMAIL:
            raise OSError("audit storage unavailable")

    with pytest.raises(DeliveryEvidenceError) as failure:
        await service(email, fallback).deliver(notification, after_attempt=fail_observer)
    assert failure.value.result.success
    assert failure.value.result.channel == Channel.EMAIL
    assert isinstance(failure.value.__cause__, OSError)
    if mode == DeliveryMode.GUARANTEED:
        assert fallback.calls == 0
