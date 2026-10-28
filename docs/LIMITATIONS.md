# Current limitations and unperformed validation

- The verified pair is pandas 2.3.3 → 3.0.0 on CPython 3.12.3, Linux x86_64,
  NumPy 2.2.6, with no PyArrow. Other pandas patches, operating systems and
  dependency combinations have not been validated. Worker wheel locks deliberately
  support this platform. Non-pandas environment drift is reported as a confounder.
- Only reviewed repository cases execute. Uploads remain disabled even if Docker
  happens to be installed. Resource-limited subprocesses can access host files and
  network, and are not a secure sandbox. There is no untrusted-code profile.
- Baseline probes use finite AST rules and missing-value injection. They do not
  explore every input, prove equivalence, infer business intent, or understand
  arbitrary feature pipelines. Stable repeated samples are a check, not a proof
  of determinism. There is no paid/live model or embedding provider.
- Rule-based evidence matching is deliberately conservative. Hash integrity and
  version correctness do not prove that a passage explains every downstream effect.
  Missing, conflicting or temporally ineligible evidence stays visible as uncertainty.
- The benchmark is small and curated. Historical inputs are present-day replays,
  not validation of original environments. Family grouping reduces obvious leakage
  but does not make this an independently collected heldout customer evaluation.
- Existing-tests and edgetest-style baselines reuse the same executed test outcomes
  for a controlled exact dependency pair. The edgetest package itself is not run;
  there is no fabricated coding-assistant comparison.
- Human review latency, maintenance burden, customer value and commercial demand
  have not been measured. Report preparation time is measured separately. No
  market-validation claim is made, and nothing has been published or deployed.
- Only DataFrame outputs with supported scalar encodings are accepted. Inputs
  are small JSON fixtures. Duplicate feature labels are rejected; unordered
  tolerant comparison is limited to 500 rows. Datetime values/categories are
  supported; arbitrary object graphs, distributed dataframes and stateful jobs are not.
- A proposed patch may preserve columns while still changing dtype or null
  representation. Validation lists remaining differences; patches never auto-apply.
  Downloaded regression artifacts capture old behavior and need review for intentional
  changes. A determinism/environment error cannot be accepted as an intended change.
- The local API is a single-user loopback application without production auth,
  multi-tenant isolation or remote deployment hardening. CI configuration is provided;
  remote CI and external integration runs remain unperformed.
