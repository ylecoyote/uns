# Consolidated UNS baseline

The canonical working branch is **main**. It contains the original consolidation, both adversarial remediation iterations, their documentation and verification receipts. Continue implementation here rather than on the historical remediation branches.

## Integration

The previous canonical head `b508cc367f9eccdec5a1cbec2b1c691d16d84132` was an ancestor of the complete iteration-two head `76fc43ec99951f323768bab08e1c7fca34df7a9e`. Integration was a fast-forward, preserving all commits without conflicts, cherry-picking or rewriting history. Application source remains identical to reviewed implementation `ba46a311d071736a6beca241a6e43a1407f29f3b`; subsequent changes are documentation and receipts.

Preserved checkpoints: `uns/consolidation` at `b508cc3`, `remediation/adversarial` at `3f6005f`, and `remediation/iteration2` at `76fc43e`. The earlier remediation checkouts remain available as historical checkpoints. No original source directory was deleted or rewritten.

## Fresh verification from main

- Python: **1,765 passed**, **90.70% coverage** against the 75% gate.
- Console: **305 passed**; TypeScript, ESLint and production build passed from the merged lockfile.
- Ruff, mypy across 91 files, Bandit and UI boundary passed. Existing framework deprecations and non-failing annotation warnings are retained in logs.
- Wheel/source distribution rebuilt; 90 shipped Python modules match source. Separate installed full-wheel delivery/ACK, repeated migration CLI and unchanged-byte maintenance preview passed.
- Local recording-adapter delivery, restart and acknowledgment demo passed.

See [merge receipts](../verification/consolidated/results.json), [testing](TESTING.md), [iteration-two decisions](REMEDIATION_ITERATION2.md), and [review brief](REVIEW_BRIEF.md). Previous receipt sets are immutable historical evidence; this merge does not reclassify the original reviewer assertions or claim every assertion should pass unchanged.

No dependency advisory refresh, live-provider/human-receipt test, live PostgreSQL, representative load, hosted CI, publication or deployment was performed. This is a local integrated baseline, not production acceptance. External effects remain at least once; SMTP effects already in flight may complete after timeout.
