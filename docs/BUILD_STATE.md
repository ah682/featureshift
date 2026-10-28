# FeatureShift build state

## Scope and implementation plan

Build a credential-free, CPU-first local preflight for repository-owned stateless
DataFrame transformations. The first acceptance fixture selects inferred string
columns with `df.loc[:, df.dtypes == "object"]`: pandas 2.3 should retain the
feature and pandas 3.0 should drop it. Execute both real environments, attach
versioned migration evidence, and retain the complete audit trail.

1. Verify/pin Python, pandas and shared dependencies; capture resolved manifests.
2. Implement the first vertical slice: fixture → two workers → structured diff →
   persisted report. Use uv for environment setup and bounded trusted workers.
3. Add version-filtered keyword evidence, reviewable targeted probes, contracts,
   repeated execution, audit acceptance, downloadable reports and regression tests.
4. Add the local report UI/API and at least 20 provenance-labeled evaluation cases.
5. Execute acceptance/evaluation, inspect browser rendering, fix issues, and record
   measured results plus remaining limitations.

## Decisions

- Workspace initially contains only the supplied build prompt; no existing code.
- Host Python is 3.12.3. No Docker executable is installed. Arbitrary code upload
  will remain disabled; a subprocess is not a security sandbox.
- Use a deterministic rule-based probe/retrieval baseline with zero model calls.
  No credentials, paid services, public deployment, or market-validation claims.
- Parallel work has explicit boundaries: worker/environment code; evidence corpus
  and retrieval; static report UI. Main agent integrates core logic/API/evaluation.

## Checks, blockers and next steps

- Read the entire project prompt and checked ancestor/workspace instructions.
- Opened official pandas documentation and the supplied historical references.
- Basic Python HTTPS requests cannot resolve pypi.org in the restricted shell;
  investigate permitted dependency installation and local caches during setup.
- Next: establish actual pinned environments and execute the selector fixture.

## First runtime discovery

Both environments installed successfully with Python 3.12.3 and NumPy 2.2.6.
An actual probe showed `select_dtypes(include=["object"])` still selects strings
in pandas 3.0.0 with a deprecation warning. The acceptance fixture uses an explicit
`df.dtypes == "object"` mask, which does lose the string feature. The former is
retained as a benchmark control; documentation risks are not assumed to be bugs.

## Implemented local release

- Real before/after workers, exact hash-pinned shared dependencies, complete
  manifests and setup-attempt persistence; cold worker recreation from cached
  wheels verified. The application setup tries cached wheels before downloading.
- Closed source/fixture registry, typed contracts, structured output comparison,
  repeated execution, independently validated probes, distinct finding types,
  review audit, proposed diff validation and standalone regression artifacts.
- Offline exact-version evidence from 10 immutable official snapshots and 23
  passages, including explicit source-availability/permission/temporal metadata.
- Local API and responsive UI; no arbitrary upload profile. Browser checks cover
  live runs, review, downloads, errors, keyboard interaction and five screen widths.
- 28 labeled benchmark cases with grouped family folds and four explicit baselines.
  The first 27-case run matched outcomes but its citation audit found overbroad
  passage selection; operation-specific matching fixed it, and a full rerun passed.
- An additional constructed missingness-indicator case demonstrates an actual
  probe-only difference absent from the supplied fixture and existing tests. Its
  standalone regression artifact replays the validated probe. It does not establish
  external product usefulness. The final 28-case evaluation passes all labels,
  citations and repeat checks.

## Current verification status

The final integrated **79-test suite passed in 50.47 seconds**. Ruff, mypy and
Python compilation pass. The final benchmark matched **28/28 labels**, **140/140
citations**, and **3/3 fresh normalized reruns** in 76.49 seconds. The UI passed 37
browser assertions; desktop/mobile screenshots were inspected. Checks and
limitations are recorded in `docs/VERIFICATION.md`. `make demo` has been executed
from clean report state through the optional `npm run dev` launcher.
The final clean-source offline check also passed: fresh application and both
workers installed from the wheel cache, all 13 acceptance tests passed, and all
three demonstration reports were regenerated. The scoped local release gates
are complete; the local report server is running at `http://127.0.0.1:8765`.

## Remaining external gates

No release-blocking local implementation issue is known. Generalization to real
maintainer repositories, stronger test suites, human review/customer studies,
other dependency pairs, a live model experiment and verified container uploads
remain unperformed. They are not simulated or claimed as complete.
