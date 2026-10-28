#!/usr/bin/env python3
"""Verify offline evidence, or re-fetch exactly the pinned source bytes.

This is an explicit setup task. Ordinary retrieval never calls the network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from featureshift.evidence import corpus_status  # noqa: E402


def refresh(source_id: str | None = None) -> list[dict[str, str]]:
    """Repair snapshots from immutable allowlisted URLs without changing pins."""
    directory = ROOT / "evidence"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    sources = [source for source in manifest["sources"] if source_id is None or source["id"] == source_id]
    if not sources:
        raise ValueError(f"Unknown source: {source_id}")
    events = []
    for source in sources:
        release = manifest["releases"][source["source_version"]]
        expected_url = f"https://raw.githubusercontent.com/pandas-dev/pandas/{release['commit']}/{source['repository_path']}"
        if source["download_url"] != expected_url or source["source_commit"] != release["commit"]:
            raise ValueError(f"Source does not match its immutable release pin: {source['id']}")
        destination = (directory / source["snapshot_path"]).resolve()
        if not destination.is_relative_to(directory.resolve()):
            raise ValueError("Snapshot destination escapes evidence directory")
        raw = b""
        for attempt in range(3):
            try:
                request = Request(expected_url, headers={"User-Agent": "FeatureShift-evidence-cache/0.1"})
                with urlopen(request, timeout=20) as response:
                    if response.url != expected_url:
                        raise ValueError("Unexpected source redirect; no fallback is permitted")
                    raw = response.read(2_000_001)
                break
            except (URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
        if len(raw) > 2_000_000 or len(raw) != source["byte_length"]:
            raise ValueError(f"Unexpected source size: {source['id']}")
        if "sha256:" + hashlib.sha256(raw).hexdigest() != source["content_hash"]:
            raise ValueError(f"Source hash changed; refusing to replace cached evidence: {source['id']}")
        raw.decode("utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Validate fully before replacing a working cache entry.
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
            temporary.write(raw)
            temp_path = Path(temporary.name)
        temp_path.replace(destination)
        events.append({"source_id": source["id"], "verified_at": datetime.now(timezone.utc).isoformat(), "content_hash": source["content_hash"]})
    (directory / "refresh-log.json").write_text(json.dumps(events, indent=2) + "\n", encoding="utf-8")
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Validate cached metadata, snapshots and passages without network (default)")
    mode.add_argument("--fetch", action="store_true", help="Re-fetch exact immutable snapshots; reject content changes")
    parser.add_argument("--source", help="Re-fetch a single source ID; requires --fetch")
    args = parser.parse_args()
    if args.source and not args.fetch:
        parser.error("--source requires --fetch")
    try:
        if args.fetch:
            refresh(args.source)
        status = corpus_status()
    except (OSError, ValueError, KeyError, URLError) as exc:
        print(json.dumps({"available": False, "error": str(exc)}))
        return 1
    print(json.dumps({key: value for key, value in status.items() if key != "sources"}, indent=2))
    return 0 if status["available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
