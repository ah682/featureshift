"""Reviewable, bounded probe generation through an explicit provider interface.

The baseline is a small documented rule set, not a language model. Inputs are
repository-owned source and sanitized fixtures; documents never become code.
"""

import ast
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Probe:
    id: str
    title: str
    reason: str
    code: str
    timeout_s: float | None = None


class ProbeProvider(Protocol):
    name: str

    def propose(self, code: str, fixture: dict, entrypoint: str, fault: str | None = None) -> list[Probe]: ...


def operations(code: str, fixture: dict) -> list[dict]:
    tree = ast.parse(code)
    signals = []
    rules = [
        ("dtype-check", "dtypes", "dtype object string check is_string_dtype feature selector", "A dtype equality mask can exclude newly inferred strings."),
        ("string-cast", "astype", "astype str preserving missing values conversion", "String conversion can change null preservation and dtype."),
        ("select-dtypes", "select_dtypes", "select_dtypes object string backward compatibility", "Selection compatibility must be checked by executing this exact version."),
        ("copy-on-write", "inplace", "copy-on-write chained assignment inplace", "Chained mutation may stop updating its parent."),
        ("groupby", "groupby", "groupby observed categorical default True", "An implicit observed default can change categorical groups."),
        ("datetime", "to_datetime", "datetime resolution microsecond datetime64 us", "Datetime inference can change output units."),
        ("missing-indicator", "isna", "astype str preserving missing values conversion", "A null-preserving conversion can change a derived missingness indicator."),
    ]
    # AST determines operations. Only source strings supplement keyword arguments.
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    keywords = {n.arg for n in ast.walk(tree) if isinstance(n, ast.keyword)}
    for ident, marker, query, impact in rules:
        if marker in attrs | keywords:
            signals.append({"id": ident, "query": query, "impact": impact})
    if not signals and any(isinstance(v, str) for values in fixture.get("data", {}).values() for v in values):
        signals.append({"id": "string-inference", "query": "inferred string dtype object default null sentinel NaN", "impact": "Inferred string features may change dtype or missing-value representation."})
    return signals


class RulesProbeProvider:
    name = "deterministic-rules"

    def propose(self, code: str, fixture: dict, entrypoint: str, fault: str | None = None) -> list[Probe]:
        if fault == "probe_timeout":
            return [Probe("deadline-control", "Deadline control probe", "Constructed reliability case: terminate a generated non-terminating probe.",
                          "import time\n\ndef transform(df):\n    time.sleep(60)\n    return df\n", 0.5)]
        if fault == "probe_syntax":
            return [Probe("syntax-control", "Invalid syntax control", "Constructed validation negative case.", "def transform(:\n")]
        found = operations(code, fixture)
        if not found:
            return []
        text_cols = [name for name, values in fixture.get("data", {}).items() if any(isinstance(v, str) for v in values)]
        # Null injection targets the input boundary; only pre-reviewed templates
        # write code. It preserves input size and cannot add arbitrary imports.
        cols = text_cols or list(fixture.get("data", {}))[:1]
        if not cols:
            return []
        generated = code + f"\n\n_featureshift_original = {entrypoint}\n\ndef transform(df):\n"
        generated += "    candidate = df.copy(deep=True)\n"
        generated += f"    for column in {cols!r}:\n        if len(candidate):\n            candidate.loc[candidate.index[0], column] = None\n"
        generated += "    return _featureshift_original(candidate)\n"
        return [Probe("null-boundary", "Missing-value boundary", "Inject a missing value into an input feature, then execute the unchanged transformation. Review the generated wrapper below.", generated)]


def validate_syntax(code: str) -> dict:
    try:
        tree = ast.parse(code)
        compile(tree, "<reviewable-probe>", "exec")
        return {"valid": True, "error": None}
    except SyntaxError as exc:
        return {"valid": False, "error": f"{exc.msg} (line {exc.lineno})"}

