"""SLO telemetry aggregation and v1.0 certification receipt generator (`uns-slo-certify`).

Queries a durable SQLite or PostgreSQL ``uns`` database to produce a hash-verifiable
operational SLO report covering:
- Live operational progress gauges (`oldest_pending_age_seconds`,
  `oldest_due_attempt_lateness_seconds`, `overdue_ack_count`, `unknown_attempt_count`,
  `pending_callback_count`, `unresolved_failure_count`).
- Per-channel delivery volume, error rate, and `recording_only` vs. live external
  provider classification.
- Human response latency percentiles (`p50`, `p95`, `max` time-to-respond).
- Multi-week `v1.0` SLO gate evaluation and SHA-256 receipt digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from uns import __version__ as uns_version
from uns.runtime import Runtime, events, work


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return round(sorted_values[0], 3)
    idx = max(0, min(len(sorted_values) - 1, math.ceil((pct / 100.0) * len(sorted_values)) - 1))
    return round(sorted_values[idx], 3)


def compute_slo_report(
    database: str = "sqlite+pysqlite:///:memory:",
    *,
    window_days: float = 14.0,
    min_live_days_required: float = 14.0,
    max_error_rate_threshold: float = 0.05,
    max_pending_age_seconds: float = 3600.0,
    max_due_attempt_lateness_seconds: float = 300.0,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """Compute a deterministic, hash-verifiable SLO telemetry report from a UNS database."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    now_val = float(now_epoch if now_epoch is not None else time.time())
    cutoff_epoch = now_val - (window_days * 86400.0)

    runtime = Runtime(database, create_tables=True, clock=lambda: now_val)
    try:
        gauges = runtime.operational_progress()

        with runtime.sessions() as session:
            notif_rows = list(session.execute(select(work)).mappings())
            event_rows = list(
                session.execute(
                    select(events).where(events.c.at >= cutoff_epoch).order_by(events.c.at.asc())
                ).mappings()
            )
    finally:
        runtime.engine.dispose()

    accepted_at_by_id: dict[str, float] = {}
    settled_at_by_id: dict[str, float] = {}
    channel_stats: dict[str, dict[str, Any]] = {}
    earliest_event_at: float | None = None
    latest_event_at: float | None = None
    earliest_live_attempt_at: float | None = None
    latest_live_attempt_at: float | None = None
    total_live_provider_attempts = 0
    total_recording_only_attempts = 0

    for evt in event_rows:
        evt_at = float(evt["at"])
        if earliest_event_at is None or evt_at < earliest_event_at:
            earliest_event_at = evt_at
        if latest_event_at is None or evt_at > latest_event_at:
            latest_event_at = evt_at

        nid = str(evt["notification_id"])
        kind = str(evt["kind"])
        payload = evt["payload"] if isinstance(evt["payload"], dict) else {}

        if kind == "ACCEPTED" and nid not in accepted_at_by_id:
            accepted_at_by_id[nid] = evt_at
        elif kind in ("ACKED", "DISMISSED") and nid not in settled_at_by_id:
            settled_at_by_id[nid] = evt_at
        elif kind == "CHANNEL_ATTEMPT_RESULT":
            ch_name = str(payload.get("channel") or "UNKNOWN").upper()
            is_persistent_external = ch_name != "WEBSOCKET"
            bucket = channel_stats.setdefault(
                ch_name,
                {
                    "channel": ch_name,
                    "persistent_external": is_persistent_external,
                    "total_attempts": 0,
                    "succeeded_attempts": 0,
                    "failed_attempts": 0,
                    "unknown_attempts": 0,
                    "recording_only_attempts": 0,
                    "live_provider_attempts": 0,
                    "error_rate": 0.0,
                },
            )
            bucket["total_attempts"] += 1
            success = bool(payload.get("success"))
            raw_meta = payload.get("metadata")
            meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
            provider_outcome = str(meta.get("provider_outcome") or "").upper()
            recording_only = bool(meta.get("recording_only"))

            if success:
                bucket["succeeded_attempts"] += 1
            else:
                bucket["failed_attempts"] += 1
            if provider_outcome == "UNKNOWN":
                bucket["unknown_attempts"] += 1
            if recording_only:
                bucket["recording_only_attempts"] += 1
                if is_persistent_external:
                    total_recording_only_attempts += 1
            else:
                bucket["live_provider_attempts"] += 1
                if is_persistent_external and success:
                    total_live_provider_attempts += 1
                    if earliest_live_attempt_at is None or evt_at < earliest_live_attempt_at:
                        earliest_live_attempt_at = evt_at
                    if latest_live_attempt_at is None or evt_at > latest_live_attempt_at:
                        latest_live_attempt_at = evt_at

    for bucket in channel_stats.values():
        total = bucket["total_attempts"]
        bucket["error_rate"] = round(bucket["failed_attempts"] / total, 4) if total > 0 else 0.0

    # Filter notifications strictly accepted within the observation window
    window_notif_ids = set(accepted_at_by_id.keys())
    scoped_notifs = [r for r in notif_rows if str(r["id"]) in window_notif_ids]

    status_counts = {
        "total": len(scoped_notifs),
        "delivered": sum(1 for r in scoped_notifs if r["status"] == "DELIVERED"),
        "deduplicated": sum(1 for r in scoped_notifs if r["status"] == "DEDUPLICATED"),
        "pending": sum(1 for r in scoped_notifs if r["status"] == "PENDING"),
        "failed": sum(1 for r in scoped_notifs if r["status"] == "FAILED"),
        "dead_letter": sum(1 for r in scoped_notifs if r["dead_letter"]),
    }
    ack_counts = {
        "acked": sum(1 for r in scoped_notifs if r["ack_status"] == "ACKED"),
        "dismissed": sum(1 for r in scoped_notifs if r["ack_status"] == "DISMISSED"),
        "timed_out": sum(1 for r in scoped_notifs if r["ack_status"] == "TIMED_OUT"),
        "pending": sum(1 for r in scoped_notifs if r["ack_status"] == "PENDING"),
    }

    response_latencies = sorted(
        max(0.0, settled_at - accepted_at_by_id[nid])
        for nid, settled_at in settled_at_by_id.items()
        if nid in accepted_at_by_id
    )

    observed_span_days = (
        round(max(0.0, (latest_event_at - earliest_event_at) / 86400.0), 4)
        if earliest_event_at is not None and latest_event_at is not None
        else 0.0
    )
    observed_live_span_days = (
        round(max(0.0, (latest_live_attempt_at - earliest_live_attempt_at) / 86400.0), 4)
        if earliest_live_attempt_at is not None and latest_live_attempt_at is not None
        else 0.0
    )

    max_observed_error_rate = max(
        (b["error_rate"] for b in channel_stats.values() if b["persistent_external"]),
        default=0.0,
    )

    oldest_pending_age = gauges.get("oldest_pending_age_seconds")
    oldest_due_lateness = gauges.get("oldest_due_attempt_lateness_seconds")
    oldest_callback_age = gauges.get("oldest_callback_retry_age_seconds")
    gates = {
        "zero_overdue_acks": gauges["overdue_ack_count"] == 0,
        "zero_unresolved_dead_letters": gauges["unresolved_failure_count"] == 0,
        "zero_unknown_attempts": gauges["unknown_attempt_count"] == 0,
        "zero_stalled_pending_backlog": (
            (oldest_pending_age is None or oldest_pending_age <= max_pending_age_seconds)
            and (
                oldest_due_lateness is None
                or oldest_due_lateness <= max_due_attempt_lateness_seconds
            )
            and gauges.get("pending_callback_count", 0) == 0
            and (
                oldest_callback_age is None
                or oldest_callback_age <= max_due_attempt_lateness_seconds
            )
        ),
        "provider_error_rate_within_budget": max_observed_error_rate <= max_error_rate_threshold,
        "live_external_delivery_observed": total_live_provider_attempts > 0,
        "multi_week_window_met": observed_live_span_days >= min_live_days_required,
    }
    certified = all(gates.values())

    report_body: dict[str, Any] = {
        "service": "uns",
        "version": uns_version,
        "generated_at": datetime.fromtimestamp(now_val, tz=UTC).isoformat(),
        "window_days": window_days,
        "min_live_days_required": min_live_days_required,
        "observed_span_days": observed_span_days,
        "observed_live_span_days": observed_live_span_days,
        "operational_gauges": gauges,
        "notifications": status_counts,
        "acknowledgments": ack_counts,
        "response_latency_seconds": {
            "sample_count": len(response_latencies),
            "p50": _percentile(response_latencies, 50),
            "p95": _percentile(response_latencies, 95),
            "max": round(response_latencies[-1], 3) if response_latencies else None,
        },
        "channels": [channel_stats[k] for k in sorted(channel_stats)],
        "provider_classification": {
            "live_provider_attempts": total_live_provider_attempts,
            "recording_only_attempts": total_recording_only_attempts,
            "max_channel_error_rate": max_observed_error_rate,
            "error_rate_budget": max_error_rate_threshold,
        },
        "slo_gates": gates,
        "v1_0_certified": certified,
    }

    canonical = json.dumps(report_body, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    sha_token = f"sha256:{digest}"
    report_body["receipt_hash"] = sha_token
    report_body["receipt_sha256"] = sha_token

    if isinstance(database, str):
        runtime.engine.dispose()
    return report_body


def format_slo_markdown(report: dict[str, Any]) -> str:
    """Format an SLO report dictionary as a Markdown certification summary."""
    gauges = report["operational_gauges"]
    notifs = report["notifications"]
    acks = report["acknowledgments"]
    lat = report["response_latency_seconds"]
    gates = report["slo_gates"]
    status_label = (
        "CERTIFIED (`v1.0` GATES PASSED)"
        if report["v1_0_certified"]
        else "REHEARSAL / PENDING LIVE PILOT"
    )

    lines = [
        "# UNS Operational SLO Telemetry & Certification Receipt",
        "",
        f"- **Status:** {status_label}",
        f"- **Version:** `{report['version']}`",
        f"- **Generated At:** `{report['generated_at']}`",
        f"- **Observation Window:** `{report['observed_span_days']}` / `{report['min_live_days_required']}` days required",
        f"- **Receipt Digest:** `{report['receipt_hash']}`",
        "",
        "## 1. Real-Time Operational Backlog Gauges",
        "",
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| `pending_count` | `{gauges['pending_count']}` |",
        f"| `oldest_pending_age_seconds` | `{gauges['oldest_pending_age_seconds']}` |",
        f"| `oldest_due_attempt_lateness_seconds` | `{gauges['oldest_due_attempt_lateness_seconds']}` |",
        f"| `overdue_ack_count` | `{gauges['overdue_ack_count']}` |",
        f"| `unknown_attempt_count` | `{gauges['unknown_attempt_count']}` |",
        f"| `unresolved_failure_count` | `{gauges['unresolved_failure_count']}` |",
        f"| `pending_callback_count` | `{gauges['pending_callback_count']}` |",
        "",
        "## 2. Obligation Volume & Response Latency",
        "",
        f"- **Notifications:** `{notifs['total']}` total (`{notifs['delivered']}` delivered, `{notifs['deduplicated']}` deduplicated, `{notifs['failed']}` failed, `{notifs['dead_letter']}` dead-letter)",
        f"- **Responses:** `{acks['acked']}` ACKED, `{acks['dismissed']}` DISMISSED, `{acks['timed_out']}` TIMED_OUT, `{acks['pending']}` PENDING",
        f"- **Time to Respond (`n={lat['sample_count']}`):** `p50={lat['p50']}s`, `p95={lat['p95']}s`, `max={lat['max']}s`",
        "",
        "## 3. Channel Delivery & Provider Error Rates",
        "",
        "| Channel | Attempts | Succeeded | Failed | Unknown | Live Provider | Recording Only | Error Rate |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    if report["channels"]:
        for ch in report["channels"]:
            lines.append(
                f"| `{ch['channel']}` | `{ch['total_attempts']}` | `{ch['succeeded_attempts']}` | "
                f"`{ch['failed_attempts']}` | `{ch['unknown_attempts']}` | `{ch['live_provider_attempts']}` | "
                f"`{ch['recording_only_attempts']}` | `{ch['error_rate']:.4f}` |"
            )
    else:
        lines.append("| *(none)* | `0` | `0` | `0` | `0` | `0` | `0` | `0.0000` |")

    lines.extend(
        [
            "",
            "## 4. `v1.0` SLO Certification Gates",
            "",
            "| Gate | Passed |",
            "| :--- | :--- |",
        ]
    )
    for gate_name, passed in gates.items():
        lines.append(f"| `{gate_name}` | `{'PASS' if passed else 'FAIL'}` |")

    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for ``uns-slo-certify``."""
    parser = argparse.ArgumentParser(
        prog="uns-slo-certify",
        description="Compute UNS operational SLO telemetry and generate a hash-verifiable receipt.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("UNS_DATABASE_URL", ""),
        help="SQLite or PostgreSQL database URL (defaults to UNS_DATABASE_URL).",
    )
    parser.add_argument(
        "--window-days",
        type=float,
        default=14.0,
        help="Observation window in days (default: 14.0).",
    )
    parser.add_argument(
        "--min-live-days",
        type=float,
        default=14.0,
        help="Minimum observed span in days required for v1.0 certification (default: 14.0).",
    )
    parser.add_argument(
        "--max-error-rate",
        type=float,
        default=0.05,
        help="Maximum allowed channel provider error rate (default: 0.05).",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Emit Markdown report instead of JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output file path to write the report.",
    )
    parser.add_argument(
        "--require-certified",
        action="store_true",
        help="Exit with code 2 if v1_0_certified is False.",
    )

    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or UNS_DATABASE_URL is required")

    report = compute_slo_report(
        args.database_url,
        window_days=args.window_days,
        min_live_days_required=args.min_live_days,
        max_error_rate_threshold=args.max_error_rate,
    )
    rendered = format_slo_markdown(report) if args.markdown else json.dumps(report, indent=2) + "\n"

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    if args.require_certified and not report["v1_0_certified"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
