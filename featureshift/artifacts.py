"""Portable reports and a standalone old-output regression assertion."""

import html
import inspect
import json
from pathlib import Path


def html_report(report: dict) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value))
    pieces = ["<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
              f"<title>FeatureShift · {esc(report['title'])}</title>",
              "<style>body{font:16px system-ui;background:#f5f7f8;color:#172a3a;max-width:1080px;margin:40px auto;padding:0 24px}h1{letter-spacing:-1px}article,section{background:white;border:1px solid #d9e0e6;border-radius:12px;padding:24px;margin:18px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf2f4;padding:16px}a{color:#006c67}.tag{font-size:12px;text-transform:uppercase;color:#536370}code{font-size:13px}</style>",
              f"<h1>FeatureShift / {esc(report['title'])}</h1><p>pandas 2.3.3 → 3.0.0 · {esc(report['status'])}</p>",
              "<p>Observed differences from trusted local fixtures. This report is not a universal safe-upgrade judgment.</p>",
              f"<section><h2>Summary</h2><pre>{esc(json.dumps(report['summary'], indent=2))}</pre><p>Provider: deterministic rules · 0 model calls</p></section>"]
    for f in report.get("findings", []):
        pieces += [f"<article><span class='tag'>{esc(f['type'])}{' · Accepted' if f.get('accepted') else ''}</span><h2>{esc(f['title'])}</h2><p>{esc(f['description'])}</p><p>{esc(f.get('impact',''))}</p>",
                   f"<p>Comparison: <code>{esc(f['rule'])}</code> · Probe: {esc(f['probe_id'])}</p>",
                   f"<h3>Before / after</h3><pre>{esc(json.dumps({'before':f['before'],'after':f['after']},indent=2))}</pre>"]
        for e in f.get("evidence", []):
            pieces += [f"<p><a href='{esc(e['url'])}'>{esc(e['title'])}</a> · pandas {esc(e['source_version'])}</p><blockquote>{esc(e['passage'])}</blockquote>",
                       f"<small>SHA256 {esc(e['content_hash'])} · offsets {esc(e['start'])}:{esc(e['end'])} · fetched {esc(e['fetched_at'])}</small>"]
        if f.get("acceptance_reason"):
            pieces.append(f"<p>Review: {esc(f['acceptance_reason'])}</p>")
        pieces += [f"<h3>Reproduce</h3><pre>{esc(f['reproduce'])}</pre></article>"]
    for title, key in [("Source and inputs", "source"), ("Environment manifests", "environments"), ("Generated probes", "probes"), ("Execution records", "executions"), ("Review audit", "events")]:
        pieces.append(f"<section><h2>{title}</h2><pre>{esc(json.dumps(report.get(key),indent=2))}</pre></section>")
    pieces.append("</html>")
    return "\n".join(pieces)


def regression_test(report: dict) -> str:
    """Emit a pytest artifact that replays the captured input in any pandas env.

    Exact schema and values intentionally lock the pre-upgrade behavior. The
    original compare contract stays embedded; the assertion reuses the standalone
    serializer so null kinds, category mappings and numeric tolerances survive.
    """
    before = report.get("executions", {}).get("before", [])
    if not before or before[0].get("status") != "ok" or not report["summary"].get("deterministic"):
        return 'raise SystemExit("Regression artifact unavailable: a deterministic successful baseline is required.")\n'
    expected = before[0]["output"]
    code = report["source"]["code"]
    entrypoint = report["source"]["entrypoint"]
    selected_probe = "baseline"
    if not any(f["type"] == "observed_change" and f["probe_id"] == "baseline" for f in report["findings"]):
        changed_probes = {f["probe_id"] for f in report["findings"] if f["type"] == "observed_change"}
        for probe in report.get("probes", []):
            if probe["id"] in changed_probes and probe["status"] == "completed":
                expected = probe["executions"]["before"][0]["output"]
                code = probe["code"]
                entrypoint = "transform"
                selected_probe = probe["id"]
                break
    payload = json.dumps(report["input"]["fixture"], sort_keys=True)
    from featureshift import compare, worker
    support_code = "\n\n".join(inspect.getsource(fn) for fn in (
        worker.encode, worker.decode, worker.load_fixture, worker.encode_frame,
        compare.equal_value, compare._key, compare._match_rows, compare.compare_frames,
    ))
    return f'''"""FeatureShift regression for {report['case_id']}.
Captures the old behavior; inspect before adopting intentional migration changes.
Selected executed input: {selected_probe}. A generated wrapper may inject its boundary input.
Run in an environment containing pandas and NumPy:
    python /path/to/regression_test.py
Also collectable by pytest. No FeatureShift installation is required.
"""
from __future__ import annotations
import datetime as dt
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Any

MAX_ROWS = 10_000
MAX_CELLS = 100_000
Contract = SimpleNamespace

{support_code}

SOURCE = {code!r}
FIXTURE = json.loads({payload!r})
EXPECTED = json.loads({json.dumps(expected, sort_keys=True)!r})
CONTRACT = Contract(**json.loads({json.dumps(report['configuration']['contract'])!r}))

def test_captured_feature_behavior():
    namespace = {{}}
    exec(compile(SOURCE, "<captured-transform>", "exec"), namespace)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.json"
        path.write_text(json.dumps(FIXTURE))
        frame = load_fixture(path)
        actual = encode_frame(namespace[{entrypoint!r}](frame))
    differences = compare_frames(EXPECTED, actual, CONTRACT)
    assert not differences, json.dumps(differences, indent=2)

if __name__ == "__main__":
    test_captured_feature_behavior()
    print("Captured feature behavior matches the pre-upgrade baseline.")
'''


def write_artifacts(report: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in [("report.json", json.dumps(report, indent=2, allow_nan=False)),
                          ("report.html", html_report(report)), ("regression_test.py", regression_test(report))]:
        temp = directory / (name + ".tmp")
        temp.write_text(content)
        temp.replace(directory / name)

