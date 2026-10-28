"""Standalone entry point for the two dependency environments.

This is a resource-bounded *trusted* process, not an untrusted-code sandbox.
It deliberately has no dependency on the host application's packages.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import resource
import sys
import traceback
from pathlib import Path
from typing import Any

MAX_ROWS = 10_000
MAX_CELLS = 100_000


class MissingExistingTest(ValueError):
    """The optional existing-test baseline was not supplied."""


def apply_limits(timeout_s: float) -> dict[str, int]:
    """Apply Linux/POSIX damage limits before importing native libraries."""
    limits = {
        "cpu_seconds": max(1, math.ceil(timeout_s)),
        "address_space_bytes": 1536 * 1024 * 1024,
        "file_bytes": 8 * 1024 * 1024,
        "processes_per_user": 32,
        "open_files": 64,
    }
    resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu_seconds"], limits["cpu_seconds"] + 1))
    resource.setrlimit(resource.RLIMIT_AS, (limits["address_space_bytes"], limits["address_space_bytes"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits["file_bytes"], limits["file_bytes"]))
    resource.setrlimit(resource.RLIMIT_NPROC, (limits["processes_per_user"], limits["processes_per_user"]))
    resource.setrlimit(resource.RLIMIT_NOFILE, (limits["open_files"], limits["open_files"]))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return limits


def encode(value: Any, pd: Any, np: Any) -> Any:
    """Losslessly distinguish supported scalar values, especially null sentinels."""
    if value is None:
        return {"$null": "None"}
    if value is pd.NA:
        return {"$null": "NA"}
    if value is pd.NaT:
        return {"$null": "NaT"}
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if math.isnan(number):
            return {"$null": "NaN"}
        if math.isinf(number):
            return {"$float": "Infinity" if number > 0 else "-Infinity"}
        return number
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (pd.Timestamp, dt.datetime, dt.date)):
        return {"$datetime": value.isoformat()}
    if isinstance(value, (pd.Timedelta, dt.timedelta)):
        return {"$timedelta_ns": int(pd.Timedelta(value).value)}
    if isinstance(value, (np.datetime64, np.timedelta64)):
        if np.isnat(value):
            return {"$null": "NaT"}
        converted = pd.Timestamp(value) if isinstance(value, np.datetime64) else pd.Timedelta(value)
        return encode(converted, pd, np)
    if isinstance(value, tuple):
        return {"$tuple": [encode(item, pd, np) for item in value]}
    if isinstance(value, list):
        return [encode(item, pd, np) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Structured cell dictionaries must have string keys")
        return {key: encode(item, pd, np) for key, item in value.items()}
    raise TypeError(f"Unsupported output scalar type: {type(value).__name__}")


def decode(value: Any, pd: Any, np: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"$null"}:
        sentinels = {"None": None, "NaN": np.nan, "NA": pd.NA, "NaT": pd.NaT}
        if value["$null"] not in sentinels:
            raise ValueError("Unknown fixture null sentinel")
        return sentinels[value["$null"]]
    if isinstance(value, dict) and set(value) == {"$float"}:
        return {"Infinity": np.inf, "-Infinity": -np.inf}[value["$float"]]
    if isinstance(value, list):
        return [decode(item, pd, np) for item in value]
    if isinstance(value, dict):
        return {key: decode(item, pd, np) for key, item in value.items()}
    return value


def load_fixture(path: Path, pd: Any = None, np: Any = None) -> Any:
    if pd is None:
        import pandas as pandas_module
        pd = pandas_module
    if np is None:
        import numpy as numpy_module
        np = numpy_module
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Fixture exceeds the 1 MiB trusted-demo limit")
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(fixture, dict) or not isinstance(fixture.get("data"), dict):
        raise ValueError("Fixture must contain a data mapping of column names to lists")
    if not all(isinstance(items, list) for items in fixture["data"].values()):
        raise ValueError("Every fixture column must be a list")
    df = pd.DataFrame(decode(fixture["data"], pd, np))
    if len(df) > MAX_ROWS or df.size > MAX_CELLS:
        raise ValueError("Fixture exceeds trusted-demo row/cell limits")
    for name in fixture.get("date_columns", []):
        df[name] = pd.to_datetime(df[name])
    for name, dtype in fixture.get("dtypes", {}).items():
        if isinstance(dtype, dict):
            dtype = pd.CategoricalDtype(categories=dtype["categories"], ordered=dtype.get("ordered", False))
        df[name] = df[name].astype(dtype)
    if "index" in fixture:
        df.index = decode(fixture["index"], pd, np)
    return df


def encode_frame(frame: Any, pd: Any = None, np: Any = None) -> dict[str, Any]:
    if pd is None:
        import pandas as pandas_module
        pd = pandas_module
    if np is None:
        import numpy as numpy_module
        np = numpy_module
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Transformation entry point must return a pandas.DataFrame")
    if len(frame) > MAX_ROWS or frame.size > MAX_CELLS:
        raise ValueError("Output exceeds trusted-demo row/cell limits")
    columns = []
    for position, name in enumerate(frame.columns):
        series = frame.iloc[:, position]
        column = {"name": encode(name, pd, np), "dtype": str(series.dtype)}
        if isinstance(series.dtype, pd.CategoricalDtype):
            column["categories"] = [encode(value, pd, np) for value in series.cat.categories]
            column["ordered"] = bool(series.cat.ordered)
        columns.append(column)
    # Do not use iterrows(): it can coerce integers to floats across a mixed row.
    arrays = [frame.iloc[:, position].array for position in range(frame.shape[1])]
    return {
        "row_count": len(frame),
        "columns": columns,
        "index": [encode(value, pd, np) for value in frame.index],
        "index_names": [encode(value, pd, np) for value in frame.index.names],
        "data": [[encode(values[row], pd, np) for values in arrays] for row in range(len(frame))],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--entrypoint", default="transform")
    parser.add_argument("--timeout", type=float, default=8)
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    result: dict[str, Any] = {"status": "error", "output": None, "versions": {}, "error": None}
    stage = "environment"
    try:
        result["limits"] = apply_limits(args.timeout)
        import numpy as np
        import pandas as pd

        result["versions"] = {"python": platform.python_version(), **{
            name: importlib.metadata.version(name)
            for name in ["pandas", "numpy", "python-dateutil", "pytz", "tzdata", "six"]
        }}
        stage = "fixture"
        df = load_fixture(args.fixture, pd, np)
        stage = "source"
        spec = importlib.util.spec_from_file_location("featureshift_trusted_transform", args.source)
        if spec is None or spec.loader is None:
            raise ImportError("Cannot create transformation module")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stage = "existing_test" if args.test_mode else "transform"
        name = "existing_test" if args.test_mode else args.entrypoint
        entrypoint = getattr(module, name, None)
        if not callable(entrypoint):
            if args.test_mode:
                raise MissingExistingTest("No optional existing_test(df) entry point was supplied")
            raise ValueError(f"Missing callable entry point: {name}")
        if args.test_mode:
            value = entrypoint(df)
            if value is False:
                raise AssertionError("existing_test returned False")
            result["test_passed"] = True
        else:
            value = entrypoint(df)
            stage = "serialization"
            result["output"] = encode_frame(value, pd, np)
        result["status"] = "ok"
    except BaseException as error:
        result["status"] = "environment_error" if stage == "environment" else "error"
        result["error"] = {
            "type": type(error).__name__, "message": str(error), "stage": stage,
            "traceback": traceback.format_exc(limit=12),
        }
        if args.test_mode:
            result["test_passed"] = False
    try:
        temporary = args.output.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        os.replace(temporary, args.output)
    except BaseException:
        traceback.print_exc(file=sys.stderr)
        return 2
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
