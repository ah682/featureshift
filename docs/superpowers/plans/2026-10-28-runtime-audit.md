# Runtime audit implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement these tasks with regression tests and a final independent review.

**Goal:** Correct the reproduced comparison, queue recovery and stale browser response defects.

**Architecture:** Keep the current local service, trusted registry, SQLite store and browser UI. Fix each rule at its existing boundary; add no runtime dependencies.

**Tech stack:** Python 3.12, FastAPI, SQLite, plain JavaScript and Chrome.

**Spec:** The README's comparison, bounded queue, persisted review and local-only contracts; the user's request to audit all code and verification with Ponytail and Superpowers.

## Constraints and review focus

- Preserve exact pandas environments, evidence provenance and existing findings.
- A value change next to an unchanged null must not become a null-change attribution.
- Failed run creation must return its queue capacity, including disk-write failures.
- Delayed acceptance or polling responses must not replace a newer report selection.
- The selected report and its downloadable artifacts must always refer to the same run.
- Keep server execution and audit persistence independent of browser navigation.

## Tasks

- [x] Add `test_unchanged_null_does_not_reclassify_a_value_change` in `tests/test_compare.py`; prove that `[1, null]` → `[2, null]` reports `values:value`, then fix `compare_frames` in `featureshift/compare.py`.
- [x] Add `test_failed_creation_releases_queue_capacity` in `tests/test_api.py`; inject eight `OSError` failures, then assert the next valid submission returns 202. Release the semaphore for unexpected creation exceptions in `featureshift/api.py`.
- [x] Extend `scripts/browser_qa.mjs` with delayed acceptance and completion responses while selecting a different report. Observe failure before adding selection guards in `featureshift/static/app.js`.
- [x] Run focused regressions, `make check`, `make test`, `make evaluate`, and both browser suites. Check that exported standalone regression code still works through the existing artifact tests.
- [x] Record exact evidence and limitations in the audit report, obtain independent review, and commit the changes.
