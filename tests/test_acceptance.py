"""End-to-end release gates using actual workers and the pinned offline corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from featureshift.cases import get_case, trusted_path
from featureshift.config import ENV_ROOT, upload_policy
from featureshift.engine import Engine, normalized_findings
from featureshift.evidence import evidence_supports
from featureshift.models import Contract, RunRequest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not all((ENV_ROOT / side / "bin" / "python").exists() for side in ("before", "after")), reason="Run make setup for the actual pandas pair"),
]


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    return Engine(state=tmp_path)


def findings(report: dict, kind: str, *, rule: str | None = None) -> list[dict]:
    return [finding for finding in report["findings"] if finding["type"] == kind and (rule is None or finding["rule"] == rule)]


def test_string_selector_loses_feature_with_executed_outputs_and_exact_evidence(engine: Engine) -> None:
    report = engine.run(RunRequest(case_id="selector"))
    assert report["status"] == "completed", report["findings"]
    assert all(result["status"] == "ok" for side in ("before", "after") for result in report["executions"][side])
    old, new = report["executions"]["before"][0], report["executions"]["after"][0]
    assert old["versions"]["pandas"] == "2.3.3" and new["versions"]["pandas"] == "3.0.0"
    assert [column["name"] for column in old["output"]["columns"]] == ["segment"]
    assert new["output"]["columns"] == []
    assert findings(report, "observed_change", rule="columns")
    expected = findings(report, "expected_change", rule="columns")
    assert expected and all(evidence_supports(item["evidence"]) for item in expected)
    assert all(any(item["source_version"] == "3.0.0" for item in finding["evidence"]) for finding in expected)
    assert findings(report, "contract_violation", rule="contract:columns")
    assert report["summary"]["equivalent"] is False
    assert report["environments"]["shared_dependencies_constant"] is True
    assert report["source"]["sha256"] == hashlib.sha256(report["source"]["code"].encode()).hexdigest()
    assert report["provider"]["model_calls"] == 0 and report["provider"]["live_ai"] is False
    directory = engine.store.state / "runs" / report["id"]
    assert json.loads((directory / "report.json").read_text())["id"] == report["id"]
    assert (directory / "report.html").is_file() and (directory / "regression_test.py").is_file()
    assert report["patches"] and all(not patch["applied"] for patch in report["patches"])


def test_unaffected_transformation_has_no_defect_or_observed_difference(engine: Engine) -> None:
    report = engine.run(RunRequest(case_id="numeric"))
    assert report["status"] == "completed", report["findings"]
    assert report["summary"]["equivalent"] is True
    assert report["summary"]["deterministic"] is True
    assert report["findings"] == []


def test_declared_intentional_dtype_change_keeps_outputs_and_audit(engine: Engine) -> None:
    report = engine.run(RunRequest(case_id="intentional-dtype"))
    observed = findings(report, "observed_change", rule="dtype:label")
    assert report["status"] == "completed" and observed, report["findings"]
    assert all(item["accepted"] is True and item["acceptance_origin"] == "declared_contract" for item in observed)
    assert all(item["before"] == "object" and item["after"] == "str" for item in observed)
    assert all(item["acceptance_reason"] == get_case("intentional-dtype").contract.rationale for item in observed)
    accepted_events = [event for event in report["events"] if event["kind"] == "finding_accepted"]
    assert {item["id"] for item in observed}.issubset({event["payload"]["finding_id"] for event in accepted_events})
    persisted = engine.store.get(report["id"])
    assert normalized_findings(persisted) == normalized_findings(report)
    assert persisted["summary"]["unaccepted_changes"] == 0


def test_null_sentinel_comparison_obeys_declared_equivalence(engine: Engine) -> None:
    strict = engine.run(RunRequest(case_id="null-sentinel"))
    assert findings(strict, "observed_change", rule="nulls:label")
    equivalent = engine.run(RunRequest(case_id="null-equivalent"))
    assert equivalent["status"] == "completed", equivalent["findings"]
    assert equivalent["configuration"]["contract"]["nulls"] == "equivalent"
    assert equivalent["findings"] == []
    assert equivalent["summary"]["equivalent"] is True


def test_null_conversion_can_introduce_a_non_null_contract_violation(engine: Engine) -> None:
    report = engine.run(RunRequest(case_id="astype-null"))
    assert report["status"] == "completed", report["findings"]
    assert findings(report, "observed_change", rule="nulls:value")
    assert findings(report, "contract_violation", rule="contract:non_null:value")
    checks = report["contract_checks"]["baseline"]
    assert not any(item["rule"] == "contract:non_null:value" for item in checks["before"])
    assert any(item["rule"] == "contract:non_null:value" for item in checks["after"])


def test_real_failed_install_is_an_environment_error_without_semantic_result(engine: Engine) -> None:
    report = engine.run(RunRequest(case_id="install-failure"))
    assert report["status"] == "partial"
    assert report["setup_failure"]["verified"] is True
    assert report["setup_failure"]["environment_unchanged"] is True
    assert report["setup_failure"]["exit_code"] == 1
    assert report["executions"] == {"before": [], "after": []}
    assert report["summary"]["equivalent"] is None
    assert findings(report, "probe_environment_error", rule="environment:install")
    assert not findings(report, "observed_change") and not findings(report, "contract_violation")


def test_stochastic_transformation_withholds_cross_version_attribution(engine: Engine) -> None:
    report = engine.run(RunRequest(case_id="stochastic"))
    assert report["status"] == "completed", report["findings"]
    assert findings(report, "insufficient_evidence", rule="determinism")
    assert report["summary"]["deterministic"] is False
    assert report["summary"]["equivalent"] is None
    assert not findings(report, "expected_change") and not findings(report, "observed_change")


@pytest.mark.parametrize("case_id", ["wrong-version", "retrospective-cutoff"])
def test_ineligible_evidence_cannot_support_a_definitive_change(engine: Engine, case_id: str) -> None:
    report = engine.run(RunRequest(case_id=case_id))
    assert report["status"] == "completed", report["findings"]
    assert report["evidence"] == []
    assert findings(report, "observed_change") and findings(report, "insufficient_evidence")
    assert not findings(report, "expected_change")
    assert all(not item["evidence"] for item in report["findings"])


def test_generated_probe_timeout_is_excluded_and_next_job_completes(engine: Engine) -> None:
    report = engine.run(RunRequest(case_id="probe-timeout"))
    assert report["status"] == "partial", report["findings"]
    probe = next(item for item in report["probes"] if item["id"] == "deadline-control")
    assert probe["syntax"]["valid"] is True
    assert all(item["status"] == "timeout" and item["exit_code"] < 0 for item in probe["validation"].values())
    assert probe["executions"] == {"before": [], "after": []}
    assert findings(report, "probe_environment_error", rule="probe:execution")
    assert not findings(report, "observed_change")
    next_run = engine.run(RunRequest(case_id="numeric"))
    assert next_run["status"] == "completed" and next_run["summary"]["equivalent"] is True


def test_arbitrary_upload_policy_and_unregistered_paths_are_disabled(engine: Engine) -> None:
    assert upload_policy()["uploads_enabled"] is False
    with pytest.raises(ValueError, match="repository-owned"):
        trusted_path("/tmp/customer-upload.py")
    with pytest.raises(KeyError):
        engine.run(RunRequest(case_id="unregistered-upload"))
    assert engine.store.list() == []


def test_deterministic_repeated_runs_have_stable_normalized_findings(engine: Engine) -> None:
    request = RunRequest(case_id="dtype-mask")
    first, second = engine.run(request), engine.run(request)
    assert first["id"] != second["id"]
    assert first["status"] == second["status"] == "completed"
    assert first["summary"]["deterministic"] is True and second["summary"]["deterministic"] is True
    assert normalized_findings(first) == normalized_findings(second)
    assert first["normalized_findings_sha256"] == second["normalized_findings_sha256"]
    assert [item["id"] for item in first["findings"]] == [item["id"] for item in second["findings"]]


def test_intentional_rule_requires_rationale_before_execution(engine: Engine) -> None:
    with pytest.raises(ValueError, match="rationale"):
        engine.run(RunRequest(case_id="intentional-dtype", contract=Contract(intentional=["dtype"])))
    assert engine.store.list() == []
