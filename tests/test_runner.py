"""Observable worker results under the actual pinned pandas environments."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from featureshift.runner import environment_manifest, run_worker, verify_install_failure

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = {profile: ROOT / ".featureshift" / "envs" / profile / "bin" / "python" for profile in ("before", "after")}
requires_pair = pytest.mark.skipif(not all(path.exists() for path in ENVIRONMENTS.values()), reason="Run python3 scripts/setup_environments.py for real worker integration tests")


def write_case(tmp_path: Path, code: str, data: dict | None = None) -> tuple[Path, Path]:
    source = tmp_path / "transform.py"
    source.write_text(code, encoding="utf-8")
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps(data if data is not None else {"data": {"n": [1, 2]}}), encoding="utf-8")
    return source, fixture


@pytest.mark.integration
@requires_pair
def test_real_legacy_selector_drops_inferred_strings_only_after_upgrade(tmp_path: Path) -> None:
    source, fixture = write_case(tmp_path, "def transform(df):\n    return df.loc[:, df.dtypes == 'object']\n", {"data": {"city": ["Oslo", "Rome", None], "n": [1, 2, 3]}})
    outputs = {name: run_worker(python, source, fixture, tmp_path / name) for name, python in ENVIRONMENTS.items()}
    assert all(result["status"] == "ok" for result in outputs.values()), outputs
    assert outputs["before"]["versions"]["pandas"] == "2.3.3"
    assert outputs["after"]["versions"]["pandas"] == "3.0.0"
    assert outputs["before"]["output"]["columns"] == [{"name": "city", "dtype": "object"}]
    assert outputs["after"]["output"]["columns"] == []
    assert outputs["after"]["output"]["row_count"] == 3
    assert outputs["after"]["output"]["data"] == [[], [], []]
    assert {name: version for name, version in outputs["before"]["versions"].items() if name != "pandas"} == {name: version for name, version in outputs["after"]["versions"].items() if name != "pandas"}


@pytest.mark.integration
@requires_pair
def test_serialization_preserves_nulls_numeric_values_and_categories(tmp_path: Path) -> None:
    source, fixture = write_case(tmp_path, "def transform(df):\n    return df\n", {
        "data": {
            "nulls": [{"$null": "None"}, {"$null": "NaN"}, {"$null": "NA"}, {"$null": "NaT"}],
            "integer": [1, 2, 3, 4], "number": [1.5, {"$float": "Infinity"}, {"$float": "-Infinity"}, 0.0],
            "level": ["low", "high", "low", "low"],
        },
        "dtypes": {"nulls": "object", "level": {"categories": ["low", "high", "unused"], "ordered": True}},
    })
    for name, python in ENVIRONMENTS.items():
        result = run_worker(python, source, fixture, tmp_path / name)
        assert result["status"] == "ok", result
        output = result["output"]
        assert [row[0] for row in output["data"]] == [{"$null": value} for value in ("None", "NaN", "NA", "NaT")]
        assert isinstance(output["data"][0][1], int)
        assert isinstance(output["data"][0][2], float)
        assert output["data"][1][2] == {"$float": "Infinity"}
        assert output["data"][2][2] == {"$float": "-Infinity"}
        assert output["columns"][3] == {"name": "level", "dtype": "category", "categories": ["low", "high", "unused"], "ordered": True}


@pytest.mark.integration
@requires_pair
def test_worker_omits_ambient_secret_and_captures_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEATURESHIFT_TEST_SECRET", "do-not-forward-this-value")
    source, fixture = write_case(tmp_path, "import os, sys\ndef transform(df):\n    print(os.environ.get('FEATURESHIFT_TEST_SECRET', 'absent'))\n    print('warning from example', file=sys.stderr)\n    return df\n")
    result = run_worker(ENVIRONMENTS["before"], source, fixture, tmp_path / "result")
    assert result["status"] == "ok", result
    assert result["stdout"] == "absent\n"
    assert result["stderr"] == "warning from example\n"
    assert result["execution_profile"]["secure_sandbox"] is False
    assert result["execution_profile"]["arbitrary_uploads"] is False


@pytest.mark.integration
@requires_pair
def test_timeout_is_recorded_and_next_job_remains_healthy(tmp_path: Path) -> None:
    source, fixture = write_case(tmp_path, "import time\ndef transform(df):\n    print('started', flush=True)\n    time.sleep(10)\n    return df\n")
    timed_out = run_worker(ENVIRONMENTS["after"], source, fixture, tmp_path / "timeout", timeout_s=0.8)
    assert timed_out["status"] == "timeout", timed_out
    assert timed_out["exit_code"] is not None and timed_out["exit_code"] < 0
    assert timed_out["duration_s"] < 4
    assert json.loads((tmp_path / "timeout" / "result.json").read_text())["status"] == "timeout"
    source.write_text("def transform(df):\n    return df\n", encoding="utf-8")
    healthy = run_worker(ENVIRONMENTS["after"], source, fixture, tmp_path / "healthy")
    assert healthy["status"] == "ok", healthy
    assert healthy["output"]["data"] == [[1], [2]]


@pytest.mark.integration
@requires_pair
def test_existing_tests_and_invalid_transform_return_are_distinct(tmp_path: Path) -> None:
    source, fixture = write_case(tmp_path, "def transform(df):\n    return 42\ndef existing_test(df):\n    assert df.shape == (2, 1)\n")
    test_result = run_worker(ENVIRONMENTS["before"], source, fixture, tmp_path / "test", test_mode=True)
    assert test_result["status"] == "ok" and test_result["test_passed"] is True
    assert test_result["output"] is None
    run_result = run_worker(ENVIRONMENTS["before"], source, fixture, tmp_path / "transform")
    assert run_result["status"] == "error"
    assert run_result["error"]["stage"] == "serialization"
    assert run_result["error"]["type"] == "TypeError"
    source.write_text("def existing_test(df):\n    assert len(df) == 999\n", encoding="utf-8")
    failed = run_worker(ENVIRONMENTS["after"], source, fixture, tmp_path / "failed-test", test_mode=True)
    assert failed["status"] == "error" and failed["test_passed"] is False
    assert failed["error"]["type"] == "AssertionError"


def test_missing_environment_is_persisted_as_environment_error(tmp_path: Path) -> None:
    source, fixture = write_case(tmp_path, "def transform(df):\n    return df\n")
    result = run_worker(tmp_path / "missing-python", source, fixture, tmp_path / "result")
    assert result["status"] == "environment_error"
    assert result["output"] is None and result["exit_code"] is None
    assert json.loads((tmp_path / "result" / "result.json").read_text())["status"] == "environment_error"


@pytest.mark.integration
@requires_pair
def test_impossible_pinned_install_fails_without_changing_environment() -> None:
    result = verify_install_failure(ROOT)
    assert result["status"] == "environment_error"
    assert result["verified"] is True and result["environment_unchanged"] is True
    assert result["exit_code"] == 1
    assert result["semantic_regression"] is False
    assert environment_manifest(ENVIRONMENTS["before"])["packages"]["pandas"] == "2.3.3"
