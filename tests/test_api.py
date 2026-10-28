"""API boundary, asynchronous execution, review and downloadable audit behavior."""

from __future__ import annotations

import html
import json
import time
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_artifacts import captured_selector as captured_selector

from featureshift.api import create_app
from featureshift.config import ENV_ROOT
from featureshift.models import RunRequest


def test_unknown_examples_paths_and_uploaded_source_are_rejected(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        assert client.post("/api/runs", json={"case_id": "unknown-example"}).status_code == 404
        assert client.post("/api/runs", json={"case_id": "../../untrusted.py"}).status_code == 422
        assert client.post("/api/runs", json={"case_id": "numeric", "source": "print('untrusted')"}).status_code == 422
        assert client.post("/api/runs", json={"case_id": "numeric", "fixture": "/tmp/private.json"}).status_code == 422
        assert client.get("/api/runs/nonexistent").status_code == 404
        assert client.get("/api/runs/nonexistent/report.json").status_code == 404
        assert client.get("/api/runs").json() == []


def test_cross_origin_mutations_uploads_and_oversized_controls_are_disabled(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        blocked = client.post("/api/runs", json={"case_id": "numeric"}, headers={"Origin": "https://external.example"})
        assert blocked.status_code == 403 and "Cross-origin" in blocked.json()["detail"]
        upload = client.post("/api/uploads", json={"source": "untrusted"}, headers={"Origin": "http://testserver"})
        assert upload.status_code == 403 and "disabled" in upload.json()["detail"]
        oversized = client.post("/api/runs", content=json.dumps({"case_id": "x" * 20_000}), headers={"Content-Type": "application/json"})
        assert oversized.status_code == 413
        assert client.get("/api/status").json()["uploads_enabled"] is False
        assert client.get("/api/runs").json() == []
        assert client.get("/", headers={"Host": "external.example"}).status_code == 400


def test_malformed_origin_is_rejected_without_creating_a_run(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path), raise_server_exceptions=False) as client:
        response = client.post(
            "/api/runs", json={"case_id": "numeric"}, headers={"Origin": "http://["}
        )
        assert response.status_code == 403
        assert client.get("/api/runs").json() == []


def test_failed_creation_releases_queue_capacity(tmp_path: Path, monkeypatch) -> None:
    app = create_app(tmp_path)
    engine = app.state.engine
    create = engine.create

    def disk_full(request):
        raise OSError("No space left on device")

    with TestClient(app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(engine, "create", disk_full)
        for _ in range(8):
            assert client.post("/api/runs", json={"case_id": "numeric"}).status_code == 500
        monkeypatch.setattr(engine, "create", create)
        monkeypatch.setattr(engine, "execute", lambda run_id: None)
        response = client.post("/api/runs", json={"case_id": "numeric"})
        assert response.status_code == 202
        assert client.get(f"/api/runs/{response.json()['id']}").status_code == 200


@pytest.mark.integration
@pytest.mark.skipif(not all((ENV_ROOT / side / "bin" / "python").exists() for side in ("before", "after")), reason="Run make setup for real queued workers")
def test_queued_numeric_run_completes_with_json_html_and_regression_downloads(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        start = client.post("/api/runs", json={"case_id": "numeric"}, headers={"Origin": "http://testserver"})
        assert start.status_code == 202 and start.json()["status"] == "queued"
        run_id = start.json()["id"]
        # This job performs 12 sequential worker runs, each with its own metadata
        # check and execution deadline. Completion is the assertion here, not a
        # 15-second performance target for shared CI hardware.
        deadline = time.monotonic() + 300
        while True:
            response = client.get(f"/api/runs/{run_id}")
            assert response.status_code == 200
            report = response.json()
            if report["status"] in ("completed", "partial", "failed"):
                break
            assert report["status"] in ("queued", "running")
            assert time.monotonic() < deadline, f"Queued numeric run did not finish: {report['status']}"
            time.sleep(0.1)
        assert report["status"] == "completed", report["findings"]
        assert report["summary"]["equivalent"] is True
        assert {"queued", "running", "completed"}.issubset({event["kind"] for event in report["events"]})
        assert len(report["executions"]["before"]) == len(report["executions"]["after"]) == 2
        for artifact, media in (("report.json", "application/json"), ("report.html", "text/html"), ("regression_test.py", "text/x-python")):
            downloaded = client.get(f"/api/runs/{run_id}/{artifact}")
            assert downloaded.status_code == 200
            assert downloaded.headers["content-type"].startswith(media)
            assert downloaded.headers["content-disposition"].startswith("attachment;")
            assert downloaded.headers["x-content-type-options"] == "nosniff"
            assert downloaded.content
        assert client.get(f"/api/runs/{run_id}/report.json").json()["summary"] == report["summary"]
        assert "def test_captured_feature_behavior" in client.get(f"/api/runs/{run_id}/regression_test.py").text
        assert client.get("/api/runs").json()[0]["id"] == run_id


@pytest.mark.integration
def test_acceptance_updates_summary_audit_and_downloads_with_escaped_reason(captured_selector: dict, tmp_path: Path) -> None:
    app = create_app(tmp_path)
    report = deepcopy(captured_selector)
    app.state.engine.store.save(report, "captured_fixture_loaded")
    original = next(item for item in report["findings"] if item["type"] == "observed_change" and item["rule"] == "columns")
    reason = '<img src=x onerror="alert(1)"> Approved & reviewed'
    with TestClient(app) as client:
        response = client.post(f"/api/runs/{report['id']}/accept", json={"finding_id": original["id"], "reason": reason})
        assert response.status_code == 200, response.text
        accepted = response.json()
        updated = next(item for item in accepted["findings"] if item["id"] == original["id"])
        assert updated["accepted"] is True and updated["acceptance_reason"] == reason
        assert updated["before"] == original["before"] and updated["after"] == original["after"]
        assert updated["evidence"] == original["evidence"]
        assert accepted["summary"]["accepted"] == report["summary"]["accepted"] + 1
        assert accepted["summary"]["unaccepted_changes"] == report["summary"]["unaccepted_changes"] - 1
        audit = accepted["events"][-1]
        assert audit["kind"] == "finding_accepted" and audit["payload"]["reason"] == reason
        assert audit["payload"]["origin"] == "reviewer"
        json_report = client.get(f"/api/runs/{report['id']}/report.json").json()
        assert json_report["summary"] == accepted["summary"]
        assert json_report["events"][-1] == audit
        html_report = client.get(f"/api/runs/{report['id']}/report.html").text
        assert reason not in html_report and html.escape(reason) in html_report
        assert "<img src=x" not in html_report
        directory = tmp_path / "runs" / report["id"]
        assert json.loads((directory / "report.json").read_text())["summary"] == accepted["summary"]
        assert html.escape(reason) in (directory / "report.html").read_text()


def test_service_startup_marks_interrupted_runs_without_fabricating_outputs(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    queued = app.state.engine.create(RunRequest(case_id="numeric"))
    assert queued["status"] == "queued"
    with TestClient(app) as client:
        recovered = client.get(f"/api/runs/{queued['id']}").json()
        assert recovered["status"] == "failed"
        assert "stopped before this run completed" in recovered["error"]
        assert recovered["events"][-1]["kind"] == "interrupted"
        assert recovered["executions"] == {"before": [], "after": []}
        assert recovered["findings"] == []
        assert "Regression artifact unavailable" in client.get(f"/api/runs/{queued['id']}/regression_test.py").text
