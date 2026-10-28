"""Comparison rules tested with independently specified observable outcomes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from featureshift.compare import compare_frames, contract_violations, equal_value
from featureshift.models import Contract, RunRequest


def frame(data: list[list[Any]], names: tuple[str, ...] = ("value",), index: list[Any] | None = None, dtype: str = "float64") -> dict:
    return {
        "row_count": len(data),
        "columns": [{"name": name, "dtype": dtype} for name in names],
        "index": list(range(len(data))) if index is None else index,
        "data": data,
    }


def rules(changes: list[dict]) -> set[str]:
    return {change["rule"] for change in changes}


def test_numeric_tolerance_is_explicit_and_booleans_remain_distinct() -> None:
    contract = Contract(rtol=0.001, atol=0.0001)
    assert equal_value(1000, 1000.5, contract)
    assert equal_value(0, 0.00005, contract)
    assert not equal_value(1000, 1002, contract)
    assert not equal_value(True, 1, contract)
    assert not equal_value(False, 0, contract)
    assert not equal_value("1", 1, contract)
    assert rules(compare_frames(frame([[1.0]]), frame([[1.01]]), Contract(rtol=0, atol=0))) == {"values:value"}


def test_exact_integer_comparison_keeps_precision_beyond_float_mantissa() -> None:
    exact = Contract(rtol=0, atol=0)
    assert not equal_value(2**60, 2**60 + 1, exact)
    assert equal_value(2**60, 2**60, exact)


@pytest.mark.parametrize("left,right", [("None", "NaN"), ("NaN", "NA"), ("NA", "NaT"), ("NaT", "None")])
def test_null_kinds_only_normalize_when_declared(left: str, right: str) -> None:
    before, after = frame([[{"$null": left}]]), frame([[{"$null": right}]])
    assert rules(compare_frames(before, after, Contract())) == {"nulls:value"}
    assert compare_frames(before, after, Contract(nulls="equivalent")) == []
    assert not equal_value({"$null": left}, "nan", Contract(nulls="equivalent"))


def test_allowed_column_reordering_aligns_each_feature_by_name() -> None:
    before = frame([[1, 100], [2, 200]], ("x", "y"))
    after = frame([[100, 1], [200, 2]], ("y", "x"))
    assert rules(compare_frames(before, after, Contract())) == {"columns"}
    assert compare_frames(before, after, Contract(column_order=False)) == []
    after["data"][0][1] = 42
    assert rules(compare_frames(before, after, Contract(column_order=False))) == {"values:x"}


def test_missing_feature_is_reported_without_unrelated_value_changes() -> None:
    before = frame([[1, 100], [2, 200]], ("x", "y"))
    after = frame([[1], [2]], ("x",))
    assert rules(compare_frames(before, after, Contract(column_order=False))) == {"columns"}


def test_unordered_rows_preserve_row_membership_and_multiplicity() -> None:
    before = frame([[1, 100], [2, 200]], ("x", "y"))
    reordered = frame([[2, 200], [1, 100]], ("x", "y"))
    contract = Contract(row_order=False, compare_index=False)
    assert compare_frames(before, reordered, contract) == []
    reassociated = frame([[1, 200], [2, 100]], ("x", "y"))
    assert compare_frames(before, reassociated, contract)
    assert compare_frames(frame([[1], [1], [2]]), frame([[1], [2], [2]]), contract)


def test_unordered_rows_preserve_index_to_feature_association() -> None:
    before = frame([[1], [2]], index=["a", "b"])
    contract = Contract(row_order=False, compare_index=True)
    assert compare_frames(before, frame([[2], [1]], index=["b", "a"]), contract) == []
    assert compare_frames(before, frame([[2], [1]], index=["a", "b"]), contract)


def test_unordered_rows_apply_null_equivalence_before_matching() -> None:
    before = frame([[{"$null": "None"}, 1], [{"$null": "NaN"}, 2]], ("null", "id"))
    after = frame([[{"$null": "NaN"}, 1], [{"$null": "None"}, 2]], ("null", "id"))
    assert compare_frames(before, after, Contract(row_order=False, compare_index=False, nulls="equivalent")) == []


def test_unordered_rows_apply_numeric_tolerances_when_matching() -> None:
    before = frame([[9.999, "x"], [10.0001, "y"]], ("value", "label"))
    after = frame([[10.0002, "x"], [10.0003, "y"]], ("value", "label"))
    assert compare_frames(before, after, Contract(row_order=False, compare_index=False, atol=0.002, rtol=0)) == []


def test_unordered_tolerant_matching_finds_a_bijection_when_greedy_pairing_fails() -> None:
    before, after = frame([[0.0], [0.09]]), frame([[0.05], [-0.05]])
    assert compare_frames(before, after, Contract(row_order=False, compare_index=False, atol=0.1, rtol=0)) == []


def test_index_comparison_can_be_disabled_without_hiding_value_changes() -> None:
    before, after = frame([[1]], index=["old"]), frame([[1]], index=["new"])
    assert rules(compare_frames(before, after, Contract())) == {"index"}
    assert compare_frames(before, after, Contract(compare_index=False)) == []
    after["data"] = [[2]]
    assert rules(compare_frames(before, after, Contract(compare_index=False))) == {"values:value"}


def test_index_names_participate_only_when_index_is_contractually_relevant() -> None:
    before, after = frame([[1]]), frame([[1]])
    before["index_names"], after["index_names"] = ["customer"], ["anonymous"]
    assert rules(compare_frames(before, after, Contract())) == {"index_names"}
    assert compare_frames(before, after, Contract(compare_index=False)) == []


def test_dtype_and_category_mapping_have_independent_rules() -> None:
    before = frame([["low"], ["high"]], dtype="category")
    before["columns"][0].update(categories=["low", "high"], ordered=True)
    after = deepcopy(before)
    after["columns"][0]["categories"] = ["high", "low"]
    assert rules(compare_frames(before, after, Contract(compare_dtypes=False))) == {"categories:value"}
    after["columns"][0] = {"name": "value", "dtype": "object"}
    assert rules(compare_frames(before, after, Contract())) == {"dtype:value", "categories:value"}


def test_declared_contract_reports_schema_rows_dtype_and_null_violations() -> None:
    output = frame([[1, {"$null": "NA"}]], ("id", "feature"))
    contract = Contract(expected_columns=["id", "feature", "required"], expected_row_count=2,
                        expected_dtypes={"id": "int64", "required": "str"}, non_null=["feature", "required"])
    violations = contract_violations(output, contract)
    assert rules(violations) == {"contract:columns", "contract:row_count", "contract:dtype:id", "contract:dtype:required", "contract:non_null:feature", "contract:non_null:required"}
    by_rule = {item["rule"]: item for item in violations}
    assert by_rule["contract:non_null:feature"]["after"] == 1
    assert by_rule["contract:non_null:required"]["after"] == "missing column"


def test_unordered_column_contract_handles_mixed_tuple_and_string_labels() -> None:
    output = frame([[1, 2]], ("placeholder", "y"), dtype="int64")
    tuple_label = {"$tuple": ["group", "x"]}
    output["columns"][0]["name"] = tuple_label
    contract = Contract(column_order=False, expected_columns=["y"], expected_dtypes={"y": "int64"})
    violations = contract_violations(output, contract)
    assert rules(violations) == {"contract:columns"}
    assert violations[0]["after"] == [tuple_label, "y"]


def test_duplicate_output_labels_are_explicitly_unsupported() -> None:
    with pytest.raises(ValueError, match="Duplicate output column"):
        compare_frames(frame([[1, 2]], ("same", "same")), frame([[1, 2]], ("same", "same")), Contract())


@pytest.mark.parametrize("kwargs", [{"rtol": -0.01}, {"atol": float("nan")}, {"atol": float("inf")}, {"nulls": "guess"}, {"unknown_setting": True}])
def test_invalid_comparison_contract_is_rejected(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        Contract(**kwargs)


def test_run_request_requires_repeats_and_registry_identifiers() -> None:
    with pytest.raises(ValidationError):
        RunRequest(case_id="numeric", repeats=1)
    with pytest.raises(ValidationError):
        RunRequest(case_id="../../untrusted.py")
