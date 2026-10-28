"""A single local entry point for setup, demo, preflight and evaluation."""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from featureshift.artifacts import write_artifacts
from featureshift.cases import load_cases
from featureshift.config import ROOT, STATE
from featureshift.engine import Engine, get_environments
from featureshift.evidence import corpus_status, retrieve
from featureshift.models import Contract, RunRequest
from featureshift.runner import setup_environments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="featureshift", description="Local pandas upgrade preflight — observed differences, versioned evidence.")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup", help="Build the pinned environments (only network-capable stage)")
    setup.add_argument("--offline", action="store_true")
    commands.add_parser("cases", help="List reviewed transformations")
    commands.add_parser("doctor", help="Inspect environments, evidence and execution restrictions")
    run = commands.add_parser("run", help="Execute a reviewed transformation under both pandas versions")
    run.add_argument("case_id")
    run.add_argument("--repeats", type=int, default=2)
    run.add_argument("--timeout", type=float, default=8)
    run.add_argument("--contract-json", help="Explicit comparison/output contract as a JSON object")
    run.add_argument("--output", type=Path)
    run.add_argument("--json", action="store_true")
    run.add_argument("--fail-on-contract", action="store_true")
    accept = commands.add_parser("accept", help="Record acceptance of a finding without erasing it")
    accept.add_argument("run_id")
    accept.add_argument("finding_id")
    accept.add_argument("--reason", required=True)
    evidence = commands.add_parser("evidence", help="Search the pinned offline corpus")
    evidence.add_argument("query")
    evidence.add_argument("--cutoff")
    evaluation = commands.add_parser("evaluate", help="Run labeled cases and baseline comparisons")
    evaluation.add_argument("--output", type=Path, default=STATE / "evaluation")
    evaluation.add_argument("--state", type=Path, default=STATE / "evaluation-state")
    demo = commands.add_parser("demo", help="Seed meaningful reports and serve the local UI")
    demo.add_argument("--seed-only", action="store_true")
    serve = commands.add_parser("serve", help="Serve existing local reports")
    for sub in (demo, serve):
        sub.add_argument("--port", type=int, default=int(os.environ.get("FEATURESHIFT_PORT", "8765")))
        sub.add_argument("--host", choices=["127.0.0.1", "localhost", "::1"], default=os.environ.get("FEATURESHIFT_HOST", "127.0.0.1"))
    commands.add_parser("reset", help="Remove generated reports/database; retain downloaded dependencies and evidence")
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            result = setup_environments(ROOT, offline=args.offline)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "ok" else 1
        if args.command == "cases":
            for case in load_cases():
                print(f"{case.id:26s} {case.title}")
            return 0
        if args.command == "doctor":
            from featureshift.config import upload_policy
            print(json.dumps({**upload_policy(), "environments": get_environments(), "corpus": corpus_status()}, indent=2))
            return 0
        if args.command == "evidence":
            print(json.dumps(retrieve(args.query, cutoff=args.cutoff), indent=2))
            return 0
        if args.command == "reset":
            for name in ("runs", "evaluation", "evaluation-state"):
                path = STATE / name
                if path.is_dir():
                    shutil.rmtree(path)
            for name in ("featureshift.sqlite3", "featureshift.sqlite3-wal", "featureshift.sqlite3-shm"):
                (STATE / name).unlink(missing_ok=True)
            print("Generated local reports reset. Dependency environments and evidence retained.")
            return 0
        if args.command == "evaluate":
            from featureshift.evaluation import evaluate
            result = evaluate(args.state, args.output)
            print(json.dumps(result.get("summary", result), indent=2))
            print(f"Evaluation artifacts: {args.output.resolve()}")
            return 0 if result.get("acceptance_passed", True) else 1
        engine = Engine()
        if args.command == "run":
            contract = Contract.model_validate_json(args.contract_json) if args.contract_json else None
            report = engine.run(RunRequest(case_id=args.case_id, repeats=args.repeats, timeout_s=args.timeout, contract=contract))
            if args.output:
                write_artifacts(report, args.output)
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(f"{report['title']}: {report['status']} / run {report['id']}")
                print(json.dumps(report["summary"], indent=2))
                print(f"Report: {engine.store.state / 'runs' / report['id'] / 'report.html'}")
            return 2 if args.fail_on_contract and report["summary"]["contract_violations"] else (1 if report["status"] == "failed" else 0)
        if args.command == "accept":
            report = engine.store.accept(args.run_id, args.finding_id, args.reason)
            write_artifacts(report, engine.store.state / "runs" / args.run_id)
            print(f"Acceptance saved for {args.finding_id}; original observation retained.")
            return 0
        if args.command == "demo":
            for case_id in ("numeric", "intentional", "selector"):
                report = engine.run(RunRequest(case_id=case_id))
                print(f"Seeded {case_id}: {report['status']} ({report['summary']['observed_differences']} differences)", flush=True)
                if report["status"] != "completed":
                    print("Demo setup incomplete. Inspect the report and run make setup.", file=sys.stderr)
                    return 1
            if args.seed_only:
                return 0
        if args.command in ("serve", "demo"):
            import uvicorn

            from featureshift.api import create_app
            print(f"FeatureShift: http://{args.host}:{args.port} — trusted fixtures, no live model", flush=True)
            uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
            return 0
    except (ValueError, KeyError) as exc:
        print(f"Invalid request: {exc}", file=sys.stderr)
        return 2
    return 0

