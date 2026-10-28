# Verified environment pair

The local release executes real pandas installations with CPython **3.12.3** on
Linux x86_64. The worker lock files target CPython 3.12 Linux x86_64 wheels. They
include exact versions and the SHA256 of every permitted wheel; setup rejects
unpinned or modified package sets. Other operating systems, architectures, and
Python minor versions need separately verified wheel locks.

| Package | Before | After |
| --- | --- | --- |
| pandas | 2.3.3 | 3.0.0 |
| numpy | 2.2.6 | 2.2.6 |
| python-dateutil | 2.9.0.post0 | 2.9.0.post0 |
| pytz | 2025.2 | 2025.2 |
| tzdata | 2025.2 | 2025.2 |
| six | 1.17.0 | 1.17.0 |

PyArrow is absent in both environments, so the new pandas string type uses its
NumPy-backed implementation. pytz and tzdata remain installed in the after
environment even where no longer required, to hold the environment constant.
This isolates the installed package change to pandas; it does not imply that
every observed difference is a pandas defect.

## Compatibility and provenance

Verified on 2026-10-13 against the official
[pandas 2.3 installation guide](https://pandas.pydata.org/pandas-docs/version/2.3/getting_started/install.html),
[pandas 3.0 release requirements](https://pandas.pydata.org/docs/whatsnew/v3.0.0.html#increased-minimum-version-for-python),
and the release-specific PyPI metadata for
[pandas 2.3.3](https://pypi.org/pypi/pandas/2.3.3/json),
[pandas 3.0.0](https://pypi.org/pypi/pandas/3.0.0/json), and
[NumPy 2.2.6](https://pypi.org/pypi/numpy/2.2.6/json).

The installed package metadata is the executable compatibility check: pandas
2.3.3 requires Python >=3.9 and NumPy >=1.26.0 on Python 3.12; pandas 3.0.0 requires
Python >=3.11 and NumPy >=1.26.0 on Python <3.14. NumPy 2.2.6 requires Python
>=3.10. CPython 3.12.3 satisfies all three. Actual imports and transformations
passed in both environments. `dependency_metadata` in each manifest retains the
installed `Requires-Python` and `Requires-Dist` declarations.

The requirements files were generated from the version-specific PyPI JSON wheel
digests. `uv pip sync --require-hashes --only-binary :all:` enforces those hashes.
The tested setup tool is **uv 0.11.28**. Setup records its actual version, installed
packages, Python patch version, interpreter path, platform, requirements-file
hash, commands, durations, exit codes, and logs.

## Setup and reproduction

From the repository root, with CPython 3.12 and uv installed:

```sh
python3 scripts/setup_environments.py
python3 scripts/setup_environments.py --verify-install-failure
.venv/bin/python -m pytest tests/test_runner.py -q
```

Setup creates `.featureshift/envs/before` and `.featureshift/envs/after` using uv.
It syncs all six dependencies, checks the exact resulting package set, and saves
`.featureshift/setup/environments.json`, individual manifests, and immutable
`attempt-<id>.json` setup records. Setup failures are persisted as
`environment_error`; a missing environment cannot become a semantic finding.
The after environment is independently attempted if before setup fails.

Already matching environments are reused without fetching. To recreate missing
environments from previously fetched wheels only:

```sh
python3 scripts/setup_environments.py --offline
```

Retain `.featureshift/uv-cache` for this offline reconstruction. A new machine
still needs to fetch the pinned public wheels during setup. No dependency fetching
occurs in a transformation worker.

The real failure check invokes `uv pip install --offline pandas==999999.0.0`
against the before environment. uv must return a nonzero exit and the full
package manifest must remain unchanged. The check saves its actual command,
output, status, and `semantic_regression: false` to
`.featureshift/setup/install-failure-check.json`.

## Execution profile

Docker is unavailable on this host. Arbitrary-upload execution is disabled.
The supported profile is explicitly **trusted subprocess**, for repository-owned
examples and reviewed generated probes only. The caller must enforce its source
registry. This is not a secure sandbox: host filesystem and network access are
not isolated, and same-user code can change the copied input permissions.

Each worker gets a new process group, an environment containing only locale,
timezone, executable path, temporary directory, and numeric-library thread
settings; ambient credentials and application environment variables are not
forwarded. Python runs in isolated mode (`-I`) without bytecode writes (`-B`).
Inputs are copied into a dedicated artifact directory with read-only file
permissions; stdout, stderr, structured output, and the final execution record
are saved separately. Resource limits apply before pandas/NumPy imports:

| Limit | Value |
| --- | --- |
| Wall time | 8 seconds default; configurable up to 60 seconds |
| CPU | Wall timeout rounded up, plus one second hard-limit grace |
| Virtual address space | 1.5 GiB |
| Output file size | 8 MiB per file |
| Open file descriptors | 64 |
| Process count | RLIMIT_NPROC 32; this counts processes for the Unix user |
| Core dumps | Disabled |
| Fixture | 1 MiB, 10,000 rows, 100,000 cells |
| Source | 256 KiB |
| Structured result | 10,000 rows, 100,000 cells |
| Reported stdout/stderr | 64 KiB each, with a truncation flag |

The parent kills the entire process group on wall timeout and cleans up surviving
children after completion. POSIX process limits are not per-job containment and
may block child creation when the host user already has more processes. These
limits reduce accidental damage from trusted code; they do not authorize running
untrusted uploads. CPU/kill signal termination is reported as a worker timeout
or resource limit, not a pandas regression.

## Structured output contract

`run_worker(python, source, fixture, artifact_dir, entrypoint='transform',
timeout_s=8, test_mode=False)` returns `status`, `output`, `stdout`, `stderr`,
`exit_code`, `duration_s`, `versions`, `error`, input hashes, execution profile,
and artifact paths. Status is `ok`, `error`, `timeout`, or `environment_error`.
`error` is null or a mapping with `type`, `message`, and `stage`; worker
exceptions also retain a traceback.

The JSON fixture contains `data: {column: [values]}` with optional `dtypes`,
`date_columns`, and `index`. A categorical dtype can be declared as
`{"categories": ["low", "high"], "ordered": true}`. The entry point must return
a DataFrame. The output retains row count, positional column metadata, index
values/names, category order, and data cells. Numeric values remain JSON numbers.
Special scalars are explicit: `{"$null": "None"}`, `{"$null": "NaN"}`,
`{"$null": "NA"}`, `{"$null": "NaT"}`, and
`{"$float": "Infinity"}` / `{"$float": "-Infinity"}`. Timestamps, timedeltas,
and tuple index values also use tagged JSON encodings. Unsupported scalar types
fail serialization instead of silently stringifying objects.

`test_mode=True` calls `existing_test(df)` independently, with a newly loaded
fixture. Passing tests return `test_passed: true` and `output: null`; failed
assertions return an error. An absent optional test is explicitly identified as
`MissingExistingTest`, so callers can distinguish unavailable tests from passes.

## Executed checks

On 2026-10-13:

- Installed both complete environments with hash verification using uv 0.11.28;
  each contains exactly the six listed packages.
- `python3 scripts/setup_environments.py` returned `ok` and
  `shared_dependencies_constant: true`.
- `python3 scripts/setup_environments.py --verify-install-failure` exercised the
  impossible pin: actual uv exit 1, `environment_error`, unchanged environment.
- A clean pair was created at
  `/tmp/featureshift-clean-worker-offline-ygr8vcz7` with the warmed cache and
  `setup_environments(root, offline=True)`. All four creation/install commands
  returned exit 0; six packages installed per environment.
- A separate empty-cache setup in the restricted host failed DNS fetching from
  PyPI and persisted both environment failures. This is a real setup failure,
  not a simulated semantic result. Direct approved uv installation fetched the
  wheels successfully; cached offline recreation then passed.
- `.venv/bin/python -m pytest tests/test_runner.py -q`: 7 passed in 3.58 seconds
  on the initial integration run, including a terminated timeout followed by a
  healthy job, ambient-secret omission, null/category serialization, actual
  package versions, baseline assertions, and missing-environment handling.
- Ruff passed for the worker, runner, setup script, and runner tests; mypy
  passed for the runner.

A useful empirical correction: pandas 3.0.0's `select_dtypes(include=['object'])`
retains string columns for compatibility. The disappearing-feature acceptance
fixture therefore uses the actual legacy equality selector
`df.loc[:, df.dtypes == 'object']`, which retains the string feature in 2.3.3
and drops it in 3.0.0. Worker testing caught this distinction before it became a
false demonstration claim.
