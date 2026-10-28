"""Preflight orchestration: evidence, trusted execution, comparison and audit."""

import ast
import difflib
import hashlib
import json
import shlex
import time
import uuid
from pathlib import Path
from typing import Any

from featureshift.artifacts import write_artifacts
from featureshift.cases import get_case, trusted_path
from featureshift.compare import compare_frames, contract_violations
from featureshift.config import AFTER, BEFORE, ENV_ROOT, ROOT, STATE, upload_policy
from featureshift.evidence import corpus_status, evidence_supports, retrieve
from featureshift.models import Case, Contract, RunRequest
from featureshift.probes import RulesProbeProvider, operations, validate_syntax
from featureshift.runner import environment_manifest, run_worker, verify_install_failure
from featureshift.store import Store, now


def digest(value: object) -> str:
    data = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


def normalized_findings(report: dict) -> list[dict]:
    """Strip run IDs, paths, timings and audit decisions for repeatability."""
    return [{k: finding[k] for k in ("type", "rule", "before", "after", "probe_id")}
            | {"evidence": [e["id"] for e in finding["evidence"]]} for finding in report["findings"]]


def get_environments() -> dict:
    result: dict[str, Any] = {}
    for side, version in (("before", BEFORE), ("after", AFTER)):
        manifest = environment_manifest(ENV_ROOT / side / "bin" / "python")
        manifest["id"] = digest({"python": manifest["python"], "packages": manifest["packages"]})[:16]
        manifest["requirements_sha256"] = digest((ROOT / "requirements" / f"{side}.txt").read_bytes())
        if manifest["status"] == "ok" and manifest["packages"].get("pandas") != version:
            manifest.update(status="environment_error", error={"message": f"Expected pandas {version}; rerun make setup."})
        result[side] = manifest
    old, new = result["before"], result["after"]
    result["shared_dependencies_constant"] = (
        old["status"] == new["status"] == "ok" and old["python"] == new["python"] and
        {k: v for k, v in old["packages"].items() if k != "pandas"} ==
        {k: v for k, v in new["packages"].items() if k != "pandas"})
    return result


def _source_evidence(code: str, fixture: dict, case: Case) -> tuple[list[dict], list[dict]]:
    signals = operations(code, fixture)
    queries = [case.evidence_query] if case.evidence_query else [s["query"] for s in signals]
    versions = case.evidence_versions or (BEFORE, AFTER)
    evidence = {}
    for query in queries:
        for item in retrieve(query, before_version=versions[0], after_version=versions[1], limit=8, cutoff=case.cutoff):
            evidence[item["id"]] = item
    return signals, list(evidence.values())


def _support_for(change: dict, evidence: list[dict], signals: list[dict], cutoff: str | None) -> list[dict]:
    rule = change["rule"].split(":")[0]
    operations_found = {s["id"] for s in signals}
    suffixes = set()
    if rule == "columns" and "dtype-check" in operations_found:
        suffixes.add("dtype-check")
    if rule == "dtype":
        if "datetime" in operations_found and str(change["before"]).startswith("datetime64") and str(change["after"]).startswith("datetime64"):
            suffixes.add("datetime-resolution")
        elif "string-cast" in operations_found:
            suffixes.add("astype-str")
        elif change["before"] == "object" and change["after"] == "str":
            suffixes.add("inference")
    if rule == "nulls":
        if "copy-on-write" in operations_found:
            suffixes.add("chained-assignment")
        elif "string-cast" in operations_found:
            suffixes.add("astype-str")
        elif "datetime" not in operations_found:
            suffixes.add("null-sentinel")
    if rule == "values" and "string-cast" in operations_found:
        # A missingness indicator can change values while retaining its int dtype.
        # The source operation must expose that downstream consequence explicitly.
        if any(s["id"] == "missing-indicator" for s in signals):
            suffixes.add("astype-str")
    if "groupby" in operations_found and rule in ("row_count", "rows", "index", "index_names", "values", "categories"):
        suffixes.add("groupby-observed")
    if "copy-on-write" in operations_found and rule in ("values", "nulls"):
        suffixes.add("chained-assignment")
    selected = [e for e in evidence if e["id"].rsplit(":", 1)[-1] in suffixes and not e.get("conflict")]
    return selected if evidence_supports(selected, BEFORE, AFTER, cutoff=cutoff) else []


def _new_finding(report: dict, kind: str, change: dict, probe_id: str, evidence: list[dict], title: str | None = None) -> dict:
    titles = {
        "observed_change": "Executed output changed",
        "expected_change": "Change matches versioned migration evidence",
        "contract_violation": "Declared output contract violated",
        "probe_environment_error": "Execution could not complete",
        "insufficient_evidence": "Evidence is insufficient for a definitive attribution",
    }
    identity = {"type": kind, "rule": change["rule"], "probe_id": probe_id,
                "before": change.get("before"), "after": change.get("after")}
    finding = identity | {
        "id": digest(identity)[:16], "title": title or titles[kind],
        "description": change.get("description", ""), "evidence": evidence,
        "location": {"path": report["source"]["path"], "line": report["source"]["line"], "entrypoint": report["source"]["entrypoint"]},
        "affected_code": report["source"]["code"],
        "impact": "Review downstream feature schema, encoders and consumers before accepting the upgrade.",
        "reproduce": f".venv/bin/python -m featureshift run {report['case_id']} --repeats {report['configuration']['repeats']} --timeout {report['configuration']['timeout_s']} --contract-json {shlex.quote(json.dumps(report['configuration']['contract'], separators=(',', ':')))}",
        "accepted": False,
    }
    # Accepted changes remain observed changes and keep every evidence/output field.
    contract = Contract.model_validate(report["configuration"]["contract"])
    if kind in ("observed_change", "expected_change") and any(
        change["rule"] == allowed or change["rule"].startswith(allowed + ":") for allowed in contract.intentional
    ) and contract.rationale:
        finding.update(accepted=True, acceptance_reason=contract.rationale, acceptance_origin="declared_contract")
    report["findings"].append(finding)
    return finding


class Engine:
    def __init__(self, state: Path = STATE):
        if upload_policy()["requested_provider"] != "deterministic-rules":
            raise ValueError("Only FEATURESHIFT_PROVIDER=deterministic-rules is available. No live model adapter is configured in this release.")
        self.store = Store(state)
        self.provider = RulesProbeProvider()

    def create(self, request: RunRequest) -> dict:
        case = get_case(request.case_id)
        source, fixture = trusted_path(case.source), trusted_path(case.fixture)
        code, data = source.read_text(), json.loads(fixture.read_text())
        tree = ast.parse(code)
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == case.entrypoint]
        if not functions:
            raise ValueError("The registered entry point is missing.")
        contract = request.contract or case.contract
        if contract.intentional and not contract.rationale:
            raise ValueError("Intentional comparison rules require a rationale.")
        run_id = uuid.uuid4().hex[:16]
        directory = self.store.state / "runs" / run_id
        directory.mkdir(parents=True)
        (directory / "source.py").write_text(code)
        (directory / "input.json").write_bytes(fixture.read_bytes())
        report: dict[str, Any] = {
            "schema_version": 1, "id": run_id, "case_id": case.id, "title": case.title,
            "status": "queued", "created_at": now(), "mode": "trusted-fixtures",
            "provider": {"name": self.provider.name, "model_calls": 0, "cost_usd": 0.0, "live_ai": False},
            "configuration": {"before": BEFORE, "after": AFTER, "repeats": request.repeats,
                              "timeout_s": request.timeout_s, "contract": contract.model_dump(), "cutoff": case.cutoff},
            "source": {"path": case.source, "code": code, "sha256": digest(code.encode()), "entrypoint": case.entrypoint, "line": functions[0].lineno},
            "input": {"path": case.fixture, "sha256": digest(fixture.read_bytes()), "normalized_sha256": digest(data), "fixture": data},
            "provenance": case.provenance, "family": case.family, "environments": {},
            "evidence": [], "operations": [], "probes": [], "findings": [], "patches": [],
            "executions": {"before": [], "after": []}, "existing_tests": {}, "summary": {},
            "isolation": upload_policy(),
        }
        self.store.save(report, "queued", {"configuration": report["configuration"], "code_sha256": report["source"]["sha256"], "input_sha256": report["input"]["sha256"]})
        return report

    def run(self, request: RunRequest) -> dict:
        return self.execute(self.create(request)["id"])

    def execute(self, run_id: str) -> dict:
        report = self.store.get(run_id)
        if report["status"] != "queued":
            raise ValueError("This run has already started.")
        started = time.monotonic()
        report["status"] = "running"
        self.store.save(report, "running")
        try:
            self._execute(report)
        except Exception as exc:
            # Persist unexpected orchestration failures; do not fabricate results.
            _new_finding(report, "probe_environment_error", {"rule": "orchestration", "before": None, "after": type(exc).__name__, "description": str(exc)}, "baseline", [])
            report["status"] = "failed"
        report["duration_s"] = round(time.monotonic() - started, 4)
        report["finished_at"] = now()
        self._summarize(report)
        report["normalized_findings_sha256"] = digest(normalized_findings(report))
        self.store.save(report, report["status"], {"summary": report["summary"]})
        for finding in report["findings"]:
            if finding.get("acceptance_origin") == "declared_contract":
                self.store.save(report, "finding_accepted", {"finding_id": finding["id"], "reason": finding["acceptance_reason"], "origin": "declared_contract"})
        report = self.store.get(run_id)
        write_artifacts(report, self.store.state / "runs" / run_id)
        return report

    def _execute(self, report: dict) -> None:
        case = get_case(report["case_id"])
        config = report["configuration"]
        contract = Contract.model_validate(config["contract"])
        directory = self.store.state / "runs" / report["id"]
        source, fixture = directory / "source.py", directory / "input.json"
        report["environments"] = get_environments()
        report["corpus"] = corpus_status()
        report["operations"], report["evidence"] = _source_evidence(report["source"]["code"], report["input"]["fixture"], case)
        self.store.save(report, "environments_checked")
        if case.fault == "environment":
            check = verify_install_failure(ROOT)
            report["setup_failure"] = check
            if not check.get("verified") or not check.get("environment_unchanged"):
                raise RuntimeError("The install-failure control did not verify an isolated setup failure; inspect its log.")
            _new_finding(report, "probe_environment_error", {"rule": "environment:install", "before": "pinned dependency installation", "after": check["status"], "description": "Constructed negative case: a real offline install of an impossible pinned dependency failed. No transformation ran."}, "baseline", [], "Dependency installation failed")
            report["status"] = "partial"
            return
        if any(report["environments"][s]["status"] != "ok" for s in ("before", "after")):
            _new_finding(report, "probe_environment_error", {"rule": "environment:setup", "before": report["environments"]["before"]["status"], "after": report["environments"]["after"]["status"], "description": "The pinned environments are unavailable. Run make setup; this is not evidence of semantic regression."}, "baseline", [])
            report["status"] = "partial"
            return
        if not report["environments"]["shared_dependencies_constant"]:
            _new_finding(report, "insufficient_evidence", {"rule": "environment:confounding", "before": report["environments"]["before"]["packages"], "after": report["environments"]["after"]["packages"], "description": "Other dependencies or Python changed too; causal attribution to pandas is uncertain."}, "baseline", [])
        for side in ("before", "after"):
            python = Path(report["environments"][side]["executable"])
            report["existing_tests"][side] = run_worker(python, source, fixture, directory / "existing-tests" / side, case.entrypoint, config["timeout_s"], test_mode=True)
            for index in range(config["repeats"]):
                report["executions"][side].append(run_worker(python, source, fixture, directory / "baseline" / side / str(index), case.entrypoint, config["timeout_s"]))
            self.store.save(report, "baseline_completed", {"environment": side})
        deterministic = self._compare_runs(report, report["executions"], "baseline", contract)
        report["deterministic"] = deterministic
        for proposal in self.provider.propose(report["source"]["code"], report["input"]["fixture"], case.entrypoint, case.fault):
            probe_dir = directory / "probes" / proposal.id
            probe_dir.mkdir(parents=True, exist_ok=True)
            probe_path = probe_dir / "probe.py"
            probe_path.write_text(proposal.code)
            syntax = validate_syntax(proposal.code)
            probe: dict[str, Any] = {"id": proposal.id, "title": proposal.title, "reason": proposal.reason,
                     "code": proposal.code, "sha256": digest(proposal.code.encode()), "syntax": syntax,
                     "status": "validating", "validation": {}, "executions": {"before": [], "after": []},
                     "timeout_s": proposal.timeout_s or config["timeout_s"]}
            report["probes"].append(probe)
            if not syntax["valid"]:
                probe["status"] = "invalid"
                _new_finding(report, "probe_environment_error", {"rule": "probe:syntax", "before": None, "after": syntax["error"], "description": "Probe failed syntax validation and was not executed."}, proposal.id, [])
                continue
            for side in ("before", "after"):
                python = Path(report["environments"][side]["executable"])
                probe["validation"][side] = run_worker(python, probe_path, fixture, probe_dir / "validation" / side, "transform", probe["timeout_s"])
            if any(r["status"] != "ok" for r in probe["validation"].values()):
                probe["status"] = "error"
                _new_finding(report, "probe_environment_error", {"rule": "probe:execution", "before": probe["validation"]["before"]["status"], "after": probe["validation"]["after"]["status"], "description": "Probe could not validate in both environments. Its output is excluded from semantic comparisons."}, proposal.id, [])
                continue
            probe["status"] = "validated"
            for side in ("before", "after"):
                python = Path(report["environments"][side]["executable"])
                for index in range(config["repeats"]):
                    probe["executions"][side].append(run_worker(python, probe_path, fixture, probe_dir / "comparison" / side / str(index), "transform", probe["timeout_s"]))
            stable = self._compare_runs(report, probe["executions"], proposal.id, contract)
            report["deterministic"] = report["deterministic"] and stable
            probe["status"] = "completed" if stable else "inconclusive"
            self.store.save(report, "probe_completed", {"probe_id": proposal.id, "status": probe["status"]})
        self._patch(report, fixture, directory)
        report["status"] = "partial" if any(f["type"] == "probe_environment_error" for f in report["findings"]) else "completed"

    def _compare_runs(self, report: dict, executions: dict, probe_id: str, contract: Contract) -> bool:
        flat = executions["before"] + executions["after"]
        if any(r["status"] != "ok" for r in flat):
            _new_finding(report, "probe_environment_error", {"rule": "execution", "before": [r["status"] for r in executions["before"]], "after": [r["status"] for r in executions["after"]], "description": "The transformation did not return a valid DataFrame in every repetition. Inspect stderr and exit status; no output comparison was made."}, probe_id, [])
            return False
        for side in ("before", "after"):
            first = executions[side][0]["output"]
            if any(compare_frames(first, r["output"], contract) for r in executions[side][1:]):
                _new_finding(report, "insufficient_evidence", {"rule": "determinism", "before": side, "after": "different repeated outputs", "description": "Repeated execution in the same environment produced different output. Cross-version attribution is withheld."}, probe_id, [], "Transformation failed the determinism check")
                return False
        before, after = executions["before"][0]["output"], executions["after"][0]["output"]
        changes = compare_frames(before, after, contract)
        for change in changes:
            support = _support_for(change, report["evidence"], report["operations"], report["configuration"]["cutoff"])
            if not report["environments"]["shared_dependencies_constant"]:
                support = []
            _new_finding(report, "observed_change", change, probe_id, support)
            if support:
                _new_finding(report, "expected_change", change, probe_id, support)
            else:
                _new_finding(report, "insufficient_evidence", {**change, "description": "The executed difference is real, but no non-conflicting evidence for this exact version pair and comparison rule supports a definitive cause."}, probe_id, [])
        old_violations = {v["rule"] for v in contract_violations(before, contract)}
        for violation in contract_violations(after, contract):
            if violation["rule"] not in old_violations:
                _new_finding(report, "contract_violation", violation, probe_id, [], "New output violates the declared contract")
        report.setdefault("contract_checks", {})[probe_id] = {"before": contract_violations(before, contract), "after": contract_violations(after, contract)}
        return True

    def _patch(self, report: dict, fixture: Path, directory: Path) -> None:
        code = report["source"]["code"]
        old = 'df.loc[:, df.dtypes == "object"]'
        if old not in code or not any(f["type"] == "expected_change" and f["rule"] == "columns" for f in report["findings"]):
            return
        new_code = code.replace(old, 'df.select_dtypes(include=["object", "string"])')
        path = directory / "suggested_patch.py"
        path.write_text(new_code)
        results = {side: run_worker(Path(report["environments"][side]["executable"]), path, fixture,
                                    directory / "patch-check" / side, report["source"]["entrypoint"], report["configuration"]["timeout_s"]) for side in ("before", "after")}
        contract = Contract.model_validate(report["configuration"]["contract"])
        checks = {}
        baseline = report["executions"]["before"][0]
        if baseline["status"] == "ok":
            for side, record in results.items():
                checks[side] = compare_frames(baseline["output"], record["output"], contract) if record["status"] == "ok" else [{"rule": "execution", "description": "Patch failed"}]
        report["patches"].append({"title": "Select both object and string features", "applied": False,
                                  "diff": "".join(difflib.unified_diff(code.splitlines(True), new_code.splitlines(True), fromfile=report["source"]["path"], tofile=report["source"]["path"])),
                                  "justification": "The compatible selector preserves string feature membership. Dtype differences may remain and need a separate contract decision.",
                                  "validation": results, "remaining_differences": checks, "fully_equivalent": bool(checks) and not any(checks.values())})

    @staticmethod
    def _summarize(report: dict) -> None:
        findings = report["findings"]
        def count(kind: str) -> int:
            return sum(f["type"] == kind for f in findings)
        errors = count("probe_environment_error")
        uncertain = count("insufficient_evidence")
        observed = count("observed_change")
        report["summary"] = {"observed_differences": observed, "contract_violations": count("contract_violation"),
                             "expected_changes": count("expected_change"), "errors": errors,
                             "insufficient_evidence": uncertain, "accepted": sum(bool(f["accepted"]) for f in findings),
                             "deterministic": report.get("deterministic", False),
                             "equivalent": None if errors or not report.get("deterministic", False) else observed == 0,
                             "unaccepted_changes": sum(f["type"] == "observed_change" and not f["accepted"] for f in findings)}

