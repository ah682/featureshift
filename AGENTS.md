# Working on FeatureShift

Read [CONTRIBUTING.md](CONTRIBUTING.md), [ARCHITECTURE.md](docs/ARCHITECTURE.md), and the relevant evidence/evaluation contract before changing behavior. The current audit is [QUALITY_AUDIT.md](docs/QUALITY_AUDIT.md).

- When available, apply Ponytail and the relevant Superpowers skills. Reproduce the defect, write one useful failing regression, fix the shared cause, run the relevant checks, then obtain a fresh independent review of substantive code or workflow changes. Use the existing authorized review process; add no approval gates or required agent counts.
- Search callers, fixtures and exported regression code before changing an interface. Reuse the current registry, runner, store and UI patterns; add no speculative execution framework.
- Keep pandas 2.3.3 and 3.0.0, their shared pins, and versioned evidence fixed unless the task explicitly changes the comparison protocol. Preserve hashes, cutoffs, exact citations and dated results.
- Registered source is trusted; arbitrary uploaded code stays unavailable. Process limits do not establish sandbox security. Unsupported providers must stay explicitly unavailable.
- Keep review acceptance separate from observed differences. A late request must not replace a newer report selection or its download links.
- Use `make check` and `make test` for runtime changes; add `make evaluate` and `scripts/refresh_evidence.py --check` when comparison or evidence changes. UI changes use both browser scripts in [the QA notes](scripts/browser-qa-notes.md), including their delayed-response checks.
- For docs-only changes, check links, commands and claims. Do not rerun the full experiment just to edit prose. Report skipped checks honestly and keep hosted CI status separate from local results.
- Preserve retained state, MIT licensing and upstream notices. Use disposable local data for failures and browser tests; do not reset user investigations or send their content to external services.
