# MIP-252A HTTP Idempotency and Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add producer `idempotency_key` support and richer simulation output to the standalone AGSignal HTTP app.

**Architecture:** Extend `notification.routes` request/response models and use a small app-state idempotency cache in `notification.main`. Keep this slice synchronous and in-process; durable idempotency belongs to later operational parity.

**Tech Stack:** FastAPI, Pydantic, pytest, ruff, mypy.

---

## Tasks

1. Add failing HTTP tests for idempotent retry and rich simulation.
2. Add app-state idempotency cache and route response fields.
3. Expand simulation response from captured `Notification`.
4. Add donor parity docs.
5. Run focused tests/lint/mypy/diff check, commit, merge to `main`, update Linear.

