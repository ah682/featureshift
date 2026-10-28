# Data, licenses and provenance

`examples/cases.json` is the demonstration registry. Each entry names a reviewed
source file, its callable entry point, a small fixture, comparison contract and
expected outcome. `benchmarks/cases.json` contains 28 separately labeled replay
cases. Input data are fabricated, sanitized and have no personal/customer records.
Constructed fixtures are MIT-licensed project code. Historical adaptations retain
BSD-3-Clause attribution and links in each case's `provenance` and in
`evidence/historical.json`; redistribution notices are in `evidence/licenses/`.

Two real pandas regression families are replayed under the present upgrade pair:
the string-cast missing-value tests associated with issue #36904 (None, NaN and
pd.NA variants), and float32 string formatting associated with issue #36451.
They are adaptations of licensed repository regression tests, not claims to have
reproduced those issues under their original historical dependency environments.
The temporal control uses a 2020 cutoff; future migration evidence is withheld.
The supplied DoWhy/Ruff references were inspected for context and are not silently
relabeled as reproduced customer failures.

Each evidence source records URL, immutable commit, exact package/version scope,
release time, fetch time, byte length, SHA256 and license path. Indexed passages
record Unicode-codepoint offsets, excerpt hash, keywords and finite reviewed
behavior annotations. See `docs/EVIDENCE.md` for source availability details.
The unavailable versioned 3.0.0 HTML is replaced explicitly by its original release
commit source, not a mutable current documentation page.

Historical regression test snapshots are retained for provenance but excluded
from retrieval. Retrospective queries apply an explicit publication cutoff before
scoring, conservatively using source release timestamps. No later issue discussion,
resolution or fix is ingested as contemporaneous evidence.

Each execution report includes captured source/input, hashes, configuration,
resolved environments, stderr/stdout and structured values. Scalar nulls have
tagged encodings (`None`, `NaN`, `NA`, `NaT`) so contracts can distinguish or unify
them deliberately. Categories retain their mapping and ordering. Runtime artifacts
are local, ignored by source control and removed by the explicit reset command.

Add a case by creating a reviewed Python file and JSON fixture, then registering
provenance, expected outcome and a change family. Changes in the same family must
remain in the same split/fold. Expand with independently curated repositories and
case labels before interpreting benchmark scores as evidence of generalization.
