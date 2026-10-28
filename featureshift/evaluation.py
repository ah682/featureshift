"""Measured diagnostic replay evaluation, without simulated baseline results."""

from __future__ import annotations

import hashlib
import html
import json
import os
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from featureshift.cases import load_cases, trusted_path
from featureshift.compare import compare_frames
from featureshift.config import AFTER, BEFORE, ROOT
from featureshift.engine import Engine, normalized_findings
from featureshift.evidence import (
    CORPUS_DIR,
    corpus_status,
    evidence_supports,
    retrieve,
    validate_source,
)
from featureshift.models import Case, Contract, RunRequest
from featureshift.probes import operations

_DEVELOPMENT_GROUPS = {"string-selector", "string-inference", "numeric"}
_FAMILY_ALIASES = {
    "demo-string-selection": "string-selector", "evidence-controls": "string-selector",
    "demo-string-inference": "string-inference", "demo-numeric": "numeric",
    "numeric-scale": "numeric", "numeric-aggregate": "numeric",
    "historical-36904": "string-conversion", "temporal-evidence": "string-conversion",
    "historical-36451": "float-string-precision",
}
_SOURCE_SUFFIXES = {
    "string-selector": {"dtype-check"},
    "string-inference": {"inference", "dtype-check", "string-release", "null-sentinel"},
    "null-representation": {"null-sentinel", "inference"},
    "string-conversion": {"astype-str"},
    "copy-on-write": {"chained-assignment", "mutation", "readonly-array", "inplace", "cow"},
    "categorical-observed": {"groupby-observed"},
    "datetime-resolution": {"datetime-resolution"},
    "select-dtypes-compat": {"select-dtypes"},
}
_SOURCE_OPERATIONS = {
    "dtype-check": {"dtype-check"}, "inference": {"string-inference", "string-cast"},
    "string-release": {"string-inference"}, "null-sentinel": {"string-inference", "string-cast"},
    "astype-str": {"string-cast"}, "chained-assignment": {"copy-on-write"},
    "mutation": {"copy-on-write"}, "readonly-array": {"copy-on-write"},
    "inplace": {"copy-on-write"}, "cow": {"copy-on-write"},
    "groupby-observed": {"groupby"}, "datetime-resolution": {"datetime"},
    "select-dtypes": {"select-dtypes"},
}


def family_fold(case: Case) -> dict[str, str]:
    """Keep every repository/change family together, including temporal controls."""
    family = _FAMILY_ALIASES.get(case.family, case.family)
    return {"group": f"pandas/{family}", "change_family": family,
            "fold": "development" if family in _DEVELOPMENT_GROUPS else "evaluation",
            "registered_split": case.split}


def documentation_prediction(case: Case) -> dict[str, Any]:
    """Static risk prediction: this function accepts no runtime output or label."""
    started = time.monotonic()
    code = trusted_path(case.source).read_text(encoding="utf-8")
    fixture = json.loads(trusted_path(case.fixture).read_text(encoding="utf-8"))
    signals = operations(code, fixture)
    queries = [case.evidence_query] if case.evidence_query else [signal["query"] for signal in signals]
    versions = case.evidence_versions or (BEFORE, AFTER)
    sources = {}
    for query in queries:
        for item in retrieve(query, *versions, limit=8, cutoff=case.cutoff):
            sources[item["id"]] = item
    evidence = list(sources.values())
    supported = evidence_supports(evidence, *versions, cutoff=case.cutoff)
    return {
        "method": "documentation_only", "risk_flag": bool(signals and supported),
        "risk_definition": "A statically recognized operation has matching-version migration evidence; input-specific behavior is unverified.",
        "runtime_consulted": False, "observed_change": False, "definitive_observation": False,
        "defect_allegation": False, "operations": signals,
        "evidence_ids": sorted(sources), "exact_version_support": supported,
        "duration_s": round(time.monotonic() - started, 6),
        "model_calls": 0, "model_cost_usd": 0.0,
    }


def classify_outcome(report: dict[str, Any]) -> str:
    """Classification precedence is fixed before consulting benchmark labels."""
    findings = report.get("findings", [])
    errors = [finding for finding in findings if finding["type"] == "probe_environment_error"]
    if any(finding["rule"].startswith("environment:") for finding in errors):
        return "environment_error"
    if errors or report.get("status") == "failed":
        return "probe_error"
    if any(finding["type"] == "insufficient_evidence" for finding in findings):
        return "insufficient_evidence"
    observed = [finding for finding in findings if finding["type"] == "observed_change"]
    if observed:
        if all(finding.get("accepted", False) for finding in observed) and not any(
            finding["type"] == "contract_violation" for finding in findings
        ):
            return "intentional_change"
        return "material_change"
    if report.get("summary", {}).get("equivalent") is True:
        return "equivalent"
    return "insufficient_evidence"


def _test_baselines(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = report.get("existing_tests", {})
    before, after = results.get("before", {}), results.get("after", {})
    available = all(result.get("test_passed") in (True, False) for result in (before, after))
    alert = bool(available and before["test_passed"] and not after["test_passed"])
    measured = {"available": available, "change_flag": alert,
                "before_passed": before.get("test_passed"), "after_passed": after.get("test_passed"),
                "before_status": before.get("status", "not_executed"), "after_status": after.get("status", "not_executed"),
                "defect_allegation": False, "signal_kind": "new_existing_test_failure",
                "duration_s": round(sum(result.get("duration_s", 0.0) for result in (before, after)), 6)}
    return {
        "existing_tests": {**measured, "method": "existing_tests_in_both_environments"},
        "edgetest_style": {**measured, "method": "pinned_dependency_test_replay",
                           "actual_edgetest_package_executed": False, "shares_execution_with": "existing_tests",
                           "description": "Edgetest-style upgrade-and-test baseline using the exact same executed before/after tests and fixed dependency pair; not a run of the edgetest package."},
    }


def _source_audit(case: Case, report: dict[str, Any]) -> dict[str, Any]:
    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    sources = {source["id"]: source for source in manifest["sources"]}
    passages = {passage["id"]: passage for passage in json.loads((CORPUS_DIR / "passages.json").read_text(encoding="utf-8"))}
    code_signals = {signal["id"] for signal in operations(report["source"]["code"], report["input"]["fixture"])}
    allowed = _SOURCE_SUFFIXES.get(family_fold(case)["change_family"], set())
    citations = []
    unsupported_expected_findings = []
    for finding in report["findings"]:
        attached = finding.get("evidence", [])
        if finding["type"] == "expected_change" and not evidence_supports(attached, BEFORE, AFTER, cutoff=case.cutoff):
            unsupported_expected_findings.append(finding["id"])
        for citation in attached:
            valid = False
            source = sources.get(citation.get("source_id", ""))
            passage = passages.get(citation.get("id", ""))
            if source and passage and passage["source_id"] == source["id"] and validate_source(citation)["valid"]:
                raw = (CORPUS_DIR / source["snapshot_path"]).read_bytes().decode("utf-8")
                valid = all(citation.get(key) == passage[key] for key in ("start", "end", "passage_hash", "applies_to"))
                valid = valid and citation.get("passage") == raw[passage["start"]:passage["end"]]
                valid = valid and citation.get("source_version") in (BEFORE, AFTER) and not citation.get("conflict")
                if case.cutoff:
                    cutoff = datetime.fromisoformat(case.cutoff.replace("Z", "+00:00"))
                    if cutoff.tzinfo is None:
                        cutoff = cutoff.replace(tzinfo=timezone.utc)
                    if len(case.cutoff) == 10:
                        cutoff = cutoff.replace(hour=23, minute=59, second=59, microsecond=999999)
                    valid = valid and datetime.fromisoformat(source["published_at"].replace("Z", "+00:00")) <= cutoff
            suffix = citation.get("id", "").rsplit(":", 1)[-1]
            group_match = suffix in allowed
            operation_match = bool(_SOURCE_OPERATIONS.get(suffix, set()) & code_signals)
            citations.append({"finding_id": finding["id"], "finding_type": finding["type"],
                              "rule": finding["rule"], "probe_id": finding["probe_id"],
                              "evidence_id": citation.get("id"), "source_version": citation.get("source_version"),
                              "valid_exact_source": bool(valid), "source_group_match": group_match,
                              "operation_match": operation_match,
                              "correct": bool(valid and group_match and operation_match)})
    return {"citations": citations, "citation_count": len(citations),
            "correct_citation_count": sum(citation["correct"] for citation in citations),
            "unsupported_expected_findings": unsupported_expected_findings,
            "valid": all(citation["correct"] for citation in citations) and not unsupported_expected_findings,
            "matching_policy": "Independent reviewed change-family and AST-operation allowlists; hash/offset/version revalidation. Not a natural-language entailment model."}


def _within_environment_repeatability(report: dict[str, Any]) -> list[dict[str, Any]]:
    contract = Contract.model_validate(report["configuration"]["contract"])
    contexts = [("baseline", report["executions"])] + [(probe["id"], probe["executions"]) for probe in report["probes"]]
    result = []
    for context, executions in contexts:
        for side in ("before", "after"):
            runs = executions.get(side, [])
            testable = len(runs) >= 2 and all(run["status"] == "ok" for run in runs)
            stable = not any(compare_frames(runs[0]["output"], run["output"], contract) for run in runs[1:]) if testable else None
            result.append({"context": context, "environment": side, "repetitions": len(runs),
                           "testable": testable, "equivalent": stable})
    return result


def _fraction(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator,
            "rate": round(numerator / denominator, 6) if denominator else None}


def summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute metrics with explicit denominators; unknown outcomes stay unknown."""
    positives = [case for case in cases if case["expected"] == "material_change"]
    negatives = [case for case in cases if case["expected"] in {"equivalent", "intentional_change"}]
    equivalent_cases = [case for case in cases if case["expected"] == "equivalent"]
    intentional_cases = [case for case in cases if case["expected"] == "intentional_change"]
    baselines = {}
    for method in ("existing_tests", "edgetest_style", "documentation_only", "full_system"):
        field = "risk_flag" if method == "documentation_only" else "change_flag"
        detected = sum(bool(case["baselines"][method].get(field)) for case in positives)
        alerts = sum(bool(case["baselines"][method].get(field)) for case in negatives)
        false_defects = sum(bool(case["baselines"][method].get("defect_allegation")) for case in negatives)
        baselines[method] = {
            "material_change_alert_recall": _fraction(detected, len(positives)),
            "material_change_observation_recall": _fraction(detected, len(positives)) if method == "full_system" else None,
            "nonmaterial_case_alert_rate": _fraction(alerts, len(negatives)),
            "equivalent_case_alert_rate": _fraction(sum(bool(case["baselines"][method].get(field)) for case in equivalent_cases), len(equivalent_cases)),
            "intentional_change_visibility": _fraction(sum(bool(case["baselines"][method].get(field)) for case in intentional_cases), len(intentional_cases)),
            "false_defect_allegations": _fraction(false_defects, len(negatives)),
            "alert_semantics": "documented operation risk; no runtime observation" if method == "documentation_only" else "executed output difference" if method == "full_system" else "existing test newly fails after upgrade",
        }
    proposed = [probe for case in cases for probe in case["probes"]]
    ordinary_probes = [probe for case in cases if case["expected"] != "probe_error" for probe in case["probes"]]
    repetitions = [item for case in cases for item in case["within_environment_repeatability"] if item["testable"]]
    citations = [citation for case in cases for citation in case["source_audit"]["citations"]]
    return {
        "case_count": len(cases), "label_counts": dict(Counter(case["expected"] for case in cases)),
        "outcome_counts": dict(Counter(case["actual"] for case in cases)),
        "outcome_agreement": _fraction(sum(case["label_match"] for case in cases), len(cases)),
        "baselines": baselines,
        "probe_execution_success_all": _fraction(sum(probe.get("execution_succeeded", probe["status"] in {"completed", "inconclusive"}) for probe in proposed), len(proposed)),
        "probe_execution_success_excluding_declared_failure_controls": _fraction(sum(probe.get("execution_succeeded", probe["status"] in {"completed", "inconclusive"}) for probe in ordinary_probes), len(ordinary_probes)),
        "probe_deterministic_comparison_completion": _fraction(sum(probe["status"] == "completed" for probe in proposed), len(proposed)),
        "additional_material_alerts_over_existing_tests": sum(bool(case["baselines"]["full_system"].get("change_flag")) and not case["baselines"]["existing_tests"].get("change_flag") for case in positives),
        "material_cases_detected_only_by_generated_probes": [case.get("id") for case in positives if case["baselines"]["full_system"].get("probe_only_change")],
        "exact_source_version_validity": _fraction(sum(citation["valid_exact_source"] for citation in citations), len(citations)),
        "correct_source_group_and_operation": _fraction(sum(citation["correct"] for citation in citations), len(citations)),
        "expected_findings_without_verified_support": sum(len(case["source_audit"]["unsupported_expected_findings"]) for case in cases),
        "within_environment_repeatability": _fraction(sum(bool(item["equivalent"]) for item in repetitions), len(repetitions)),
        "case_report_ready_duration_s": {"median": round(statistics.median(case["report_ready_duration_s"] for case in cases), 4) if cases else None,
                                         "total": round(sum(case["report_ready_duration_s"] for case in cases), 4)},
        "human_review_latency_s": None, "human_review_sessions": 0,
        "model_calls": sum(case["model_calls"] for case in cases),
        "model_cost_usd": sum(case["model_cost_usd"] for case in cases),
    }


def _provenance(case: Case) -> dict[str, Any]:
    provenance = dict(case.provenance)
    historical = provenance.get("kind") == "adapted_historical_regression"
    provenance.update(synthetic=not historical, historical_replay=historical,
                      original_environment_reproduced=False,
                      transformation_steps=provenance.get("notes", "Repository-owned constructed stateless transformation."))
    if historical:
        original = json.loads((CORPUS_DIR / "historical.json").read_text(encoding="utf-8"))["reproductions"]
        match = next((item for item in original if item["issue_url"] == provenance.get("issue_url")), None)
        if match:
            provenance.update(licensed_code_url=match["licensed_code_url"],
                              licensed_code_content_hash=match["licensed_code_content_hash"],
                              permission=match["permission"], upstream_adaptation=match["transformation_steps"],
                              source_fetched_at=match["fetched_at"])
    return provenance


def _pretty_rate(metric: dict[str, Any]) -> str:
    if metric["rate"] is None:
        return "not measured (0 eligible)"
    return f"{metric['numerator']}/{metric['denominator']} ({100 * metric['rate']:.1f}%)"


def _write_reports(result: dict[str, Any], output: Path) -> None:
    metrics = result["metrics"]
    markdown = ["# FeatureShift diagnostic replay evaluation", "",
                "Executed local benchmark cases; this is not independent heldout or customer validation.", "",
                f"Generated: {result['finished_at']}. Exact pair: pandas {BEFORE} → {AFTER}.", "",
                f"Outcome agreement: **{_pretty_rate(metrics['outcome_agreement'])}**. "
                f"Report-ready duration: {result['duration_s']:.2f}s including static predictions, actual runs and repeat checks.", "",
                "| Baseline | Material-change alert recall | Nonmaterial alerts | False defect allegations |",
                "| --- | --- | --- | --- |"]
    baseline_rows = []
    for name, metric in metrics["baselines"].items():
        values = [name, _pretty_rate(metric["material_change_alert_recall"]), _pretty_rate(metric["nonmaterial_case_alert_rate"]), _pretty_rate(metric["false_defect_allegations"])]
        markdown.append("| " + " | ".join(values) + " |")
        baseline_rows.append("<tr>" + "".join(f"<td>{html.escape(value)}</td>" for value in values) + "</tr>")
    markdown += ["", "Documentation-only predicts operation risk, not observed changes or defects. Existing tests and the edgetest-style baseline share actual executions; the edgetest package was not run.", "",
                 f"Probe execution success including failure controls: {_pretty_rate(metrics['probe_execution_success_all'])}.",
                 f"Probe execution success excluding declared failure controls: {_pretty_rate(metrics['probe_execution_success_excluding_declared_failure_controls'])}.",
                 f"Deterministic probe comparisons completed: {_pretty_rate(metrics['probe_deterministic_comparison_completion'])}.",
                 f"Additional material alerts over existing tests: {metrics['additional_material_alerts_over_existing_tests']}; material cases detected only by generated probes: {len(metrics['material_cases_detected_only_by_generated_probes'])}.",
                 f"Exact source/version validity: {_pretty_rate(metrics['exact_source_version_validity'])}.",
                 f"Source group and operation match: {_pretty_rate(metrics['correct_source_group_and_operation'])}.",
                 f"Within-environment repeatability: {_pretty_rate(metrics['within_environment_repeatability'])}; the stochastic negative control is included.",
                 f"Across-run normalized repeatability: {_pretty_rate(result['across_run_repeatability']['summary'])}.",
                 f"Model calls: {metrics['model_calls']}; measured model cost: ${metrics['model_cost_usd']:.2f}. Human review latency: not measured. Coding-assistant comparison: not performed.", "",
                 "## Cases", "", "| Case | Fold / family | Expected | Actual | Source audit |", "| --- | --- | --- | --- | --- |"]
    case_rows = []
    for case in result["cases"]:
        relative = os.path.relpath(case["run_artifacts"]["report_html"], output)
        values = [case["id"], case["fold"] + " / " + case["group"], case["expected"], case["actual"], "pass" if case["source_audit"]["valid"] else "FAIL"]
        markdown.append("| " + " | ".join(values) + " |")
        case_rows.append(f"<tr class='{'match' if case['label_match'] else 'mismatch'}'><th scope='row'><a href='{html.escape(relative, quote=True)}'>{html.escape(case['id'])}</a></th>" + "".join(f"<td>{html.escape(value)}</td>" for value in values[1:]) + "</tr>")
    markdown += ["", "## Unresolved checks", ""]
    markdown.extend([f"- {item}" for item in result["failures"]] or ["No benchmark label, citation, or selected across-run repeatability mismatches in this measured run."])
    markdown += ["", "The evaluation fold is grouped by change family, but cases and rules were authored together. Report family-level results; do not interpret the aggregate as generalization performance.", ""]
    rendered = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FeatureShift evaluation</title><style>
body{{font:16px/1.6 system-ui,sans-serif;margin:0;color:#172d3e;background:#f3f6f7}}main{{max-width:1180px;margin:auto;padding:32px 24px}}h1{{font-size:2rem;line-height:1.2}}p{{max-width:90ch}}.notice{{padding:16px 20px;border-left:4px solid #577f7d;background:white}}.table{{overflow:auto;background:white;border:1px solid #d1dbdf;border-radius:8px}}table{{border-collapse:collapse;width:100%;font-size:.9rem}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dce3e7;vertical-align:top}}thead{{background:#e7efef}}a{{color:#075b77}}.mismatch{{background:#fff1e5}}code{{font-family:ui-monospace,monospace}}:focus-visible{{outline:3px solid #de9400;outline-offset:3px}}@media(max-width:600px){{main{{padding:20px 12px}}h1{{font-size:1.6rem}}}}</style></head><body><main>
<p><strong>FEATURESHIFT / MEASURED EVALUATION</strong></p><h1>Diagnostic replay results</h1>
<p class="notice">{metrics['case_count']} actual benchmark runs plus {result['across_run_repeatability']['summary']['denominator']} deterministic reruns. This suite is developed with the tool; it is not independent heldout or customer validation.</p>
<p>pandas {BEFORE} → {AFTER} · {html.escape(result['finished_at'])} · total report-ready duration {result['duration_s']:.2f}s</p>
<p><strong>Outcome agreement: {_pretty_rate(metrics['outcome_agreement'])}</strong> · <a href="evaluation.json">Download measured JSON</a> · <a href="report.md">Read text report</a></p>
<h2>Baselines</h2><div class="table"><table><thead><tr><th scope="col">Method</th><th scope="col">Material-change alert recall</th><th scope="col">Nonmaterial alerts</th><th scope="col">False defect allegations</th></tr></thead><tbody>{''.join(baseline_rows)}</tbody></table></div>
<p>Documentation-only predicts operation risk, without observing outputs. Existing tests and the edgetest-style baseline share actual execution records; the edgetest package was not run.</p>
<h2>Execution and source checks</h2><ul><li>Probe execution success, including failure controls: {_pretty_rate(metrics['probe_execution_success_all'])}</li><li>Deterministic probe comparisons completed: {_pretty_rate(metrics['probe_deterministic_comparison_completion'])}</li><li>Exact source/version validity: {_pretty_rate(metrics['exact_source_version_validity'])}</li><li>Correct source group and operation: {_pretty_rate(metrics['correct_source_group_and_operation'])}</li><li>Within-environment repetition: {_pretty_rate(metrics['within_environment_repeatability'])}; stochastic control included</li><li>Across-run normalized findings: {_pretty_rate(result['across_run_repeatability']['summary'])}</li><li>{metrics['model_calls']} model calls; ${metrics['model_cost_usd']:.2f} model cost</li></ul>
<p>Additional material alerts over existing tests: {metrics['additional_material_alerts_over_existing_tests']}. Material cases detected only by generated probes: {len(metrics['material_cases_detected_only_by_generated_probes'])}. Gains also include ordinary fixture output comparison; this result alone does not establish the incremental value of generated probes.</p>
<p>Human review latency was not measured. No coding-assistant comparison was performed. Report-ready duration measures local automation only.</p>
<h2>Case traces</h2><div class="table"><table><thead><tr><th scope="col">Case</th><th scope="col">Fold / family</th><th scope="col">Expected</th><th scope="col">Actual</th><th scope="col">Source audit</th></tr></thead><tbody>{''.join(case_rows)}</tbody></table></div>
<h2>Unresolved checks</h2><ul>{''.join('<li>' + html.escape(failure) + '</li>' for failure in result['failures']) or '<li>No label, source, or selected repeatability mismatches in this run.</li>'}</ul>
<p>All members of a repository/change family stay in one fold. Discovery families overlapping the demonstration are development cases. The remaining evaluation fold is still a diagnostic replay suite, not an independent generalization test.</p></main></body></html>"""
    (output / "report.md").write_text("\n".join(markdown), encoding="utf-8")
    (output / "report.html").write_text(rendered, encoding="utf-8")
    (output / "evaluation.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def evaluate(state: Path, output: Path) -> dict[str, Any]:
    """Run every benchmark, persist real traces, and write JSON/HTML/Markdown."""
    started = time.monotonic()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    state = Path(state).resolve()
    engine = Engine(state)
    cases = [case for case in load_cases() if case.source.startswith("benchmarks/")]
    implementation_hashes = {name: hashlib.sha256((ROOT / "featureshift" / name).read_bytes()).hexdigest()
                             for name in ("engine.py", "probes.py", "compare.py", "runner.py", "evidence.py", "evaluation.py")}
    # Freeze every static risk prediction before observing any runtime result.
    predictions = {case.id: documentation_prediction(case) for case in cases}
    results, reports = [], {}
    for index, case in enumerate(cases, 1):
        began = time.monotonic()
        report = engine.run(RunRequest(case_id=case.id, repeats=2, timeout_s=8))
        wall_s = round(time.monotonic() - began, 4)
        reports[case.id] = report
        findings = report["findings"]
        baselines = _test_baselines(report)
        baselines["documentation_only"] = predictions[case.id]
        baselines["full_system"] = {
            "method": "evidence_plus_real_execution_and_probes",
            "change_flag": any(finding["type"] == "observed_change" for finding in findings),
            "defect_allegation": any(finding["type"] == "contract_violation" and not finding.get("accepted") for finding in findings),
            "accepted_observed_changes": sum(finding["type"] == "observed_change" and bool(finding.get("accepted")) for finding in findings),
            "observed_change": any(finding["type"] == "observed_change" for finding in findings),
            "definitive_expected_attribution": any(finding["type"] == "expected_change" for finding in findings),
            "baseline_observed_change": any(finding["type"] == "observed_change" and finding["probe_id"] == "baseline" for finding in findings),
            "probe_only_change": any(finding["type"] == "observed_change" and finding["probe_id"] != "baseline" for finding in findings) and not any(finding["type"] == "observed_change" and finding["probe_id"] == "baseline" for finding in findings),
        }
        actual = classify_outcome(report)
        result = {
            "id": case.id, "title": case.title, "expected": case.expected, "actual": actual,
            "label_match": actual == case.expected, "family": case.family, **family_fold(case),
            "provenance": _provenance(case), "run_id": report["id"], "run_status": report["status"],
            "source_sha256": report["source"]["sha256"], "input_sha256": report["input"]["sha256"],
            "contract": report["configuration"]["contract"], "cutoff": case.cutoff,
            "evidence_versions": list(case.evidence_versions or (BEFORE, AFTER)),
            "baselines": baselines, "summary": report["summary"], "source_audit": _source_audit(case, report),
            "within_environment_repeatability": _within_environment_repeatability(report),
            "probes": [{"id": probe["id"], "status": probe["status"], "syntax_valid": probe["syntax"]["valid"],
                        "validation_status": {side: record["status"] for side, record in probe["validation"].items()},
                        "execution_succeeded": probe["status"] in {"completed", "inconclusive"} and all(record["status"] == "ok" for side in ("before", "after") for record in probe["executions"][side])}
                       for probe in report["probes"]],
            "report_ready_duration_s": wall_s, "engine_duration_s": report["duration_s"],
            "model_calls": report["provider"]["model_calls"], "model_cost_usd": report["provider"]["cost_usd"],
            "normalized_findings_sha256": report["normalized_findings_sha256"],
            "run_artifacts": {"report_json": str(state / "runs" / report["id"] / "report.json"),
                              "report_html": str(state / "runs" / report["id"] / "report.html")},
        }
        results.append(result)
        # Durable progress is useful when the long-running evaluation is interrupted.
        (output / "progress.json").write_text(json.dumps({"completed": index, "total": len(cases), "last_case": case.id, "results": results}, indent=2) + "\n", encoding="utf-8")
        print(f"[{index}/{len(cases)}] {case.id}: expected={case.expected} actual={actual} source_audit={'pass' if result['source_audit']['valid'] else 'FAIL'}", flush=True)
    repeat_checks = []
    for case_id in ("dtype-mask", "numeric-scale", "intentional-dtype"):
        if case_id not in reports:
            continue
        second = engine.run(RunRequest(case_id=case_id, repeats=2, timeout_s=8))
        original = reports[case_id]
        equal = normalized_findings(original) == normalized_findings(second)
        repeat_checks.append({"case_id": case_id, "first_run_id": original["id"], "second_run_id": second["id"],
                              "equivalent": equal, "first_hash": original["normalized_findings_sha256"],
                              "second_hash": second["normalized_findings_sha256"],
                              "second_model_calls": second["provider"]["model_calls"], "second_model_cost_usd": second["provider"]["cost_usd"]})
        print(f"[repeat] {case_id}: normalized_findings_equal={equal}", flush=True)
    failures = [f"{case['id']}: expected {case['expected']}, observed {case['actual']}" for case in results if not case["label_match"]]
    failures += [f"{case['id']}: source/version or source-group/operation citation audit failed" for case in results if not case["source_audit"]["valid"]]
    failures += [f"{check['case_id']}: normalized findings changed on a fresh run" for check in repeat_checks if not check["equivalent"]]
    summary = summarize_cases(results)
    summary["model_calls"] += sum(check["second_model_calls"] for check in repeat_checks)
    summary["model_cost_usd"] += sum(check["second_model_cost_usd"] for check in repeat_checks)
    result = {
        "schema_version": 1, "kind": "measured_diagnostic_replay", "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": round(time.monotonic() - started, 4), "metrics": summary,
        "summary": {"cases": len(results), "outcome_agreement": summary["outcome_agreement"],
                    "material_change_recall": summary["baselines"]["full_system"]["material_change_alert_recall"],
                    "false_defect_allegations": summary["baselines"]["full_system"]["false_defect_allegations"],
                    "source_operation_correctness": summary["correct_source_group_and_operation"],
                    "model_calls": summary["model_calls"], "model_cost_usd": summary["model_cost_usd"],
                    "failures": failures, "acceptance_passed": not failures},
        "by_fold": {fold: summarize_cases([case for case in results if case["fold"] == fold]) for fold in ("development", "evaluation")},
        "by_family": {group: summarize_cases([case for case in results if case["group"] == group]) for group in sorted({case["group"] for case in results})},
        "cases": results, "failures": failures, "acceptance_passed": not failures,
        "across_run_repeatability": {"summary": _fraction(sum(check["equivalent"] for check in repeat_checks), len(repeat_checks)), "checks": repeat_checks},
        "environments": next(iter(reports.values()))["environments"] if reports else {},
        "corpus": corpus_status(),
        "benchmark_manifest_sha256": hashlib.sha256((ROOT / "benchmarks" / "cases.json").read_bytes()).hexdigest(),
        "implementation_sha256_at_start": implementation_hashes,
        "methodology": {
            "repetitions_per_environment": 2, "baseline_execution_reuse": "existing_tests and edgetest_style share identical actual execution records",
            "actual_edgetest_package_executed": False, "coding_assistant_comparison": {"performed": False, "results": None},
            "docs_only_predictions_frozen_before_execution": True,
            "material_change_denominator": "Cases labeled material_change; intentional changes and insufficient-evidence controls are reported separately.",
            "false_defect_definition": "Unaccepted declared-contract violation asserted on an equivalent or intentional-change case. A risk or test-failure alert is not itself a defect allegation.",
            "fold_policy": "Group by pandas change family; demo-overlapping string-selector, string-inference and numeric groups are development. All other families are evaluation; no family spans folds.",
            "heldout_independent": False, "suite_scope": "All benchmark cases are diagnostic replays authored alongside implementation, separately registered from demonstration examples.",
            "history": "Adapted BSD-licensed regressions replayed on the selected present-day pair; original issue environments are not recreated. Temporal cutoffs withhold later evidence.",
            "human_review_latency_measured": False, "commercial_validation": False,
        },
        "artifacts": {"json": str(output / "evaluation.json"), "html": str(output / "report.html"), "markdown": str(output / "report.md")},
    }
    _write_reports(result, output)
    return result
