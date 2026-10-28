# Contributing

Start with the [demo](docs/DEMO.md), [architecture](docs/ARCHITECTURE.md), and [evidence contract](docs/EVIDENCE.md). FeatureShift compares a fixed pandas pair using trusted registered transformations. A useful bug report includes the source revision, exact environment manifests, input, contract, expected observation, and actual report. Use a small synthetic example and remove credentials or private data.

Reproduce a behavior defect before editing. Add a small regression that fails for that reason, fix the shared cause, and run the relevant tests. Use a fresh independent review after checks pass for behavior, execution, evidence or workflow changes. Describe the observed result, checks run, and remaining limits in the pull request. When available, use Ponytail to keep the change small and the relevant Superpowers skills for diagnosis, tests, verification and review; existing user authorization governs routine work.

After setup, the normal checks are:

```sh
make setup
make check
make test
.venv/bin/python scripts/refresh_evidence.py --check
make evaluate
```

`make test-fast` is useful while iterating; it omits tests that execute the target environments and does not replace `make test` for changes to execution or comparison. Evaluation writes under `.featureshift/evaluation/`. Keep old evidence dated and identify new runs rather than presenting a historical result as a fresh check.

For browser changes, use a disposable seeded local service and the isolated Chrome setup in [browser QA notes](scripts/browser-qa-notes.md), then run:

```sh
node scripts/browser_qa.mjs
node scripts/browser_failure_qa.mjs
```

The checks create fixture runs and record review decisions. They cover delayed responses, downloads, keyboard use, layout and failure recovery. Inspect screenshots when presentation changes. The same scripts run in [CI](.github/workflows/ci.yml); workflow edits should also pass actionlint. Documentation-only edits need accurate commands, working links and supported claims, not another environment rebuild or evaluation run.

Preserve the fixed pandas 2.3.3 → 3.0.0 comparison and common dependency versions unless the task explicitly changes the experimental protocol. Preserve source hashes, passage offsets, version filters, publication cutoffs, original observations and acceptance history. Do not turn missing execution or evidence into equivalence. Arbitrary uploads remain disabled, subprocess limits are not a secure sandbox, and suggested patches remain reviewable downloads rather than automatic edits.

Stop the server before resetting disposable state. Do not reset retained investigations or introduce live services merely to reproduce a local defect. Original code is [MIT licensed](LICENSE); preserve the [upstream evidence notices](evidence/licenses/) and the permission boundaries in [DATA.md](docs/DATA.md).

Install ShellCheck alongside actionlint when checking workflow edits, so embedded shell commands are validated as they are on the GitHub runner.
