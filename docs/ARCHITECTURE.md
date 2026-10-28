# Architecture

The application process never imports a target pandas version. A small FastAPI
service and an argparse CLI share `Engine`; SQLite stores consequential state
transitions and review events, while each run has a dedicated artifact directory.
The user-facing page uses local static HTML/CSS/JavaScript with no build pipeline
or external fonts/services. uv manages installation instead of a custom package
resolver or orchestration platform.

```text
Closed case registry + sanitized fixture + contract
  → snapshot source/input, hash and persist queued event
  → inspect exact environment manifests and offline evidence
  → existing test + repeated trusted worker execution in each environment
  → compare baseline outputs and check determinism
  → generate a reviewable rule-based boundary probe
  → syntax check → independent execution validation → repeated probe comparison
  → classify observations / expected changes / contract violations / uncertainty
  → persist report + audit + JSON/HTML/regression artifacts
```

`runner.py` executes the standalone `worker.py` with each virtual-environment
interpreter. Workers clear ambient environment variables, disable user site paths,
bound CPU, address space, output size, processes and descriptors, and run with a
wall-clock deadline. Timeout kills the process group. They serialize per-column
values directly to avoid `iterrows` numeric coercion. Logs, exit code, timing,
versions and errors are retained even when comparison is impossible. Dependency
fetching occurs only during setup; a worker never invokes an installer.

These limits protect the trusted demo from accidental runaway jobs. They do not
isolate the host filesystem or network. Public API requests cannot specify code,
paths, commands or imports; only registered cases and typed contracts are accepted.
The service binds to loopback, rejects unrecognized hosts and cross-origin
mutations, serves escaped report data, and has a bounded queue with one concurrent
preflight. A verified non-root container runner with immutable images, read-only
input, no runtime network/secrets/socket mounts, and resource limits is future work.

`evidence.py` implements deterministic keyword scoring with exact source-version
filters and verifies content hashes/offsets before returning or accepting citations.
Engine rules also match a comparison to an operation-specific passage. A retrieved
passage alone cannot establish an observed difference. Conflicting claims and
post-cutoff documents cannot support a definitive documented-change finding.

The comparator handles columns/order, rows/order, index associations, dtypes,
categories, null kinds and tolerant numeric values. Unordered rows use a bijective
match rather than independent column sorting, preserving records and duplicates.
That more expensive profile is capped at 500 rows; ordinary ordered fixtures are
capped at 10,000 rows/100,000 cells. Large production datasets are out of scope.

The `ProbeProvider` protocol has a deterministic rules implementation. It uses
AST operation detection and fixed source templates, never executes instructions
from documentation, and reports zero model calls/cost. A live model adapter is
not implemented. All generated code and validation results are retained.

Database migration 1 lives in `Store` initialization. Run creation, progress,
completion and acceptance are persisted. Startup marks interrupted jobs failed;
it does not quietly mark them complete or retry unknown side effects. Setup may
be safely retried because it checks complete manifests against pinned lock inputs.
Atomic artifact replacement avoids half-written downloads; SQLite is authoritative.
