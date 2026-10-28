"""Downloaded reports escape text, and regression artifacts run independently."""

from __future__ import annotations

import html
import subprocess
from pathlib import Path

import pytest

from featureshift.artifacts import html_report, regression_test
from featureshift.compare import compare_frames
from featureshift.config import ENV_ROOT
from featureshift.engine import Engine
from featureshift.evidence import evidence_supports
from featureshift.models import Contract, RunRequest


@pytest.fixture(scope="session")
def captured_selector(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """One real selector run, reused by artifact and API review tests."""
    if not all((ENV_ROOT / side / "bin" / "python").exists() for side in ("before", "after")):
        pytest.skip("Run make setup for the pinned pandas environments")
    report = Engine(state=tmp_path_factory.mktemp("captured-selector")).run(RunRequest(case_id="selector"))
    assert report["status"] == "completed", report["findings"]
    return report


@pytest.mark.integration
def test_standalone_regression_passes_before_and_detects_upgrade_after(captured_selector: dict, tmp_path: Path) -> None:
    artifact = regression_test(captured_selector)
    assert "from featureshift" not in artifact and "import featureshift" not in artifact
    script = tmp_path / "downloaded_regression_test.py"
    script.write_text(artifact, encoding="utf-8")
    results = {}
    for side in ("before", "after"):
        python = ENV_ROOT / side / "bin" / "python"
        results[side] = subprocess.run(
            [str(python), "-I", "-B", str(script)], cwd=tmp_path, capture_output=True,
            text=True, timeout=8, check=False,
            env={"PATH": f"{python.parent}:/usr/bin:/bin", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "LANG": "C.UTF-8"},
        )
    assert results["before"].returncode == 0, results["before"].stderr
    assert "matches the pre-upgrade baseline" in results["before"].stdout
    assert results["after"].returncode == 1
    assert "AssertionError" in results["after"].stderr and '"rule": "columns"' in results["after"].stderr
    assert "ModuleNotFoundError" not in results["after"].stderr


@pytest.mark.integration
@pytest.mark.skipif(not all((ENV_ROOT / side / "bin" / "python").exists() for side in ("before", "after")), reason="Run make setup for the pinned pandas environments")
def test_probe_only_change_is_documented_and_downloaded_regression_replays_boundary(tmp_path: Path) -> None:
    report = Engine(state=tmp_path / "state").run(RunRequest(case_id="probe-only-null"))
    assert report["status"] == "completed", report["findings"]
    assert report["summary"]["deterministic"] is True
    assert all(test["status"] == "ok" and test["test_passed"] for test in report["existing_tests"].values())
    contract = Contract.model_validate(report["configuration"]["contract"])
    before = report["executions"]["before"][0]["output"]
    after = report["executions"]["after"][0]["output"]
    assert compare_frames(before, after, contract) == []
    observed = [item for item in report["findings"] if item["type"] == "observed_change"]
    assert observed and all(item["probe_id"] == "null-boundary" for item in observed)
    assert all(item["rule"] == "values:missing_indicator" for item in observed)
    assert observed[0]["before"][0] == 0 and observed[0]["after"][0] == 1
    expected = [item for item in report["findings"] if item["type"] == "expected_change"]
    assert expected and all(item["probe_id"] == "null-boundary" and evidence_supports(item["evidence"]) for item in expected)
    assert any(evidence["source_version"] == "3.0.0" and evidence["id"].endswith(":astype-str") for item in expected for evidence in item["evidence"])
    probe = next(item for item in report["probes"] if item["id"] == "null-boundary")
    assert probe["status"] == "completed" and probe["syntax"]["valid"]
    assert all(result["status"] == "ok" for result in probe["validation"].values())
    artifact = regression_test(report)
    assert "Selected executed input: null-boundary." in artifact
    script = tmp_path / "boundary_regression_test.py"
    script.write_text(artifact, encoding="utf-8")
    results = {}
    for side in ("before", "after"):
        python = ENV_ROOT / side / "bin" / "python"
        results[side] = subprocess.run(
            [str(python), "-I", "-B", str(script)], cwd=tmp_path, capture_output=True,
            text=True, timeout=8, check=False,
            env={"PATH": f"{python.parent}:/usr/bin:/bin", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "LANG": "C.UTF-8"},
        )
    assert results["before"].returncode == 0, results["before"].stderr
    assert results["after"].returncode == 1
    assert "AssertionError" in results["after"].stderr and '"rule": "values:missing_indicator"' in results["after"].stderr
    assert "ModuleNotFoundError" not in results["after"].stderr


@pytest.mark.parametrize("report", [
    {"executions": {"before": []}, "summary": {"deterministic": False}},
    {"executions": {"before": [{"status": "error"}]}, "summary": {"deterministic": True}},
    {"executions": {"before": [{"status": "ok"}]}, "summary": {"deterministic": False}},
])
def test_unavailable_regression_artifact_cannot_silently_pass(report: dict) -> None:
    artifact = regression_test(report)
    with pytest.raises(SystemExit, match="deterministic successful baseline"):
        exec(compile(artifact, "<downloaded-regression>", "exec"), {})


def test_html_report_escapes_titles_values_review_reasons_and_source() -> None:
    unsafe = '<img src=x onerror="alert(1)"> & <script>bad()</script>'
    report = {
        "title": unsafe, "status": "completed", "summary": {"observed_differences": 1},
        "findings": [{"type": "observed_change", "accepted": True, "title": unsafe,
                      "description": unsafe, "impact": unsafe, "rule": "values:x", "probe_id": "baseline",
                      "before": unsafe, "after": unsafe, "evidence": [], "acceptance_reason": unsafe, "reproduce": unsafe}],
        "source": {"code": unsafe}, "events": [{"reason": unsafe}],
    }
    document = html_report(report)
    assert unsafe not in document
    assert "<script>bad()" not in document and "<img src=x" not in document
    assert html.escape(unsafe) in document
    assert "Accepted" in document
