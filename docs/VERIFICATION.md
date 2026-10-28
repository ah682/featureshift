# Executed release verification

Verified locally on **2026-10-13**, Linux x86_64, CPython **3.12.3**, uv **0.11.28**.
Both target environments use NumPy 2.2.6; only pandas changes (2.3.3 → 3.0.0).
All measurements below come from actual execution, not simulated integrations.

## Consolidated commands and results

| Command / workflow | Observed result | Durable evidence |
| --- | --- | --- |
| `make setup` | Both exact environments valid; all shared dependencies constant. Cached application install succeeds before any download is attempted. | `.featureshift/setup/environments.json`, `.featureshift/verification/setup.log` |
| `npm run dev` → `make demo` | Setup, three real seeded reports and loopback server all completed; tested from clean report state. | SQLite audit and `.featureshift/runs/*/report.json`; live `http://127.0.0.1:8765` |
| `npm test` → `make test` | **79 passed in 50.47 seconds**, one upstream Starlette/httpx deprecation warning. | `.featureshift/verification/test-final.log` |
| `make check` | Ruff passed; mypy passed for 15 application source files; Python compilation passed. | `.featureshift/verification/check.log` |
| `.venv/bin/python scripts/refresh_evidence.py --check` | 10 valid immutable source snapshots, 23 valid indexed passages, offline integrity check passed. | `.featureshift/verification/evidence-check.json` |
| `.venv/bin/python -m featureshift evaluate --state .featureshift/evaluation-state --output .featureshift/evaluation` | **28/28 labels**, **140/140 source/version/operation citations**, **3/3 fresh deterministic reruns**; exit 0. | `.featureshift/evaluation/evaluation.json`, `report.html`, `report.md`; all per-case traces retained |
| Isolated headless Chrome checks | **37 assertions passed**; no JavaScript/console errors or horizontal overflow at 320, 390, 768, 1024 and 1440px. Desktop/mobile screenshots inspected. | `.featureshift/verification/ui-checks.json`, `ui-failure-checks.json`, `ui-patch-checks.json`, `ui-*.png` |
| Standalone downloaded regression artifacts | Selector and probe-only boundary artifacts pass under old pandas and fail with the actual changed output under new pandas. No FeatureShift installation needed. | `tests/test_artifacts.py`, full suite log, per-run `regression_test.py` |
| `FEATURESHIFT_STATE=/tmp/featureshift-reset-verification make reset` | Generated runs, SQLite audit and evaluation directories removed; dependency-directory sentinel retained. | Executed isolated reset check; original working environments and evidence retained |
| Clean offline source copy: `UV_OFFLINE=1 make setup`, acceptance tests, `make seed` | **All passed**: fresh app + both worker environments created in 1.06s; 13 acceptance tests passed in 106.03s; three real demo reports seeded in 25.39s. | `.featureshift/verification/clean-release.json`, `clean-setup.log`, `clean-acceptance.log`, `clean-seed.log` |

A clean application/worker recreation and acceptance run is recorded separately
in `.featureshift/verification/clean-release.json` and `clean-*.log`. This check
copies source into a new temporary directory with no existing `.venv`, workers,
database or reports, and reuses only the pinned wheel cache with `UV_OFFLINE=1`.
The verified clean source directory is `/tmp/featureshift-clean-release-f2oy7pxe`.

The managed development shell denies ordinary socket operations, including the
cross-thread socketpair used by TestClient. The approved `npm test` launcher runs
the exact `make test` command successfully. Likewise `npm run dev` runs the exact
documented `make demo`. These wrappers do not change application/test logic or
install Node dependencies. Normal Linux users can use Make directly. Initial
direct HTTPS setup attempts failed DNS in that shell; permitted uv downloads
and later cached setup completed. Both failed and successful setup attempts are
persisted and are never treated as semantic results.

CUA exposed no browser and the Playwright extension could not connect. An
isolated headless Chrome instance successfully exercised the real local service.
The tested procedure, reusable scripts and temporary profile restrictions are in
`scripts/browser-qa-notes.md`. No remote CI job or public deployment was run.

## Required capabilities and acceptance mapping

| Capability / mandatory case | Implementation and executed check | Observation / boundary |
| --- | --- | --- |
| Parse/persist selected upgrade, manifests, code/input hashes and configuration | `models.py`, `cases.py`, `engine.py`, `store.py`; full suite plus CLI demo | Validated exact pair and registered entry points; immutable run input/source snapshots and hashes retained. Other pairs unavailable. |
| Versioned permitted evidence, keyword retrieval, source availability, conflicts and temporal cutoff | `evidence.py`, snapshots/manifests, `test_evidence.py` | Hash/offset tampering, wrong versions, contradictory claims and post-cutoff sources are rejected for definitive support. Original release-tag sources explicitly replace unavailable archived HTML. |
| **String feature disappears from selector** | `examples/selector.py`, `test_acceptance.py`, selector demo | `segment` present before, absent after `df.dtypes == "object"`; exact dtype-check documentation attached; explicit feature contract violated. |
| **Unaffected transformation has no defect finding** | `examples/numeric.py`, acceptance and API queue tests | Zero observations, zero contract violations, equivalent repeated outputs. No universal safe-upgrade badge. |
| **Intentional dtype change accepted and traceable** | `examples/intentional_dtype.py`, typed intentional rules, `Store.accept`, API/browser review checks | Two observed dtype differences plus two documented-change annotations accepted; original outputs and audit reasons remain; no unaccepted observation. |
| **Null/conversion explicit contract** | `compare.py`, `astype-null`, `null-sentinel`, `null-equivalent`; comparator/acceptance tests | Strict null kinds differ; missingness-equivalent contract deliberately normalizes them. A new non-null contract violation is distinguished from a pre-existing one. |
| **Failed installation is an environment failure** | `runner.verify_install_failure`, `install-failure`, acceptance/browser checks | Real offline `pandas==999999.0.0` installation exits nonzero; installed manifest unchanged; no transformation or semantic-regression claim. |
| **Stochastic output recognized** | Repeated workers and `_compare_runs`; `stochastic` / seeded control | Within-environment variation produces insufficient evidence; cross-version attribution withheld. Seeded control repeats. |
| **Wrong-version evidence cannot be definitive** | `wrong-version`, `retrospective-cutoff`, evidence/acceptance tests | Observations can remain visible but no expected-change finding is supported by wrong/later versions. |
| **Generated probe times out without corrupting jobs** | Worker process-group termination, validation stage; timeout/recovery acceptance and browser checks | Deliberately sleeping generated probe is terminated at its 0.5s deadline, excluded from comparisons; the next numeric run succeeds. |
| **Arbitrary-upload mode unavailable without isolation** | Closed registry, forbidden extra request fields, `/api/uploads`, `upload_policy`; API/browser tests | Endpoint returns 403 and UI disables upload. No verified container profile; trusted subprocess is explicitly not a secure sandbox. |
| **Repeated deterministic reports normalize equivalently** | `normalized_findings`, acceptance tests, evaluator's three fresh reruns | All 3/3 selected full reruns match, excluding IDs, timestamps, paths and timing. |
| Reviewable targeted code, independent validation, and coverage beyond original fixture | `probes.py`, `probe-only-null`, artifact integration test | Baseline `[0,0,0]` remains unchanged and both existing tests pass. Validated null-boundary probe changes indicator to `[1,0,0]`; exported regression replays that probe. Constructed during development. |
| Compare values, categories, ordering and tolerances | `compare.py`, 25 comparator tests | Numeric tolerances, large integer exactness, null kinds, column order, category mappings, index names and whole-row/index association tested. Unordered tolerant comparison capped at 500 rows. |
| Findings include source, evidence, code, outputs, rule, command and downstream review impact | `engine.py`, `artifacts.py`, static report UI; API/browser exports | JSON/HTML contain full audit and execution records. Suggested selector patch is not applied, and its remaining dtype differences are visible with validation records. |
| Local persistence and failure states | SQLite migration 1, bounded queue, startup recovery; API tests | Consequential events persisted; interrupted jobs marked failed. Typed invalid input, unknown IDs, unavailable uploads, loading, partial and empty states handled. |
| Baselines and reproducible evaluation | `evaluation.py`, `test_evaluation.py`, actual 28-case run | Existing tests, explicit edgetest-style replay, documentation-only risks and full system compared; no fabricated assistant/model results. |

## Measured outcomes and their limits

The final 28-case diagnostic run took **76.49 seconds**, with **2.61 seconds** median
automated report-ready time. Human review latency was not measured.

| Measure | Result |
| --- | --- |
| Full-system material-change recall | 12/12 |
| Existing tests / shared edgetest-style replay | 1/12 |
| Documentation-only risk recall | 12/12; also warned on 8/10 equivalent cases |
| Full-system alerts on equivalent cases | 0/10 |
| False defect allegations on equivalent or intentional cases | 0/11 |
| Probe execution success | 24/25 including the required timeout; 24/24 excluding it |
| Completed deterministic probe comparisons | 23/25; timeout and stochastic controls excluded |
| Within-environment repeated contexts | 98/102 equivalent; four stochastic contexts differ |
| Exact source and operation citations | 140/140 |
| Fresh normalized reruns | 3/3 |
| Actual model calls / cost | 0 / $0 |
| Cases detected only by generated probes | 1 deliberately constructed missingness-indicator case |

The suite is curated alongside the implementation. It does not establish general
accuracy, superiority to a capable coding assistant, commercial demand or
production readiness. Historical inputs are present-day adaptations of licensed
regression tests. Independent repositories, stronger test baselines, original-time
historical evidence, human review/customer studies, other environments and secure
uploaded-code execution remain unperformed gates; see `docs/LIMITATIONS.md`.
