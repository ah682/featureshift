# Five-minute demonstration

1. Run `make demo` and open `http://127.0.0.1:8765`. The selected **Object dtype
   selector** report is real, seeded execution. Inspect the `segment` feature in
   the old output and its absence in the new output. Existing tests pass because
   they check rows only. The explicit column contract fails.
2. Open the finding evidence and source panels. Inspect the exact 2.3.3/3.0.0
   sources, offsets and hashes, the executed source, generated missing-value probe,
   and each environment's versions and logs. A reviewed selector diff restores
   membership; remaining dtype differences are disclosed.
3. Select **Spend per visit**, then run it or open the seeded history item. It has
   no observed differences and no defect/contract finding. This says only what the
   fixture and boundary probe measured; it is not a universal upgrade certificate.
4. Open **Adopt the string dtype**. The dtype change is accepted by a declared
   contract; missing sentinels are compared by missingness. The observation and
   acceptance rationale remain in the audit. To exercise manual review, accept an
   observed selector finding with a written reason; it remains in downloads.
5. Run **Dependency setup failure stays an environment error** or
   `.venv/bin/python -m featureshift run install-failure`. A deliberately impossible
   dependency fails a real offline install without changing the working environment.
   The report shows an environment failure and no semantic regression.

For a second failure demonstration, run `probe-timeout`, then `numeric`. The
generated timeout control is killed, and the next run still succeeds. Run
`stochastic` to see cross-version attribution withheld because repeated output
changes in the same environment.

To inspect behavior beyond the supplied fixture, run `probe-only-null`. Its
original no-null input and existing tests pass in both environments. The generated
missing-value probe changes a derived indicator from 0 to 1 in pandas 3.0.0. This
is a deliberately constructed mechanism check, not independent customer evidence.
Its downloadable regression test replays the boundary probe, so it passes before
and fails after the upgrade despite the original fixture remaining equivalent.

Download JSON/HTML and the regression artifact from a deterministic successful
run. Execute the selector test using each pinned interpreter: old passes, new
fails. Run `make evaluate` for the complete labeled replay suite and baseline
comparison. Stop the server before `make reset` to return to a clean report state.
