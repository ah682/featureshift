# Versioned evidence and permitted historical reproductions

FeatureShift retrieves offline passages from the official pandas repository at the exact release commits. The corpus supports **pandas 2.3.3 → 3.0.0** only. It does not silently generalize to another patch release or replace a missing source with today's documentation.

| Release | Immutable commit | Exact snapshot available by |
| --- | --- | --- |
| 2.3.3 | `9c8bc3e55188c8aff37207a74f1dd144980b8874` | 2025-09-29 22:12:37 UTC |
| 3.0.0 | `366ccdfcd8ed1e5543bfb6d4ee0c9bc519898670` | 2026-01-21 13:53:10 UTC |

The timestamps are the annotated release-tag timestamps, retained in `evidence/provenance`. They conservatively date the exact snapshot rather than guessing when an individual paragraph was first written. The original fetch timestamps and SHA-256 hashes are in `evidence/manifest.json`. GitHub tag references were resolved to immutable commit IDs before fetching source files. Current documentation is not used as historical evidence. The version/3.0.0 release-notes HTML endpoint returned 404 during inspection; its official release-tag RST is available and cached. This fallback is recorded in the manifest.

The cache contains ten files: the two string migration guides, two Copy-on-Write guides, two release notes, two API source files containing the `Series.sum` documentation, and two historical regression-test files. Twenty-three explicitly indexed passages cover string inference, dtype equality checks, compatible `select_dtypes`, null sentinels, conversion, assignment, categorical `groupby`, datetime resolution, and `sum(min_count=...)`. The two historical test files are provenance artifacts and are **never indexed for retrieval**. Full snapshots preserve the source context; the complete BSD 3-Clause licenses and copyright notices are included under `evidence/licenses`.

`manifest.json` records URL, title, package, source version, behavior scope, immutable commit, tag, published and fetched times, content hash, byte length, cache path, source kind, and license. `passages.json` records title, keywords, exact `[start, end)` offsets in Unicode codepoints of UTF-8-decoded source, a separate passage hash, behavior scope and reviewed assertions. Offsets refer to the raw cached RST/Python source, not rendered HTML. Reports carry the exact excerpt and its trace metadata.

## Retrieval and evidence boundaries

`featureshift.evidence.retrieve(query, before_version="2.3.3", after_version="3.0.0", limit=4, cutoff=None)` is a deterministic keyword baseline. It ranks matches with inverse document frequency, boosts reviewed titles/keywords, and uses stable tie-breaking. It does not call a model, embedding service, vector database, or network. Unsupported version pairs, an unrelated query, missing original sources, or a cutoff before the sources return an empty result. Cache integrity is checked before passages are eligible.

`evidence_supports(items, ..., cutoff=None)` rejects unknown or altered citations, wrong versions, invalid offsets/hashes, conflicts, and exclusively old-version evidence. A definitive documentation classification needs at least one matching target-release source. This function checks citation integrity; it is **not a semantic entailment model**. The caller must still match the transformation operation, execute both environments, and compare the observation with the quoted statement. Retrieved prose never becomes executable probe code.

Conflicts are explicit reviewed assertion annotations. Different values for the same behavior and exact behavior version mark all implicated passages as conflicting, including when one side is outside the result limit. An actual version transition is not a conflict. The current indexed claims contain no contradictory pair. Automatic discovery of arbitrary natural-language contradictions is not implemented.

`select_dtypes(include=["object"])` needs particular care: the pinned migration guide recommends `include=["object", "string"]` for compatibility but does not establish that object-only selection drops strings in 3.0.0. The installed 3.0.0 behavior retains strings with a compatibility warning. The mandatory feature-loss demonstration therefore uses `df.dtypes == "object"`, which the exact guide explicitly documents as changing. Selecting an excerpt about `select_dtypes` is never by itself proof of feature loss.

Run the offline integrity check:

```sh
python3 scripts/refresh_evidence.py --check
```

An explicit connected setup task can re-fetch a missing snapshot with `--fetch` (optionally `--source SOURCE_ID`). It fetches only the immutable URL, checks the original expected hash and size before atomic replacement, and refuses unexpected redirects/content changes. It never upgrades the corpus to current docs. The fetch log is separate from the original snapshot metadata. Restricted environments may block Python network access; offline cache validation and the demo still work. The initial download was performed with the environment's permitted `curl -fL` command, with actual byte hashes recorded afterward.

## Historical benchmark provenance and time cutoffs

`evidence/historical.json` records two genuine upstream regression families, each adapted from a BSD-licensed pandas regression test. The original issue metadata supplies dates and context; the repository license is **not** assumed to license issue prose. No complete issue body, issue comments, or later issue-resolution text is cached or indexed.

| Original issue | Licensed regression | Local adaptation |
| --- | --- | --- |
| [pandas #36904](https://github.com/pandas-dev/pandas/issues/36904), opened 2020-10-06 | `test_astype_to_str_preserves_na` | Explicit object input, `astype(str)`, with None/NaN/NA variants |
| [pandas #36451](https://github.com/pandas-dev/pandas/issues/36451), opened 2020-09-18 | `test_astype_from_float_dtype` | float32 value 0.1 converted to explicit `string[python]`; an unaffected historical control |

These are present-day replays on the selected pair, not claims that the original issue environments were recreated. Their metadata records transformation steps, permissions, source hashes, and change-family split groups. The user-supplied DoWhy tracking issue and Ruff rule discussion were reviewed for context; neither is an executable permitted regression dataset, and both remain outside retrieval. The string guide's reference to pandas #25353 remains in the official documentation; that issue's discussion is not copied.

For retrospective diagnosis, pass the original issue timestamp as `cutoff`. Retrieval requires the exact source snapshot's published time to be no later than the cutoff. Date-only values include the entire UTC day. A cutoff at either original historical issue date excludes the 2025/2026 snapshots and therefore produces insufficient documentation evidence; it does not leak a later fix or claim a retrospective success. Expanding retrospective coverage requires separately licensed, pinned sources available before those dates.

Verification is in `tests/test_evidence.py`: relevant-source selection, wrong-version and forged-citation rejection, snapshot and offset corruption, unavailable-source handling, timestamp boundaries, exclusion of historical fixes, explicit conflicts, and deterministic repeatability.
