"""Wrong versions, tampering and future knowledge never become evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from featureshift.evidence import (
    CORPUS_DIR,
    corpus_status,
    evidence_supports,
    retrieve,
    validate_source,
)


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    destination = tmp_path / "evidence"
    shutil.copytree(CORPUS_DIR, destination)
    return destination


def test_cached_corpus_contains_both_official_releases_and_licensed_history() -> None:
    status = corpus_status()
    assert status["available"], status
    assert status["supported_pairs"] == [["2.3.3", "3.0.0"]]
    assert {source["source_version"] for source in status["sources"]} == {"2.3.3", "3.0.0"}
    assert all(source["license"] == "BSD-3-Clause" for source in status["sources"])
    history = json.loads((CORPUS_DIR / "historical.json").read_text())["reproductions"]
    assert len({entry["split_group"] for entry in history}) >= 2
    assert all(not entry["retrieval_eligible"] and not entry["permission"]["issue_prose_copied"] for entry in history)


@pytest.mark.parametrize(("query", "expected_suffix"), [
    ("dtype object string check is_string_dtype feature selector", "dtype-check"),
    ("select_dtypes object string", "select-dtypes"),
    ("astype str null", "astype-str"),
    ("null sentinel", "null-sentinel"),
    ("chained assignment copy-on-write", "chained-assignment"),
    ("categorical groupby observed", "groupby-observed"),
    ("datetime unit resolution", "datetime-resolution"),
    ("sum min_count", "sum-min-count"),
])
def test_operation_query_retrieves_exact_matching_version(query: str, expected_suffix: str) -> None:
    items = retrieve(query)
    assert any(item["id"] == f"pandas-3.0.0-{'cow' if expected_suffix == 'chained-assignment' else 'release-notes' if expected_suffix in ('groupby-observed', 'datetime-resolution') else 'sum-api' if expected_suffix == 'sum-min-count' else 'strings'}:{expected_suffix}" for item in items)
    assert evidence_supports(items)
    assert all(item["source_version"] in {"2.3.3", "3.0.0"} for item in items)
    assert all(not item["conflict"] for item in items)


def test_passage_offsets_and_hashes_reproduce_exact_bytes() -> None:
    items = retrieve("astype str null")
    for item in items:
        raw = (CORPUS_DIR / item["snapshot_path"]).read_bytes()
        assert item["content_hash"] == "sha256:" + hashlib.sha256(raw).hexdigest()
        assert raw.decode("utf-8")[item["start"]:item["end"]] == item["passage"]
        assert item["passage_hash"] == "sha256:" + hashlib.sha256(item["passage"].encode("utf-8")).hexdigest()
        assert validate_source(item)["valid"]


def test_wrong_version_and_forged_citations_cannot_support_findings() -> None:
    assert retrieve("string dtype", after_version="3.0.6") == []
    assert retrieve("string dtype", before_version="2.2.0") == []
    assert retrieve("string dtype", before_version="3.0.0", after_version="2.3.3") == []
    items = retrieve("astype str null")
    for key, value in (("source_version", "3.0.6"), ("passage", "invented claim"),
                       ("url", "https://pandas.pydata.org/docs/current.html"), ("end", 1)):
        forged = copy.deepcopy(items)
        forged[0][key] = value
        assert not evidence_supports(forged), key
    assert not evidence_supports(items, after_version="3.0.6")
    assert not evidence_supports([item for item in items if item["source_version"] == "2.3.3"])
    assert not validate_source({"id": "pandas-3.0.0-strings", "source_version": "2.3.3"})["valid"]


def test_missing_or_corrupted_original_source_has_no_current_docs_fallback(corpus: Path) -> None:
    for path in (corpus / "snapshots").glob("*"):
        if "historical" not in path.name:
            path.unlink()
    assert not corpus_status(corpus_dir=corpus)["available"]
    assert retrieve("string dtype", corpus_dir=corpus) == []
    assert not evidence_supports(retrieve("string dtype"), corpus_dir=corpus)


def test_corrupted_snapshot_and_offsets_are_excluded(corpus: Path) -> None:
    path = corpus / "snapshots" / "pandas-3.0.0-strings.rst"
    path.write_bytes(path.read_bytes() + b"injected source statement")
    assert not validate_source("pandas-3.0.0-strings", corpus_dir=corpus)["valid"]
    assert all(item["source_id"] != "pandas-3.0.0-strings" for item in retrieve("astype str", corpus_dir=corpus))
    passages = json.loads((corpus / "passages.json").read_text())
    target = next(item for item in passages if item["id"] == "pandas-2.3.3-strings:astype-str")
    target["start"] += 1
    (corpus / "passages.json").write_text(json.dumps(passages))
    assert all(not item["id"].endswith(":astype-str") for item in retrieve("astype str", corpus_dir=corpus))
    assert corpus_status(corpus_dir=corpus)["passage_errors"]


def test_cutoff_uses_original_snapshot_availability_not_fetch_date() -> None:
    assert retrieve("astype str null", cutoff="2019-02-17T15:03:15Z") == []
    assert retrieve("string dtype", cutoff="2025-09-28") == []
    old = retrieve("astype str null", cutoff="2026-01-21T13:53:09Z")
    assert old and all(item["source_version"] == "2.3.3" for item in old)
    assert not evidence_supports(old, cutoff="2026-01-21T13:53:09Z")
    new = retrieve("astype str null", cutoff="2026-01-21T13:53:10Z")
    assert evidence_supports(new, cutoff="2026-01-21T13:53:10Z")
    assert not evidence_supports(new, cutoff="2026-01-20")
    assert all("historical" not in item["source_id"] for item in retrieve("astype str", limit=100))


def test_conflicting_claims_are_visible_even_when_limit_hides_other_passage(corpus: Path) -> None:
    path = corpus / "passages.json"
    passages = json.loads(path.read_text())
    conflicting = next(item for item in passages if item["id"] == "pandas-2.3.3-strings:astype-str")
    # Simulate an explicitly reviewed conflicting claim about the SAME 3.0.0 behavior.
    conflicting["assertions"][0]["value"] = "stringified"
    path.write_text(json.dumps(passages))
    items = retrieve("astype str null", limit=1, corpus_dir=corpus)
    assert len(items) == 1 and items[0]["conflict"]
    assert "pandas-2.3.3-strings:astype-str" in items[0]["conflicts_with"]
    assert not items[0]["supports_definitive"]
    assert not evidence_supports(items, corpus_dir=corpus)


def test_empty_unrelated_and_repeated_queries_do_not_invent_support() -> None:
    assert retrieve("") == []
    assert retrieve("sklearn quantum teleportation") == []
    assert retrieve("astype str", limit=0) == []
    assert not evidence_supports([])
    assert retrieve("astype str") == retrieve("astype str")
