"""Startup recovery covers all unfinished jobs, independently of UI history."""

from pathlib import Path

from featureshift.store import Store


def test_recovery_includes_interrupted_run_older_than_recent_history(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.save({"id": "interrupted", "created_at": "2026-01-01", "status": "running"})
    for index in range(200):
        store.save({"id": f"completed-{index}", "created_at": "2026-01-02", "status": "completed"})

    assert len(store.list()) == 200
    assert store.recover_interrupted() == 1
    recovered = store.get("interrupted")
    assert recovered["status"] == "failed"
    assert [event["kind"] for event in recovered["events"]] == ["interrupted"]
    assert store.get("completed-0")["status"] == "completed"
    assert store.recover_interrupted() == 0
