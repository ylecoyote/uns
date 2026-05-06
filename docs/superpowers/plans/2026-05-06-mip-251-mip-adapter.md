# MIP-251 MIP Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a MIP-shaped adapter over AGSignal's generic app boundary without importing MIP or ATP code.

**Architecture:** Implement a small `MIPSignalAdapter` in `notification.integrations.mip_adapter` that builds `AppSignalRequest` objects and delegates to `AppSignalAdapter`. Tests use a recording adapter to verify request shape and boundary behavior.

**Tech Stack:** Python, Pydantic models already in AGSignal, pytest, mypy, ruff.

---

## File Structure

- Create `src/notification/integrations/mip_adapter.py`: adapter methods and typed execution alert inputs.
- Modify `src/notification/integrations/__init__.py`: export adapter types.
- Modify `src/agsignal/integrations.py`: expose public AGSignal aliases.
- Create `tests/notification/test_mip_adapter.py`: TDD request-shape tests.
- Update `docs/README.md` and `docs/m5-publish-readiness-reference.md`: link MIP adapter docs/spec.
- Add this spec and plan under `docs/superpowers/`.

## Tasks

1. Write failing tests for approval, circuit breaker, execution alert, and public alias exports.
2. Implement the minimal adapter and exports.
3. Add docs links and update M5 reference.
4. Run focused pytest, ruff, mypy, and `git diff --check`.
5. Commit with Lore format and merge to local `main`.

