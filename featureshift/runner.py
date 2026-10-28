"""Pinned environment setup and resource-bounded repository-owned workers.

Callers MUST enforce their trusted-source registry. This module is not a secure
sandbox; arbitrary repositories/uploads are deliberately outside its contract.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

EXPECTED_PACKAGES = {
    "numpy": "2.2.6", "python-dateutil": "2.9.0.post0", "pytz": "2025.2",
    "tzdata": "2025.2", "six": "1.17.0",
}
LOG_LIMIT = 64 * 1024
WORKER = Path(__file__).with_name("worker.py").resolve()
EXECUTION_PROFILE = {
    "mode": "trusted_subprocess", "arbitrary_uploads": False, "secure_sandbox": False,
    "network_isolated": False, "filesystem_isolated": False,
    "limits": "POSIX CPU/address-space/file-size/process/open-file limits; wall timeout kills process group",
    "warning": "Only repository-owned examples and approved generated probes may run. This process can access host files and network.",
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _clean_environment(python: Path, artifact_dir: Path | None = None) -> dict[str, str]:
    env = {
        "PATH": f"{python.parent}:/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "TZ": "UTC", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
    }
    if artifact_dir is not None:
        env["TMPDIR"] = str(artifact_dir)
    return env


def environment_manifest(python: Path) -> dict[str, Any]:
    """Inspect installed metadata without importing the selected transformation."""
    # absolute(), not resolve(): resolving a venv interpreter symlink loses its venv.
    python = Path(python).absolute()
    code = """
import importlib.metadata as md, json, platform, sys
packages = {d.metadata['Name'].lower().replace('_','-'): d.version for d in md.distributions()}
metadata = {name: {'requires_python': md.metadata(name).get('Requires-Python'), 'requires_dist': md.requires(name) or []} for name in ('pandas', 'numpy') if name in packages}
print(json.dumps({'python': platform.python_version(), 'executable': sys.executable, 'packages': dict(sorted(packages.items())), 'platform': platform.platform(), 'machine': platform.machine(), 'dependency_metadata': metadata}))
"""
    try:
        completed = subprocess.run(
            [str(python), "-I", "-B", "-c", code], capture_output=True, text=True,
            timeout=10, env=_clean_environment(python), check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr[-4000:] or f"Interpreter exited {completed.returncode}")
        manifest = json.loads(completed.stdout)
        missing = [name for name in ("pandas", *EXPECTED_PACKAGES) if name not in manifest["packages"]]
        manifest.update({"status": "ok" if not missing else "environment_error", "captured_at": _now()})
        if missing:
            manifest["error"] = {"type": "MissingDependency", "message": ", ".join(missing), "stage": "manifest"}
        return manifest
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as error:
        return {
            "status": "environment_error", "python": None, "executable": str(python), "packages": {},
            "captured_at": _now(), "error": {"type": type(error).__name__, "message": str(error), "stage": "manifest"},
        }


def _setup_command(command: list[str], root: Path, timeout_s: float = 180) -> dict[str, Any]:
    started = time.monotonic()
    record: dict[str, Any] = {"command": command, "started_at": _now()}
    try:
        process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_group(process)
            stdout, stderr = process.communicate()
            record["timed_out"] = True
        record.update({"exit_code": process.returncode, "stdout": stdout[-LOG_LIMIT:], "stderr": stderr[-LOG_LIMIT:]})
    except OSError as error:
        record.update({"exit_code": None, "stdout": "", "stderr": str(error)})
    record["duration_s"] = round(time.monotonic() - started, 6)
    record["status"] = "ok" if record.get("exit_code") == 0 and not record.get("timed_out") else "environment_error"
    return record


def _kill_group(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def setup_environments(root: Path, *, offline: bool = False) -> dict[str, Any]:
    """Create/sync the pinned pair, saving actual manifests and all setup attempts.

    Fetching is only performed here, never by run_worker. Failed setup is returned
    and persisted as environment_error, rather than a transformation result.
    """
    root = Path(root).resolve()
    state_dir = root / ".featureshift"
    setup_dir = state_dir / "setup"
    setup_dir.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv")
    result: dict[str, Any] = {"status": "ok", "started_at": _now(), "isolation": EXECUTION_PROFILE.copy(), "offline": offline}
    if uv:
        tool_version = _setup_command([uv, "--version"], root, timeout_s=5)
        result["setup_tool"] = tool_version.get("stdout", "").strip()
    result["setup_id"] = uuid.uuid4().hex
    attempts: dict[str, Any] = {}
    result["attempts"] = attempts
    attempt_path = setup_dir / f"attempt-{result['setup_id']}.json"
    _write_json(attempt_path, {**result, "status": "running"})
    for profile, version in (("before", "2.3.3"), ("after", "3.0.0")):
        python = state_dir / "envs" / profile / "bin" / "python"
        requirements = root / "requirements" / f"{profile}.txt"
        record: dict[str, Any] = {"profile": profile, "commands": [], "started_at": _now()}
        try:
            if uv is None:
                raise RuntimeError("uv is unavailable; install the documented pinned uv version")
            if sys.version_info[:2] != (3, 12) or sys.platform != "linux" or platform.machine() != "x86_64":
                raise RuntimeError("The verified wheel lock supports CPython 3.12 on Linux x86_64")
            requirement_hash = hashlib.sha256(requirements.read_bytes()).hexdigest()
            record["requirements_sha256"] = requirement_hash
            expected = {"pandas": version, **EXPECTED_PACKAGES}
            locked: dict[str, str] = {}
            for line in requirements.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                match = re.fullmatch(r"([A-Za-z0-9._-]+)==([^\s]+)(?:\s+--hash=sha256:[a-f0-9]{64})+", line.strip())
                if match is None:
                    raise RuntimeError("Every dependency must have an exact version and SHA256 wheel hash")
                locked[match[1].lower().replace("_", "-")] = match[2]
            if locked != expected:
                raise RuntimeError("Requirements do not match the verified pandas pair and shared dependencies")
            manifest = environment_manifest(python) if python.exists() else {}
            matches = manifest.get("status") == "ok" and manifest.get("packages") == expected
            if not matches:
                if not python.exists():
                    creation = _setup_command([uv, "venv", "--no-project", "--python", sys.executable, "--cache-dir", str(state_dir / "uv-cache"), str(python.parent.parent)], root)
                    record["commands"].append(creation)
                    if creation["status"] != "ok":
                        raise RuntimeError("Environment creation failed; see setup command log")
                installation = _setup_command([
                    uv, "pip", "sync", "--python", str(python), "--cache-dir", str(state_dir / "uv-cache"),
                    "--require-hashes", "--only-binary", ":all:", str(requirements),
                ] + (["--offline"] if offline else []), root)
                record["commands"].append(installation)
                if installation["status"] != "ok":
                    raise RuntimeError("Pinned dependency installation failed; see setup command log")
            manifest = environment_manifest(python)
            if manifest["status"] != "ok" or manifest.get("packages") != expected:
                raise RuntimeError("Resolved packages do not match the complete pinned environment")
            manifest.update({"profile": profile, "requirements_sha256": requirement_hash, "requirements_file": str(requirements)})
            record["status"] = "ok"
        except (OSError, RuntimeError) as error:
            manifest = {
                "status": "environment_error", "profile": profile, "executable": str(python),
                "python": None, "packages": {}, "captured_at": _now(),
                "error": {"type": type(error).__name__, "message": str(error), "stage": "setup"},
            }
            record.update({"status": "environment_error", "error": manifest["error"]})
            result["status"] = "environment_error"
        result[profile] = manifest
        attempts[profile] = record
        _write_json(setup_dir / f"{profile}-manifest.json", manifest)
        _write_json(attempt_path, {**result, "status": "running"})
    result["finished_at"] = _now()
    result["shared_dependencies_constant"] = (
        result["status"] == "ok" and
        {k: v for k, v in result["before"]["packages"].items() if k != "pandas"} ==
        {k: v for k, v in result["after"]["packages"].items() if k != "pandas"}
    )
    _write_json(attempt_path, result)
    _write_json(setup_dir / "environments.json", result)
    return result


def _read_log(path: Path) -> tuple[str, bool]:
    if not path.exists():
        return "", False
    with path.open("rb") as handle:
        data = handle.read(LOG_LIMIT + 1)
    return data[:LOG_LIMIT].decode("utf-8", errors="replace"), len(data) > LOG_LIMIT


def run_worker(
    python: Path, source: Path, fixture: Path, artifact_dir: Path,
    entrypoint: str = "transform", timeout_s: float = 8, test_mode: bool = False,
) -> dict[str, Any]:
    """Execute one trusted transformation; each call needs its own artifact_dir."""
    python, source, fixture = Path(python).absolute(), Path(source).resolve(), Path(fixture).resolve()
    artifact_dir = Path(artifact_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    record: dict[str, Any] = {
        "status": "error", "output": None, "stdout": "", "stderr": "", "exit_code": None,
        "duration_s": 0.0, "versions": {}, "error": None, "started_at": _now(),
        "artifact_dir": str(artifact_dir), "execution_profile": EXECUTION_PROFILE.copy(),
        "entrypoint": "existing_test" if test_mode else entrypoint, "test_mode": test_mode,
    }
    result_file = artifact_dir / "worker-output.json"
    stdout_file, stderr_file = artifact_dir / "stdout.txt", artifact_dir / "stderr.txt"
    try:
        for previous in (result_file, stdout_file, stderr_file):
            previous.unlink(missing_ok=True)
        if not math.isfinite(timeout_s) or timeout_s <= 0 or timeout_s > 60:
            raise ValueError("Worker wall timeout must be greater than zero and at most 60 seconds")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entrypoint):
            raise ValueError("Entry point must be a simple Python identifier")
        if sys.platform != "linux":
            record["status"] = "environment_error"
            raise RuntimeError("This resource-limit profile is supported on Linux only")
        manifest = environment_manifest(python)
        record["environment"] = manifest
        record["versions"] = {"python": manifest.get("python"), **manifest.get("packages", {})}
        if manifest["status"] != "ok":
            record["status"] = "environment_error"
            record["error"] = manifest["error"]
        else:
            if source.stat().st_size > 256 * 1024:
                raise ValueError("Source exceeds the 256 KiB trusted-demo limit")
            if fixture.stat().st_size > 1024 * 1024:
                raise ValueError("Fixture exceeds the 1 MiB trusted-demo limit")
            inputs = artifact_dir / "input"
            inputs.mkdir(exist_ok=True)
            source_copy, fixture_copy = inputs / "transform.py", inputs / "fixture.json"
            for original, copy in ((source, source_copy), (fixture, fixture_copy)):
                if copy.exists():
                    copy.chmod(0o600)
                shutil.copyfile(original, copy)
                copy.chmod(0o400)
            command = [str(python), "-I", "-B", str(WORKER), "--source", str(source_copy), "--fixture", str(fixture_copy), "--output", str(result_file), "--entrypoint", entrypoint, "--timeout", str(timeout_s)]
            if test_mode:
                command.append("--test-mode")
            record["command"] = command
            record["input_hashes"] = {"source": hashlib.sha256(source_copy.read_bytes()).hexdigest(), "fixture": hashlib.sha256(fixture_copy.read_bytes()).hexdigest()}
            with stdout_file.open("wb") as stdout, stderr_file.open("wb") as stderr:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, cwd=artifact_dir, env=_clean_environment(python, artifact_dir), start_new_session=True)
                try:
                    process.wait(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    _kill_group(process)
                    process.wait(timeout=5)
                    record["status"] = "timeout"
                    record["error"] = {"type": "TimeoutExpired", "message": f"Worker exceeded {timeout_s:g} second wall limit; process group killed", "stage": "execution"}
                else:
                    if result_file.exists():
                        record.update(json.loads(result_file.read_text(encoding="utf-8")))
                    elif process.returncode in (-signal.SIGXCPU, -signal.SIGKILL):
                        record["status"] = "timeout"
                        record["error"] = {"type": "ResourceLimit", "message": f"Worker terminated by signal {-process.returncode}", "stage": "execution"}
                    else:
                        record["error"] = {"type": "WorkerExit", "message": f"Worker exited {process.returncode} without structured output", "stage": "execution"}
                finally:
                    # A trusted transformation should not leave child processes behind.
                    _kill_group(process)
                record["exit_code"] = process.returncode
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        record["error"] = {"type": type(error).__name__, "message": str(error), "stage": "runner"}
    record["stdout"], stdout_truncated = _read_log(stdout_file)
    record["stderr"], stderr_truncated = _read_log(stderr_file)
    record["logs_truncated"] = stdout_truncated or stderr_truncated
    record["duration_s"] = round(time.monotonic() - started, 6)
    record["finished_at"] = _now()
    _write_json(artifact_dir / "result.json", record)
    return record


def verify_install_failure(root: Path) -> dict[str, Any]:
    """Actually ask uv to resolve an impossible pin offline, and save its failure."""
    root = Path(root).resolve()
    path = root / ".featureshift" / "setup" / "install-failure-check.json"
    uv = shutil.which("uv")
    python = root / ".featureshift" / "envs" / "before" / "bin" / "python"
    if uv is None or not python.exists():
        result = {"status": "environment_error", "verified": False, "error": "Install uv and run setup before checking installation failure"}
    else:
        before = environment_manifest(python)
        result = _setup_command([
            uv, "pip", "install", "--offline", "--python", str(python),
            "--cache-dir", str(root / ".featureshift" / "uv-cache"), "pandas==999999.0.0",
        ], root, timeout_s=20)
        after = environment_manifest(python)
        result.update({
            "case": "impossible_pinned_dependency", "requested": "pandas==999999.0.0",
            "network_enabled": False, "verified": result.get("exit_code") not in (None, 0),
            "environment_unchanged": before["packages"] == after["packages"],
            "finding_type": "environment_error", "semantic_regression": False,
        })
    _write_json(path, result)
    return result
