"""Evaluation measures genuine outcomes without leaking labels or inflating scores."""

from __future__ import annotations

from copy import deepcopy

from featureshift.cases import get_case, load_cases
from featureshift.evaluation import (
    _source_audit,
    _test_baselines,
    classify_outcome,
    documentation_prediction,
    family_fold,
    summarize_cases,
)
from featureshift.evidence import retrieve


def test_change_family_folds_prevent_demo_and_historical_family_leakage() -> None:
    cases = [case for case in load_cases() if case.source.startswith("benchmarks/")]
    groups: dict[str, set[str]] = {}
    for case in cases:
        split = family_fold(case)
        groups.setdefault(split["group"], set()).add(split["fold"])
    assert all(len(folds) == 1 for folds in groups.values())
    assert family_fold(get_case("dtype-mask"))["fold"] == "development"
    assert family_fold(get_case("wrong-version")) == {**family_fold(get_case("dtype-mask")), "registered_split": get_case("wrong-version").split}
    assert family_fold(get_case("numeric-scale"))["group"] == family_fold(get_case("numeric-aggregate"))["group"]
    assert family_fold(get_case("historical-none"))["group"] == family_fold(get_case("historical-nan"))["group"]
    assert family_fold(get_case("retrospective-cutoff"))["group"] == family_fold(get_case("historical-none"))["group"]
    assert family_fold(get_case("copy-on-write"))["fold"] == "evaluation"


def test_static_risk_prediction_ignores_expected_labels_and_withholds_wrong_versions() -> None:
    case = get_case("dtype-mask")
    first = documentation_prediction(case)
    changed_label = case.model_copy(update={"expected": "equivalent"})
    second = documentation_prediction(changed_label)
    for result in (first, second):
        result.pop("duration_s")
    assert first == second
    assert first["risk_flag"] is True and first["runtime_consulted"] is False
    assert first["observed_change"] is False and first["defect_allegation"] is False
    assert documentation_prediction(get_case("wrong-version"))["risk_flag"] is False
    assert documentation_prediction(get_case("retrospective-cutoff"))["risk_flag"] is False


def test_environment_failure_and_uncertainty_take_precedence_over_observation() -> None:
    observed = {"type": "observed_change", "rule": "dtype:x", "accepted": False}
    report = {"status": "completed", "findings": [observed], "summary": {"equivalent": False}}
    assert classify_outcome(report) == "material_change"
    report["findings"].append({"type": "insufficient_evidence", "rule": "dtype:x"})
    assert classify_outcome(report) == "insufficient_evidence"
    report["findings"].append({"type": "probe_environment_error", "rule": "probe:execution"})
    assert classify_outcome(report) == "probe_error"
    report["findings"].append({"type": "probe_environment_error", "rule": "environment:install"})
    assert classify_outcome(report) == "environment_error"
    assert classify_outcome({"status": "completed", "findings": [], "summary": {"equivalent": True}}) == "equivalent"
    assert classify_outcome({"status": "partial", "findings": [], "summary": {"equivalent": None}}) == "insufficient_evidence"


def test_intentional_change_requires_all_observations_accepted_and_no_violation() -> None:
    report = {"status": "completed", "findings": [{"type": "observed_change", "rule": "dtype:x", "accepted": True}]}
    assert classify_outcome(report) == "intentional_change"
    report["findings"].append({"type": "observed_change", "rule": "nulls:x", "accepted": False})
    assert classify_outcome(report) == "material_change"
    report["findings"].pop()
    report["findings"].append({"type": "contract_violation", "rule": "contract:dtype:x"})
    assert classify_outcome(report) == "material_change"


def test_edgetest_style_is_honest_reuse_and_setup_error_is_not_semantic_detection() -> None:
    report = {"existing_tests": {
        "before": {"test_passed": True, "status": "ok", "duration_s": 0.2},
        "after": {"test_passed": False, "status": "error", "duration_s": 0.3},
    }}
    baselines = _test_baselines(report)
    assert baselines["existing_tests"]["change_flag"] is True
    assert baselines["edgetest_style"]["change_flag"] is True
    assert baselines["edgetest_style"]["actual_edgetest_package_executed"] is False
    assert baselines["edgetest_style"]["shares_execution_with"] == "existing_tests"
    assert baselines["existing_tests"]["defect_allegation"] is False
    unavailable = _test_baselines({"existing_tests": {}})
    assert unavailable["existing_tests"]["change_flag"] is False
    assert unavailable["existing_tests"]["available"] is False


def _metric_case(expected: str, flags: dict[str, bool], *, defect: bool = False) -> dict:
    methods = {method: {"change_flag": flags.get(method, False), "defect_allegation": defect if method == "full_system" else False}
               for method in ("existing_tests", "edgetest_style", "documentation_only", "full_system")}
    methods["documentation_only"]["risk_flag"] = flags.get("documentation_only", False)
    return {"expected": expected, "actual": expected, "label_match": True, "baselines": methods,
            "probes": [], "within_environment_repeatability": [],
            "source_audit": {"citations": [], "unsupported_expected_findings": []},
            "report_ready_duration_s": 1.0, "model_calls": 0, "model_cost_usd": 0.0}


def test_metrics_separate_risk_observation_and_false_defect_with_explicit_denominators() -> None:
    cases = [
        _metric_case("material_change", {"full_system": True, "documentation_only": True}),
        _metric_case("material_change", {}),
        _metric_case("intentional_change", {"full_system": True, "documentation_only": True}),
        _metric_case("equivalent", {}, defect=True),
        _metric_case("insufficient_evidence", {"full_system": True}),
    ]
    result = summarize_cases(cases)
    full = result["baselines"]["full_system"]
    assert full["material_change_alert_recall"] == {"numerator": 1, "denominator": 2, "rate": 0.5}
    assert full["false_defect_allegations"] == {"numerator": 1, "denominator": 2, "rate": 0.5}
    assert result["baselines"]["documentation_only"]["material_change_observation_recall"] is None
    assert result["human_review_latency_s"] is None
    assert result["correct_source_group_and_operation"]["rate"] is None
    assert summarize_cases([])["outcome_agreement"]["rate"] is None


def test_valid_exact_version_citation_can_still_be_wrong_operation() -> None:
    case = get_case("dtype-mask")
    valid = next(item for item in retrieve("dtype object check is_string_dtype", limit=10) if item["id"] == "pandas-3.0.0-strings:dtype-check")
    wrong_operation = retrieve("datetime unit resolution", limit=1)[0]
    report = {
        "source": {"code": 'def transform(df):\n    return df.loc[:, df.dtypes == "object"]\n'},
        "input": {"fixture": {"data": {"label": ["a", "b"]}}},
        "findings": [{"id": "a", "type": "expected_change", "rule": "columns", "probe_id": "baseline", "evidence": [valid]}],
    }
    good = _source_audit(case, report)
    assert good["valid"] and good["correct_citation_count"] == 1
    report["findings"][0]["evidence"] = [wrong_operation]
    bad = _source_audit(case, report)
    assert bad["citations"][0]["valid_exact_source"] is True
    assert bad["citations"][0]["operation_match"] is False
    assert bad["valid"] is False
    report["findings"][0]["evidence"] = [deepcopy(valid)]
    report["findings"][0]["evidence"][0]["passage"] = "A fabricated claim"
    assert _source_audit(case, report)["valid"] is False
