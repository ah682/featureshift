"""Offline, exact-version keyword retrieval over licensed official snapshots.

Documentation is data: this module never executes source text, follows embedded
instructions, or substitutes an unversioned page when an archived source is missing.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any

CORPUS_DIR = Path(__file__).resolve().parent.parent / "evidence"
_STOP_WORDS = frozenset(
    "a an and are as at be by can code column columns data dataframe for from in "
    "is it of on or pandas series should the this to under using value values with".split()
)
_ALIASES = {
    "strings": "string", "dtypes": "dtype", "nulls": "null", "missing": "null",
    "categories": "category", "microsecond": "microseconds", "nanosecond": "nanoseconds",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _timestamp(value: str, *, end_of_day: bool = False) -> datetime:
    if len(value) == 10:
        result = datetime.combine(datetime.fromisoformat(value).date(), time.max if end_of_day else time.min)
    else:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def _root(corpus_dir: Path | str | None) -> Path:
    return Path(corpus_dir) if corpus_dir is not None else CORPUS_DIR


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Snapshot path leaves the evidence directory")
    return path


def _load(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _read_json(root / "manifest.json")
    passages = _read_json(root / "passages.json")
    if manifest.get("schema_version") != 1 or not isinstance(passages, list):
        raise ValueError("Unsupported evidence corpus schema")
    return manifest, passages


def validate_source(source: str | dict[str, Any], *, corpus_dir: Path | str | None = None) -> dict[str, Any]:
    """Validate a source ID or metadata against the local immutable snapshot.

    The result is explicit rather than truthy/falsey: inspect ``result['valid']``.
    Unknown, tampered, missing, non-official, and version-mislabeled sources fail.
    """
    root = _root(corpus_dir)
    errors: list[str] = []
    ident = source if isinstance(source, str) else source.get("source_id", source.get("id"))
    try:
        manifest, _ = _load(root)
        registered = next((entry for entry in manifest["sources"] if entry["id"] == ident), None)
        if registered is None:
            return {"valid": False, "source_id": ident, "errors": ["Unknown source"]}
        if isinstance(source, dict):
            for key in ("package", "source_version", "content_hash", "source_commit", "fetched_at"):
                if key in source and source[key] != registered.get(key):
                    errors.append(f"Source metadata mismatch: {key}")
            if "url" in source and source["url"].split("#", 1)[0] != registered["url"]:
                errors.append("Source metadata mismatch: url")
        version = registered["source_version"]
        release = manifest["releases"].get(version, {})
        commit = release.get("commit", "")
        expected_url = f"https://github.com/pandas-dev/pandas/blob/{commit}/{registered['repository_path']}"
        expected_download = f"https://raw.githubusercontent.com/pandas-dev/pandas/{commit}/{registered['repository_path']}"
        if registered.get("package") != "pandas":
            errors.append("Unsupported package")
        if not re.fullmatch(r"[0-9a-f]{40}", commit) or registered.get("source_commit") != commit:
            errors.append("Source is not pinned to the registered release commit")
        if registered.get("release_tag") != f"v{version}":
            errors.append("Release tag/version mismatch")
        if registered.get("url") != expected_url or registered.get("download_url") != expected_download:
            errors.append("URL is not the official immutable source for this release")
        if registered.get("license") != "BSD-3-Clause" or not _inside(root, registered["license_path"]).is_file():
            errors.append("Missing redistribution license")
        if registered.get("published_at") != release.get("published_at"):
            errors.append("Release timestamp mismatch")
        _timestamp(registered["published_at"])
        _timestamp(registered["fetched_at"])
        raw = _inside(root, registered["snapshot_path"]).read_bytes()
        raw.decode("utf-8")
        if _digest(raw) != registered["content_hash"]:
            errors.append("Snapshot content hash mismatch")
        if len(raw) != registered["byte_length"]:
            errors.append("Snapshot byte length mismatch")
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        errors.append(f"Source unavailable or invalid: {exc}")
    return {"valid": not errors, "source_id": ident, "errors": errors}


def _valid_passages(root: Path, manifest: dict[str, Any], passages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sources = {source["id"]: source for source in manifest["sources"]}
    valid_sources = {ident: validate_source(ident, corpus_dir=root) for ident in sources}
    texts: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen: set[str] = set()
    for passage in passages:
        ident = passage.get("id", "<unknown>")
        try:
            source_id = passage["source_id"]
            source = sources[source_id]
            if not valid_sources[source_id]["valid"]:
                raise ValueError("Parent snapshot is invalid")
            if ident in seen:
                raise ValueError("Duplicate passage ID")
            seen.add(ident)
            if source_id not in texts:
                texts[source_id] = _inside(root, source["snapshot_path"]).read_bytes().decode("utf-8")
            full = texts[source_id]
            start, end = passage["start"], passage["end"]
            if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(full)):
                raise ValueError("Passage offsets are out of range")
            excerpt = full[start:end]
            if passage.get("offset_unit") != "unicode_codepoints" or _digest(excerpt.encode("utf-8")) != passage["passage_hash"]:
                raise ValueError("Passage hash or offset unit mismatch")
            if not set(passage["applies_to"]).issubset(set(source["applies_to"])):
                raise ValueError("Passage version scope exceeds source scope")
            results.append({**source, **passage, "source_title": source["title"], "passage": excerpt})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failures.append({"id": ident, "errors": [str(exc)]})
    return results, failures


def corpus_status(*, corpus_dir: Path | str | None = None) -> dict[str, Any]:
    """Report offline cache integrity, exact release scope, and limitations."""
    root = _root(corpus_dir)
    try:
        manifest, passages = _load(root)
        checks = [validate_source(source["id"], corpus_dir=root) for source in manifest["sources"]]
        valid, bad_passages = _valid_passages(root, manifest, passages)
        errors = [entry for entry in checks if not entry["valid"]]
        return {
            "available": not errors and not bad_passages,
            "mode": "offline_keyword", "schema_version": manifest["schema_version"],
            "supported_pairs": manifest["supported_pairs"], "source_count": len(checks),
            "valid_source_count": sum(check["valid"] for check in checks),
            "passage_count": len(valid),
            "retrievable_source_count": sum(bool(s["retrieval_eligible"]) for s in manifest["sources"]),
            "source_errors": errors, "passage_errors": bad_passages,
            "source_unavailability": manifest.get("source_unavailability", []),
            "retrospective_policy": manifest["retrospective_policy"],
            "sources": [{key: source[key] for key in ("id", "title", "url", "source_version", "fetched_at", "content_hash", "license", "retrieval_eligible")} for source in manifest["sources"]],
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"available": False, "mode": "offline_keyword", "source_count": 0, "passage_count": 0,
                "source_errors": [{"errors": [str(exc)]}], "passage_errors": [], "supported_pairs": []}


def _tokens(text: str) -> set[str]:
    return {_ALIASES.get(token, token) for token in re.findall(r"[a-z0-9_]+", text.lower()) if token not in _STOP_WORDS}


def _mark_conflicts(items: list[dict[str, Any]], versions: set[str]) -> None:
    """Disagreement for one behavior/version blocks every implicated passage.

    A legitimate change between 2.3.3 and 3.0.0 is not a conflict. The finite
    assertion annotations are hand-reviewed index metadata, not generated facts.
    """
    assertions: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for item in items:
        for assertion in item.get("assertions", []):
            if assertion["behavior_version"] in versions:
                assertions[(assertion["key"], assertion["behavior_version"])][assertion["value"]].add(item["id"])
    conflicts: dict[str, set[str]] = defaultdict(set)
    for values in assertions.values():
        if len(values) > 1:
            all_ids = set().union(*values.values())
            for ident in all_ids:
                conflicts[ident].update(all_ids - {ident})
    for item in items:
        item["conflicts_with"] = sorted(conflicts[item["id"]])
        item["conflict"] = bool(item["conflicts_with"] or item.get("declared_conflict"))
        item["conflict_reason"] = "Conflicting indexed claims about the same behavior and exact version" if item["conflicts_with"] else item.get("declared_conflict", "")


def retrieve(query: str, before_version: str = "2.3.3", after_version: str = "3.0.0", limit: int = 4,
             cutoff: str | None = None, *, corpus_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """Retrieve relevant, validated passages for the supported exact version pair.

    No network or model is used. A missing source, unsupported version pair,
    unrelated query, or cutoff preceding every eligible snapshot returns ``[]``.
    A date-only cutoff includes that whole UTC day; timestamps are exact.
    """
    if limit <= 0 or not _tokens(query):
        return []
    root = _root(corpus_dir)
    try:
        manifest, passages = _load(root)
        if [before_version, after_version] not in manifest["supported_pairs"]:
            return []
        deadline = _timestamp(cutoff, end_of_day=True) if cutoff else None
        all_items, _ = _valid_passages(root, manifest, passages)
    except (OSError, ValueError, KeyError, TypeError):
        return []
    versions = {before_version, after_version}
    candidates = [item for item in all_items if item["retrieval_eligible"]
                  and item["source_version"] in versions and set(item["applies_to"]) & versions
                  and (deadline is None or _timestamp(item["published_at"]) <= deadline)]
    _mark_conflicts(candidates, versions)
    query_tokens = _tokens(query)
    token_sets = [_tokens(item["title"] + " " + " ".join(item["keywords"]) + " " + item["passage"]) for item in candidates]
    frequencies = Counter(token for token_set in token_sets for token in token_set)
    scored = []
    for item, body_tokens in zip(candidates, token_sets):
        index_tokens = _tokens(item["title"] + " " + " ".join(item["keywords"]))
        matches = query_tokens & body_tokens
        # A word buried elsewhere in a long passage alone is insufficient.
        if not matches or not query_tokens & index_tokens:
            continue
        weights = {token: 1 + math.log((len(candidates) + 1) / (frequencies[token] + 1)) for token in matches}
        score = sum(weight * (3 if token in index_tokens else 1) for token, weight in weights.items())
        item["score"] = round(score, 6)
        item["matched_terms"] = sorted(matches)
        item["retrieval_cutoff"] = cutoff
        item["source_validated"] = True
        item["supports_definitive"] = not item["conflict"] and item["source_version"] == after_version
        scored.append(item)
    scored.sort(key=lambda item: (-item["score"], item["source_version"] != after_version, item["id"]))
    return scored[:limit]


def evidence_supports(items: list[dict[str, Any]], before_version: str = "2.3.3", after_version: str = "3.0.0",
                      cutoff: str | None = None, *, corpus_dir: Path | str | None = None) -> bool:
    """Guard citation integrity; this is not a semantic entailment model.

    A definitive documented-change classification requires a verified target
    release passage and no conflict, with runtime/operation matching performed
    by the caller. Earlier guide predictions alone are insufficient.
    """
    if not items:
        return False
    root = _root(corpus_dir)
    try:
        manifest, passages = _load(root)
        if [before_version, after_version] not in manifest["supported_pairs"]:
            return False
        deadline = _timestamp(cutoff, end_of_day=True) if cutoff else None
        registered, _ = _valid_passages(root, manifest, passages)
        registered = [item for item in registered if item["retrieval_eligible"] and item["source_version"] in {before_version, after_version}
                      and (deadline is None or _timestamp(item["published_at"]) <= deadline)]
        _mark_conflicts(registered, {before_version, after_version})
        by_id = {item["id"]: item for item in registered}
        target_evidence = False
        for item in items:
            canonical = by_id.get(item.get("id", ""))
            if canonical is None or canonical["conflict"] or item.get("conflict"):
                return False
            for key in ("source_version", "url", "content_hash", "passage_hash", "start", "end", "passage", "applies_to", "fetched_at"):
                if item.get(key) != canonical[key]:
                    return False
            if after_version in canonical["applies_to"] and canonical["source_version"] == after_version:
                target_evidence = True
        return target_evidence
    except (OSError, ValueError, KeyError, TypeError):
        return False
