"""Closed registry of reviewed sources; arbitrary paths never enter workers."""

import json
from pathlib import Path

from featureshift.config import ROOT
from featureshift.models import Case


def load_cases() -> list[Case]:
    paths = [ROOT / "examples" / "cases.json", ROOT / "benchmarks" / "cases.json"]
    cases = [Case.model_validate(case) for path in paths for case in json.loads(path.read_text())]
    if len({c.id for c in cases}) != len(cases):
        raise ValueError("Duplicate case identifiers")
    return cases


def get_case(case_id: str) -> Case:
    for case in load_cases():
        if case.id == case_id:
            return case
    raise KeyError(case_id)


def trusted_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not any(path.is_relative_to(ROOT / p) for p in ("examples", "benchmarks")):
        raise ValueError("Only repository-owned examples are enabled.")
    if not path.is_file():
        raise ValueError(f"Registered source is missing: {relative}")
    return path


def public_case(case: Case) -> dict:
    return case.model_dump(include={"id", "title", "description", "category", "expected", "split", "family", "provenance", "contract"})

