"""Compare structured outputs without importing either target pandas version."""

import json
import math
from typing import Any

from featureshift.models import Contract


def equal_value(a: Any, b: Any, contract: Contract) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        if "$null" in a and "$null" in b and contract.nulls == "equivalent":
            return True
        return a.keys() == b.keys() and all(equal_value(a[k], b[k], contract) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal_value(x, y, contract) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (float, int)) and isinstance(b, (float, int)):
        if isinstance(a, int) and isinstance(b, int):
            return abs(a - b) <= max(contract.atol, contract.rtol * max(abs(a), abs(b)))
        return math.isclose(a, b, rel_tol=contract.rtol, abs_tol=contract.atol)
    return type(a) is type(b) and a == b


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _match_rows(old: list, new: list, contract: Contract) -> list[int] | None:
    """Find a bijection, not a greedy match (tolerances are not transitive)."""
    if len(old) != len(new):
        return None
    if len(old) > 500:
        raise ValueError("Unordered tolerant comparison is limited to 500 rows; use a smaller fixture or row_order=True.")
    candidates = [[j for j, b in enumerate(new) if equal_value(a, b, contract)] for a in old]
    matched: dict[int, int] = {}

    def augment(i: int, seen: set[int]) -> bool:
        for j in candidates[i]:
            if j not in seen:
                seen.add(j)
                if j not in matched or augment(matched[j], seen):
                    matched[j] = i
                    return True
        return False

    for i in range(len(old)):
        if not augment(i, set()):
            return None
    result = [0] * len(old)
    for j, i in matched.items():
        result[i] = j
    return result


def compare_frames(before: dict, after: dict, contract: Contract) -> list[dict]:
    changes: list[dict] = []

    def add(rule: str, a: Any, b: Any, description: str) -> None:
        changes.append({"rule": rule, "before": a, "after": b, "description": description})

    if before["row_count"] != after["row_count"]:
        add("row_count", before["row_count"], after["row_count"], "The number of output rows changed.")
    old_names = [c["name"] for c in before["columns"]]
    new_names = [c["name"] for c in after["columns"]]
    old_keys, new_keys = list(map(_key, old_names)), list(map(_key, new_names))
    if len(set(old_keys)) != len(old_keys) or len(set(new_keys)) != len(new_keys):
        raise ValueError("Duplicate output column labels are unsupported; declare unique feature names.")
    compared_names = (old_keys, new_keys) if contract.column_order else (sorted(old_keys), sorted(new_keys))
    if compared_names[0] != compared_names[1]:
        add("columns", old_names, new_names, "Selected feature columns or their declared order changed.")

    # Align by names so an allowed column reorder does not appear as value changes.
    common = sorted(set(old_keys) & set(new_keys))
    old_pos = [old_keys.index(k) for k in common]
    new_pos = [new_keys.index(k) for k in common]
    for oi, ni in zip(old_pos, new_pos):
        a, b = before["columns"][oi], after["columns"][ni]
        name = str(a["name"])
        if contract.compare_dtypes and a["dtype"] != b["dtype"]:
            add(f"dtype:{name}", a["dtype"], b["dtype"], f"The inferred dtype of {name!r} changed.")
        if (a.get("categories"), a.get("ordered")) != (b.get("categories"), b.get("ordered")):
            add(f"categories:{name}", {k: a.get(k) for k in ("categories", "ordered")},
                {k: b.get(k) for k in ("categories", "ordered")}, "Category mapping or ordering changed.")

    old_rows = [[row[i] for i in old_pos] for row in before["data"]]
    new_rows = [[row[i] for i in new_pos] for row in after["data"]]
    old_index, new_index = before.get("index", []), after.get("index", [])
    if not contract.row_order:
        # Compare a multiset of whole records, retaining index→row association.
        a = [[old_index[i], row] for i, row in enumerate(old_rows)] if contract.compare_index else old_rows
        b = [[new_index[i], row] for i, row in enumerate(new_rows)] if contract.compare_index else new_rows
        match = _match_rows(a, b, contract)
        if match is None:
            add("rows", a, b, "The unordered output records differ, including multiplicity and declared index associations.")
        else:
            new_rows = [new_rows[j] for j in match]
            if contract.compare_index:
                new_index = [new_index[j] for j in match]
    if contract.compare_index and not equal_value(old_index, new_index, contract):
        add("index", old_index, new_index, "Output index labels changed.")
    if contract.compare_index and not equal_value(before.get("index_names"), after.get("index_names"), contract):
        add("index_names", before.get("index_names"), after.get("index_names"), "Output index names changed.")
    for position, key in enumerate(common):
        a = [row[position] for row in old_rows]
        b = [row[position] for row in new_rows]
        if not equal_value(a, b, contract):
            name = old_names[old_keys.index(key)]
            changed_values = [v for x, y in zip(a, b) if not equal_value(x, y, contract) for v in (x, y)]
            changed_values.extend(a[len(b):] + b[len(a):])
            null_change = any(isinstance(v, dict) and "$null" in v for v in changed_values)
            prefix = "nulls" if null_change else "values"
            add(f"{prefix}:{name}", a, b, f"Values in {name!r} differ under the declared comparison rule.")
    return changes


def contract_violations(frame: dict, contract: Contract) -> list[dict]:
    violations: list[dict] = []
    columns = [c["name"] for c in frame["columns"]]
    if contract.expected_columns is not None:
        actual, expected = columns, contract.expected_columns
        if not contract.column_order:
            actual, expected = sorted(actual, key=_key), sorted(expected, key=_key)
        if actual != expected:
            violations.append({"rule": "contract:columns", "before": expected, "after": columns,
                               "description": "Output columns violate the declared feature contract."})
    if contract.expected_row_count is not None and frame["row_count"] != contract.expected_row_count:
        violations.append({"rule": "contract:row_count", "before": contract.expected_row_count,
                           "after": frame["row_count"], "description": "Row count violates the contract."})
    dtypes = {_key(c["name"]): c["dtype"] for c in frame["columns"]}
    for col, dtype in contract.expected_dtypes.items():
        if dtypes.get(_key(col)) != dtype:
            violations.append({"rule": f"contract:dtype:{col}", "before": dtype, "after": dtypes.get(_key(col)),
                               "description": f"The declared dtype for {col!r} is not satisfied."})
    for col in contract.non_null:
        if col not in columns:
            count: int | str = "missing column"
        else:
            pos = columns.index(col)
            count = sum(isinstance(row[pos], dict) and "$null" in row[pos] for row in frame["data"])
        if count:
            violations.append({"rule": f"contract:non_null:{col}", "before": 0, "after": count,
                               "description": f"The declared non-null feature {col!r} is not satisfied."})
    return violations

