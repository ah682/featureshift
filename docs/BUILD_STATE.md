# FeatureShift build state

## Release scope

A credential-free local pandas 2.3.3 → 3.0.0 preflight for reviewed stateless
DataFrame transformations on CPython 3.12/Linux x86_64. The application executes
both real environments, compares repeated structured outputs under explicit
contracts, attaches exact-version offline evidence, and retains reviewable probes,
reports, regression tests and acceptance audit events. The default provider uses
deterministic rules and makes zero model calls.

Arbitrary uploads remain disabled: the trusted subprocess runner is resource
bounded but can access host files and network. No verified container isolation
profile, live model adapter or independent customer validation is implemented.

## Publication preparation — 2026-10-28

Plan: `docs/superpowers/plans/2026-10-28-publication.md`.
The original build brief remains available locally; public architecture, data,
evaluation and limitation documents describe the implemented scope.

Completed:

- Read the full build brief and audited registry, runner, comparator, engine,
  persistence, CLI, API, artifacts and documented release requirements.
- Created fresh application and both worker environments with
  `UV_OFFLINE=1 make setup`, reusing only a copy of the original wheel cache.
  Original project files and environments remain untouched.
- Reproduced and fixed an environment-variable bypass of the loopback host
  restriction; invalid server settings now fail before application startup.
- Reproduced and fixed malformed port configuration breaking unrelated CLI
  commands. Server defaults are parsed only for the selected server command.
- Reproduced and fixed startup recovery omitting interrupted runs older than
  the 200-run recent-history window. Recovery now scans complete persisted state.
- Five regression tests failed on the original behavior and passed after fixes.
- Ruff, mypy and compilation passed. Evidence integrity passed for ten immutable
  sources and 23 indexed passages. Demo seeding generated numeric (zero changes),
  intentional (two changes), and selector (two changes) reports successfully.

Fresh checks passed: 85 automated tests, 62 fast checks, all 28 evaluation
labels, 140/140 citations and 3/3 normalized reruns. Independent browser review
passed 22 workflow checks and seven failure checks; desktop/mobile and failure
screenshots were inspected. Recorded evidence is in `docs/VERIFICATION.md`.
Independent code review completed; its malformed-Origin regression now passes.
The final suite passes 85 tests after the certifi/pytest security updates.
Application and both worker dependency audits report no known vulnerabilities.
Public GitHub publication is the remaining step.

Ruling: retain the accepted architecture and source-checkout workflow rather than
introduce standalone wheel installation. Runtime assets and reviewed case inputs
remain repository-relative, and `make demo` is the tested entry point.

## Remaining validation gates

Historical inputs are present-day adaptations; original historical environments
were not recreated. Benchmark cases were curated alongside the implementation.
Human review latency, stronger real repository tests, maintainer/customer value,
other dependency pairs, live assistant comparisons and secure uploaded-code
execution remain unperformed. They are not simulated or claimed complete.

## Hosted runner follow-up

The initial public CI run passed 84 tests but one queued API test hit its fixed
15-second wait on shared hardware. That test creates 12 sequential isolated
workers, each with metadata inspection and its own execution timeout. Its total
wait was shorter than the supported job budget; it was an accidental latency
assertion, not a product requirement. The test still polls actual terminal state
and validates all outputs, with a five-minute overall guard and fewer repeated
HTTP reads. Per-worker timeouts and the separate timeout acceptance test are
unchanged. The CI job also has a 20-minute overall limit.

Initial run: https://github.com/ah682/featureshift/actions/runs/40650169839
The corrected hosted run must pass before publication verification is complete.
