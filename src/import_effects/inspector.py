from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .models import EffectKind, ImportReport

_MODULE_RE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")


class InspectionError(RuntimeError):
    """Raised when the isolated inspector cannot produce a valid report."""


def _validate_module(module: str) -> None:
    if not _MODULE_RE.fullmatch(module):
        raise ValueError(f"Invalid module name: {module!r}")


def inspect_import(
    module: str,
    *,
    timeout: float = 10.0,
    python_executable: str | os.PathLike[str] | None = None,
) -> ImportReport:
    """Inspect one import in a fresh child interpreter.

    The target module is never imported into the caller. This is observation, not a
    security sandbox: target code executes with the child's normal OS permissions.
    """

    _validate_module(module)
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    executable = os.fspath(python_executable or sys.executable)
    with tempfile.TemporaryDirectory(prefix="import-effects-") as directory:
        report_path = Path(directory) / "report.json"
        command = [executable, "-m", "import_effects._probe", module, os.fspath(report_path)]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=os.name == "posix",
                creationflags=(
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
                ),
            )
        except OSError as error:
            raise InspectionError(f"Could not start child interpreter: {error}") from error
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            stdout, stderr = process.communicate()
            return ImportReport(
                module=module,
                duration_ms=timeout * 1000,
                success=False,
                timed_out=True,
                exception_type="TimeoutExpired",
                exception_message=f"Import exceeded {timeout:g} seconds.",
                child_stdout=_limit_output(stdout),
                child_stderr=_limit_output(stderr),
                platform=sys.platform,
                python_version=sys.version.split()[0],
            )
        if not report_path.exists():
            raise InspectionError(
                f"Inspector exited with code {process.returncode} without producing a report."
            )
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InspectionError("Inspector produced an unreadable report.") from error
        payload["child_stdout"] = _limit_output(stdout)
        payload["child_stderr"] = _limit_output(stderr)
        return ImportReport.from_dict(payload)


def assert_no_effects(
    module: str,
    *,
    forbidden: Iterable[EffectKind] = ("network", "subprocess", "file-write"),
    timeout: float = 10.0,
) -> ImportReport:
    """Inspect *module* and raise AssertionError for forbidden effects or import failure."""

    report = inspect_import(module, timeout=timeout)
    if not report.success:
        message = report.exception_message or "unknown import failure"
        raise AssertionError(f"Import of {module!r} failed: {message}")
    forbidden_set = set(forbidden)
    found = [effect for effect in report.effects if effect.kind in forbidden_set]
    if found:
        summary = ", ".join(sorted({effect.kind for effect in found}))
        raise AssertionError(f"Import of {module!r} produced forbidden effects: {summary}")
    return report


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:  # pragma: no cover - exercised by Windows CI
            process.kill()
    except ProcessLookupError:
        pass


def _limit_output(value: str, limit: int = 16_384) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n... output truncated by import-effects ..."
