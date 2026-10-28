# Local release verification

Verified on **2026-10-28**, Linux x86_64, CPython **3.12.3**, uv **0.11.28**.
The before/after workers contain the same five shared dependencies; only pandas
changes, **2.3.3 → 3.0.0**. PyArrow is absent.

The committed [machine-readable summary](release-verification.json) contains
measured outcomes, environment package sets and implementation/benchmark hashes.
Detailed run records are generated locally by the commands below and are ignored
by source control. A clean checkout does not include a database, wheel cache,
reports or historical development logs. Initial setup needs package access;
a previously populated wheel cache permits offline setup.

## Executed checks

| Command | Observed result |
| --- | --- |
| `UV_OFFLINE=1 make setup` | Fresh application and both worker environments created from a copied pinned wheel cache; manifests valid and shared dependencies constant. |
| `make check` | Ruff passed; mypy passed for 15 application files; Python compilation passed. |
| `make test` | **85 passed in 158.25s**, including real old/new execution, exported regression artifacts, API and error handling. One upstream Starlette/httpx deprecation warning. |
| `make test-fast` | **62 passed, 23 integration tests deselected in 0.62s**. |
| `.venv/bin/python scripts/refresh_evidence.py --check` | Ten valid immutable snapshots and 23 indexed passages; no hash/offset errors. |
| `make seed` | Three real reports: numeric zero differences, intentional two differences, selector two differences. |
| `make evaluate` | **28/28 labels**, **140/140 source/version/operation citations**, **3/3 fresh normalized reruns**; exit 0. JSON, HTML, Markdown and per-case execution artifacts generated. |
| `node scripts/browser_qa.mjs` against the seeded local service | **22 checks passed**, five viewport widths (320, 390, 768, 1024, 1440px), three actual artifact downloads; no page/console errors or horizontal overflow. Desktop/mobile/execution screenshots inspected. |
| `node scripts/browser_failure_qa.mjs` | **7 checks passed**: failed installation, wrong-version evidence, timed-out probe and successful subsequent execution. |

Full tests and evaluation ran concurrently with other local release checks.
Evaluation took **237.512s**, with **8.1808s** median automated report-ready time;
these are observations of this run, not performance thresholds or human latency.

The managed shell requires explicit execution approval for TestClient's local
socketpair and browser loopback access. The normal commands are unchanged.
Browser reproduction instructions are in [the QA notes](../scripts/browser-qa-notes.md).
The release coordinator independently ran both browser workflows and inspected
desktop/mobile, execution and failure-state screenshots. The committed
[workflow results](ui-checks.json), [failure checks](ui-failure-checks.json) and
[screenshots](screenshots/) retain the observations. No remote CI run or
application deployment is implied by these local checks.

## Acceptance coverage

| Capability | Implementation and executable coverage |
| --- | --- |
| Exact upgrade, manifests, configuration and code/input hashes | `models.py`, `cases.py`, `engine.py`, `runner.py`, `store.py`; runner, acceptance and artifact tests. |
| Versioned evidence, availability, conflicts and temporal cutoff | `evidence.py`, licensed snapshots/manifests; `tests/test_evidence.py` rejects tampering, wrong versions, contradictions and later evidence. |
| String feature disappears with matching documentation | `examples/selector.py`, `tests/test_acceptance.py`; `df.dtypes == "object"` loses `segment`, violating the column contract. `select_dtypes` compatibility remains a separate control. |
| Equivalent transformation has no defect finding | Numeric acceptance/API tests and benchmark controls; zero observations/contract violations. |
| Intended dtype adoption remains auditable | Typed intentional contract, `Store.accept`, API and browser review; original observations, reasons and audit events retained. |
| Null/conversion comparison follows explicit contract | Comparator and acceptance tests; strict sentinel kinds versus deliberate missingness equivalence, plus new versus pre-existing contract violations. |
| Installation failure is an environment error | A real offline impossible-pin install fails without altering installed packages; acceptance, runner and browser failure checks. |
| Stochastic output withholds cross-version attribution | Repeated baseline/probe execution and seeded control; determinism tests and benchmark. |
| Wrong-version evidence cannot establish cause | Wrong-version and retrospective controls; exact-version support checks. |
| Probe timeout terminates without harming later jobs | Process-group termination, independently validated probes, timeout/recovery acceptance and runner tests. |
| Uploads remain unavailable | Closed registry, rejected extra input fields, explicit upload policy/403 response; API and browser checks. Trusted subprocesses are not secure sandboxes. |
| Deterministic reruns normalize equivalently | Acceptance tests and three full fresh evaluator reruns, retaining behavior/evidence while excluding IDs/timing. |
| Probe-only boundary and standalone exported regression | `probe-only-null` plus artifact tests; ordinary fixture unchanged, probe indicator changes 0→1, exported test passes before and fails after without FeatureShift installation. |
| Values, ordering, categories, tolerances and index association | Comparator tests cover large integers, null kinds, reordered columns, whole-record multiset matching and duplicate-label rejection. Unordered tolerant comparison caps at 500 rows. |
| Reviewable evidence, source, before/after output and patches | JSON/HTML downloads and artifact tests; suggested selector diff is validated, never applied, and remaining dtype differences remain visible. |
| Durable states, bounded queue and startup recovery | SQLite audit, API tests and `tests/test_store.py`; unfinished runs recover even outside the UI's newest 200 records. |
| Loopback server configuration | `tests/test_cli.py`; non-loopback environment defaults fail before startup, and malformed port settings do not break unrelated commands. |
| Baselines and diagnostic evaluation | `evaluation.py`, `tests/test_evaluation.py` and full replay; edgetest-style baseline explicitly reuses actual existing-test results. The edgetest package is not executed. |

## Measured diagnostic outcomes

| Measure | Result |
| --- | --- |
| Full-system material-change recall | 12/12 |
| Existing tests / shared dependency-test replay | 1/12 |
| Documentation-only risk recall | 12/12; also warned on 8/10 equivalent cases |
| Full-system alerts on equivalent cases | 0/10 |
| False defect allegations on equivalent/intentional cases | 0/11 |
| Probe execution success | 24/25 including required timeout; 24/24 excluding it |
| Completed deterministic probe comparisons | 23/25; timeout/stochastic controls excluded |
| Within-environment repeated contexts | 98/102 equivalent; four stochastic contexts differ |
| Exact source/version/operation citations | 140/140 |
| Fresh normalized reruns | 3/3 |
| Model calls / cost | 0 / $0 |
| Material cases detected only by probes | One deliberately constructed missingness-indicator case |

The suite was curated alongside the implementation. It does not establish general
accuracy, customer usefulness, superiority to a coding assistant or production
readiness. Historical inputs are present-day adaptations of licensed regressions;
original issue environments were not recreated. Human review latency and customer
studies were not measured. See [evaluation](EVALUATION.md) and
[limitations](LIMITATIONS.md) for the remaining validation gates.

## Final review and dependency audit

Independent review found no major blocker. Its malformed-Origin regression
reproduced HTTP 500 before the fix and HTTP 403 afterward, with no run created.
The final 85-test run above includes that regression and uses the patched
application dependencies. Earlier evaluation and browser observations remain
valid for the unchanged comparison engine, worker pair and UI.

The application lock now pins certifi 2026.10.19 and pytest 9.0.3, resolving
[the certifi advisory](https://github.com/advisories/GHSA-6q48-6c7w-9gw2) and
[the pytest advisory](https://github.com/advisories/GHSA-6w46-j5rx-g56g).
`uvx pip-audit --path .venv/lib/python3.12/site-packages` reported no known
vulnerabilities. Separate audits of each pandas worker environment also passed.
The [application audit](dependency-audit-2026-10-28.json) is a dated check against
known advisories, not a guarantee against undiscovered issues.
