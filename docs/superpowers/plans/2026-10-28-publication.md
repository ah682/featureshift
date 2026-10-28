# FeatureShift publication implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. The existing user authorization covers autonomous execution; the release coordinator handles independent review and publication.

**Goal:** Publish a reproducible, accurately documented local pandas upgrade preflight.

**Architecture:** Retain the closed trusted-case registry, two pinned worker environments, deterministic evidence/probe baseline, SQLite audit and local report UI. Harden confirmed defects without redesigning the accepted implementation.

**Tech stack:** Python 3.12, pandas 2.3.3/3.0.0, NumPy 2.2.6, FastAPI, SQLite, uv, pytest, Ruff and mypy.

**Spec:** `01_ML_Upgrade_Preflight_Prompt.txt`, retained locally as the original build brief; implementation scope and public limitations are documented in `README.md` and `docs/ARCHITECTURE.md`.

## Global constraints

- Run only repository-owned trusted transformations; uploads remain unavailable.
- Keep shared worker packages constant and exact versions/hash locks intact.
- No fabricated historical environments, human latency, model results or customer validation.
- Do not touch the original project, publish, or use GitHub credentials in this task.

## Review focus

- Environment-provided server configuration must preserve the loopback-only boundary.
- Startup recovery must handle interrupted runs beyond the UI's bounded recent history.
- Clean source must include every fixture, evidence snapshot and asset used by demo commands.
- Standalone exported tests must actually replay old/new behavior without application installation.
- Measured results must be available from committed documentation or reproducible commands, not absent development-state files.

### Task 1: Harden confirmed runtime boundaries

**Files:** `featureshift/cli.py`, `featureshift/store.py`, new CLI/store tests.
**Interfaces:** Existing `main(argv) -> int`, `Store.recover_interrupted() -> int` remain stable.

- [x] Run existing checks from a fresh copied wheel cache and new environments.
- [x] Write a reproducer for environment-provided non-loopback hosts; run it and verify failure before fixing validation.
- [x] Write a recovery test with an interrupted run outside the newest 200 runs; verify failure before querying all unfinished runs directly.
- [x] Run focused tests and the full suite; commit the fixes only after checks pass.

### Task 2: Package the source release and document fresh evidence

**Files:** `README.md`, `.gitignore`, `.github/workflows/ci.yml`, `docs/BUILD_STATE.md`, `docs/VERIFICATION.md`, relevant release documentation.
**Interfaces:** Keep `make demo`, `make check`, `make test`, `make evaluate` and existing CLI behavior reproducible from the checkout.

- [x] Execute setup, lint/types, full tests, evidence-integrity check, demo seeding and full diagnostic evaluation.
- [x] Inspect source distribution inputs and README links; remove references to unavailable development artifacts as evidence of this checkout.
- [x] Retain the original prompt locally while excluding it from public release source if it adds process noise rather than user documentation.
- [x] Update measured evidence, scope and honest remaining gates. Retain a compact machine-readable evaluation summary if appropriate.
- [x] Verify a clean source copy, commit the reviewed release changes, and hand exact results/limits to the coordinator for independent browser/release review.
