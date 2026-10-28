"""SQLite persistence and append-only review events (schema migration 1)."""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path


def now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, state: Path):
        self.state = state
        self.state.mkdir(parents=True, exist_ok=True)
        self.path = state / "featureshift.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO schema_version VALUES (1);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, report TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );
            """)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        return db

    def save(self, report: dict, event: str | None = None, payload: dict | None = None) -> None:
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO runs VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET report=excluded.report",
                       (report["id"], report["created_at"], json.dumps(report, allow_nan=False)))
            if event:
                db.execute("INSERT INTO events(run_id,created_at,kind,payload) VALUES(?,?,?,?)",
                           (report["id"], now(), event, json.dumps(payload or {})))

    def get(self, run_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT report FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            report = json.loads(row[0])
            report["events"] = [{"seq": seq, "created_at": at, "kind": kind, "payload": json.loads(data)}
                                for seq, at, kind, data in db.execute(
                                    "SELECT seq,created_at,kind,payload FROM events WHERE run_id=? ORDER BY seq",
                                    (run_id,))]
            return report

    def list(self) -> list[dict]:
        with self.connect() as db:
            reports = [json.loads(r[0]) for r in db.execute("SELECT report FROM runs ORDER BY created_at DESC LIMIT 200")]
        return [{k: r.get(k) for k in ("id", "case_id", "title", "status", "created_at", "summary")} for r in reports]

    def accept(self, run_id: str, finding_id: str, reason: str) -> dict:
        if not reason.strip():
            raise ValueError("A review reason is required.")
        with self.lock:
            report = self.get(run_id)
            if report["status"] not in ("completed", "partial"):
                raise ValueError("Wait for the run to finish before reviewing findings.")
            matches = [f for f in report["findings"] if f["id"] == finding_id]
            if not matches:
                raise KeyError(finding_id)
            finding = matches[0]
            if finding["type"] in ("probe_environment_error", "insufficient_evidence"):
                raise ValueError("An execution/evidence error cannot be accepted as an intended change.")
            finding.update(accepted=True, acceptance_reason=reason.strip(), accepted_at=now())
            report["summary"]["accepted"] = sum(bool(f.get("accepted")) for f in report["findings"])
            report["summary"]["unaccepted_changes"] = sum(f["type"] == "observed_change" and not f.get("accepted") for f in report["findings"])
            self.save(report, "finding_accepted", {"finding_id": finding_id, "reason": reason.strip(), "origin": "reviewer"})
            return self.get(run_id)

    def recover_interrupted(self) -> int:
        count = 0
        for summary in self.list():
            if summary["status"] in ("queued", "running"):
                report = self.get(summary["id"])
                report.update(status="failed", error="The local service stopped before this run completed. Rerun the case.")
                self.save(report, "interrupted")
                count += 1
        return count

