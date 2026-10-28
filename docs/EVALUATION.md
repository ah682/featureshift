# Measured diagnostic replay evaluation

Run the actual pinned environments and produce the baseline comparison:

```sh
make evaluate
```

The CLI calls `featureshift.evaluation.evaluate(state: Path, output: Path)`. It writes `.featureshift/evaluation/evaluation.json`, `report.html`, `report.md`, and a durable `progress.json`. The complete per-case execution reports and regression artifacts live under `.featureshift/evaluation-state/runs`. The output and state directories can be changed with `--output` and `--state` on `.venv/bin/python -m featureshift evaluate`.

Every evaluation runs all 28 registered benchmark cases, with two repetitions in each exact environment, independent probe validation, and three additional fresh runs for deterministic repeatability. The three demonstration examples are not included in the 28-case count. The benchmark has 12 material-change, 10 equivalent, one intentional-change, three insufficient-evidence, one environment-failure, and one probe-error case. Five cases replay two licensed historical regression families, including a retrospective cutoff control; 23 are explicitly constructed. Historical cases adapt BSD-licensed pandas regression tests and do not recreate their original historical environments.

## Baselines

| Method | Input and action | Signal |
| --- | --- | --- |
| Existing tests | Execute each repository-owned `existing_test` in both pinned environments | The test passes before and fails after |
| Edgetest-style dependency test | Reuse those exact executed test records for an upgrade-and-test workflow with unrelated dependencies fixed | The same new test failure |
| Documentation only | Recognize source operations and retrieve exact-version evidence before any runtime case executes | Potential operation risk; no observed change or defect claim |
| Full system | Execute baseline fixtures and validated generated probes, compare repeated structured outputs under the declared contract, and attach matching evidence | Observed difference, expected change, contract violation, error, or insufficient evidence |

The **edgetest package is not executed**. Its workflow is represented by a pinned dependency-test replay, with execution reuse explicitly recorded. It is not an independently timed run or a fabricated integration. The documentation-only predictor receives source, sanitized fixture, version pair and temporal cutoff; it never receives executed outputs or expected labels. Every static prediction is frozen before the first benchmark execution.

No coding-assistant comparison, human review study, or paid model call is performed. A future assistant experiment needs a fixed model/version, identical inputs and evidence access, a recorded prompt, independent review, and real measured cost and outcomes.

## Labels, metrics and denominators

Actual outcome precedence is fixed: setup/environment error, probe/execution error, insufficient evidence, fully accepted intentional change, observed material change, then equivalence. Expected labels are only consulted after actual classification. Wrong-version and retrospective controls may contain real observed output differences while correctly withholding a definitive documentation attribution. A setup failure never counts as detection of a semantic change.

Material-change alert recall uses the 12 `material_change` cases as its denominator. For documentation only, this is **risk recall**, not runtime observation recall; the latter is left null. The equivalent and intentional cases are reported separately and also as a combined alert denominator. A visible accepted intentional change is not a false defect. False defect allegations mean an unaccepted declared-contract violation asserted on an equivalent or intentional case. Existing-test failures and documentation risk alerts are not themselves alleged defects.

The machine-readable report additionally measures:

- Outcome agreement for all 28 labels, by fold and change family.
- Probe execution success, with and without deliberate failure controls, separately from completion of deterministic comparisons. A successfully executed stochastic probe is inconclusive, not an execution failure.
- Exact source/version/hash/offset validity and a stricter independent match of each attached citation to the case's reviewed change family and detected operation. A valid pandas source about datetime does not support an unrelated string conversion.
- Within-environment equivalence for every testable repeated baseline/probe context. The stochastic negative control remains in the denominator and should be unstable.
- Across-run equality of normalized findings for `dtype-mask`, `numeric-scale`, and `intentional-dtype`. IDs, paths, timings and acceptance-event timestamps are excluded; behavior, comparison rule, probe and evidence identities are retained.
- Elapsed time until each automated report is ready, plus total evaluation time. Human review latency is null because no human review session was measured.
- Actual model call count and model cost from the provider records, including the three fresh reruns. The deterministic provider incurs zero model calls and zero model cost.

Additional detections over existing tests are counted. Cases detected **only** by generated probes are reported separately. Most fixture tests deliberately exercise a weak row-count assertion, so gains over those tests cannot be generalized to mature production suites. Full-system gains also include ordinary input/output comparison; they do not by themselves establish the incremental value of generated probes.

The constructed `probe-only-null` case converts numbers to strings and derives an integer missingness indicator. Its supplied fixture contains no missing values. A generated wrapper inserts a missing input, targeting the documented change in `astype(str)` null preservation. The evaluator records whether the ordinary fixture already changed or only the generated boundary exposed a difference. This case was added during development to demonstrate that mechanism; it is not independent evidence of its prevalence or customer value.

## Change-family folds and leakage limits

The evaluator canonicalizes related families before assigning folds. String-selector controls, all string-inference cases, and numeric transformations overlap the demonstration and are assigned to **development**. Numeric scale/aggregation share a group. The three null-conversion historical variants and the retrospective control share the string-conversion group. Every member of one repository/change family stays in one fold.

This yields seven development cases and twenty-one evaluation cases. Original registered split labels remain visible beside the effective grouped fold. The evaluation fold is a **diagnostic replay suite authored alongside the implementation**, not an independent heldout estimate. No aggregate score should be presented as production accuracy, commercial validation, or evidence of superiority over a capable coding assistant. Expanding to 50–100 cases means adding reviewed entries with provenance, permissions, expected behavior, and family labels; evaluation enumeration is not fixed to a hard-coded count.

Each case report retains synthetic/historical status, license, original issue timestamp and immutable source where relevant, fixture/source hashes, transformation notes, exact contract, cutoff, version pair, fold/group, expected versus actual label, and links to raw runs. The evaluator records implementation and benchmark-manifest hashes. Historical regression-test snapshots and later issue fixes are excluded from retrieval. The 2020 cutoff control receives no 2025/2026 documentation.

## Interpreting the local result

`evaluation.json` is the authoritative measured result for the most recent run. `acceptance_passed` requires matching labels, valid operation-specific citations, and the selected across-run repeat checks. The report keeps every mismatch instead of relabeling cases. The independent citation check exposed broad evidence selection during development; the implementation was corrected and the entire evaluation rerun.

The verified 2026-10-13 CLI run completed in **76.49 seconds**, with a median case report-ready time of **2.61 seconds**:

| Measure | Actual result |
| --- | --- |
| Outcome labels | 28/28 matched |
| Existing tests / reused dependency-test baseline | 1/12 material-change cases alerted |
| Documentation-only | 12/12 material risks, but also risks on 8/10 equivalent cases |
| Full system | 12/12 material changes observed; 0/10 equivalent alerts |
| Intentional change | 1/1 observed and accepted, with its trace retained |
| False defect allegations | 0/11 equivalent or intentional cases |
| Exact source/version and operation citations | 140/140 correct |
| Generated probe execution | 24/25 successful; expected timeout accounts for the failure |
| Deterministic probe comparisons | 23/25 completed; stochastic probe remains inconclusive |
| Within-environment repeat contexts | 98/102 equivalent; the four stochastic contexts differ |
| Fresh deterministic reruns | 3/3 normalized findings equivalent |
| Model calls / model cost | 0 / $0 |

**One constructed material case was detected only by a generated probe.** In `probe-only-null`, the ordinary fixture and both existing tests passed with equivalent output. The `null-boundary` probe changed the missingness indicator from `[0, 0, 0]` before the upgrade to `[1, 0, 0]` afterward, with matching `astype(str)` evidence. The full system produced eleven additional material alerts over existing tests; ten also involve ordinary fixture-output comparison. The new case demonstrates the implemented boundary-coverage mechanism, but it was deliberately constructed during development. It does not establish how often probes add value on independent workloads or validate the product hypothesis commercially. Human review latency and coding-assistant performance were not measured.

Passing the local replay establishes the scoped engineering acceptance workflow. Independent repositories, stronger existing tests, pre-issue historical sources, human review latency, optional assistant comparison, container-upload isolation and maintainer/customer usefulness remain separate validation work.

Fast evaluation invariants are checked with:

```sh
.venv/bin/python -m pytest -q tests/test_evaluation.py
```

These tests check family grouping, independence from expected labels, error/uncertainty precedence, intentional acceptance, honest baseline reuse, metric denominators, and rejection of an exact-version citation for the wrong operation. The actual runtime benchmark is separate from this fast unit suite.
