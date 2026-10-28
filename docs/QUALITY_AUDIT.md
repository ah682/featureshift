What this repo does: FeatureShift runs a reviewed feature transformation under pandas 2.3.3 and 3.0.0, compares the results against an explicit contract, and attaches versioned source evidence. This audit assumes one local operator and trusted registered examples, with overlapping browser requests and recoverable local failures.

**Audit date:** 28 October 2026. **Method:** Ponytail 5.3.2 and relevant Superpowers 7.0.1 skills: trace the main flows, reproduce concrete failures, write failing regressions, make the smallest complete fixes, and verify again. Local results below precede final integration review and hosted workflow execution.

## Must fix — resolved

1. **An unchanged null gives a value change the wrong category** ([compare.py](../featureshift/compare.py)).
   - **What this is:** The comparator classifies observed changes before evidence explains them.
   - **Reproduced problem:** `[1, null]` changing to `[2, null]` was attributed to null behavior even though the null cell did not change.
   - **Small fix and outcome:** Classify the cells that differ. [The regression](../tests/test_compare.py) now requires `values:value` for this case and passed after first failing.
   - **If it regresses:** A correct observation receives the wrong explanation and supporting evidence.

2. **Failed run creation consumes the entire queue** ([api.py](../featureshift/api.py)).
   - **What this is:** An eight-slot admission limit bounds local work before a run is stored.
   - **Reproduced problem:** Eight injected `OSError` failures during creation retained all eight permits; a later valid request could no longer enter the queue.
   - **Small fix and outcome:** Release admission capacity when creation fails, including unexpected exceptions. [The API regression](../tests/test_api.py) now accepts the next valid request with HTTP 202.
   - **If it regresses:** A recoverable storage failure leaves the service unusable until restart.

3. **Late acceptance and polling responses replace the selected report** ([app.js](../featureshift/static/app.js)).
   - **What this is:** Review saves and queued-job polling complete independently of navigation.
   - **Reproduced problem:** Delay an acceptance or completion response, select another report, then release it: the older report takes over the current view and its downloads.
   - **Small fix and outcome:** Bind updates to the selected run and request context. [The browser check](../scripts/browser_qa.mjs) asserts that both delayed paths preserve the newer selection; the harness disables browser caching so it exercises current code.
   - **If it regresses:** The displayed investigation and the operator's selection disagree.

## Verification and process changes

| Evidence | Before this repair pass | After repairs |
| --- | --- | --- |
| `make test` | 85 passing tests; the new cases were absent | 87 passing tests |
| `make check` | Existing lint/type checks | Passed |
| `make evaluate` | Dated developmental evaluation | 28/28 labels, 140/140 source/version/operation citations, 3/3 fresh normalized reruns |
| `node scripts/browser_qa.mjs` | 22 checks; delayed-response defect reproduced | 23 checks, including acceptance and completion selection guards |
| `node scripts/browser_failure_qa.mjs` | Existing negative paths | 7 checks passed |

The two Python regressions and browser race assertion failed before their fixes. These results describe the reviewed local examples, not arbitrary customer repositories or universal upgrade safety. The earlier release measurements remain in [VERIFICATION.md](VERIFICATION.md); the repair scope is in the [runtime plan](superpowers/plans/2026-10-28-runtime-audit.md).

Reproduce the checks after `make setup`:

```sh
make check
make test
.venv/bin/python scripts/refresh_evidence.py --check
make evaluate
```

For browser checks, start a seeded local service and isolated Chrome as described in the [browser QA notes](../scripts/browser-qa-notes.md), then run both commands from the table. CI uses `FEATURESHIFT_URL=http://127.0.0.1:18765` and `CHROME_DEBUG_URL=http://127.0.0.1:19227`; both scripts are part of the [verification workflow](../.github/workflows/ci.yml).

Verification jobs now use pinned action commits, read-only repository permissions, time limits, and cancellation of superseded runs. CI includes browser checks and actionlint. [Dependency checks](../.github/workflows/dependencies.yml) run on pushes, pull requests and weekly schedules; [Dependabot](../.github/dependabot.yml) proposes action updates. The exact pandas worker locks remain part of the experiment, and are audited separately from application tooling. Hosted verification and dependency checks passed for the revision recorded below.

Verdict: The three reproduced runtime defects are fixed without changing the local architecture or comparison protocol. Independent integration review and hosted checks passed for the recorded revision.

Not checked: Arbitrary repository execution, a secure untrusted-code sandbox, live model providers, customer accuracy or handling time, and public multi-user operation. One existing Starlette/httpx test-client deprecation warning remains. MIT and upstream evidence notices are unchanged.

## Hosted verification — 28 October 2026

Reviewed implementation and workflow revision: `a0ad728a2b88af7d7d369441c0513d5bb5e1c7f2`.
[Verification](https://github.com/ah682/featureshift/actions/runs/40667448073) and
[dependency auditing](https://github.com/ah682/featureshift/actions/runs/40667448053) both passed.
The run artifacts retain the generated test/browser evidence for 14 days.
Subsequent documentation-only commits do not change this tested implementation.
