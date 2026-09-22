from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from import_effects import InspectionError, assert_no_effects, inspect_import


def test_clean_import_isolated_from_parent() -> None:
    assert "clean_package" not in sys.modules
    report = inspect_import("clean_package")
    assert report.success
    assert report.module == "clean_package"
    assert report.duration_ms >= 0
    assert "clean_package" in report.imported_modules
    assert "clean_package" not in sys.modules


def test_observes_reliable_import_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMPORT_EFFECTS_FIXTURE_DIR", os.fspath(tmp_path))
    report = inspect_import("effects_package")
    kinds = {effect.kind for effect in report.effects}
    assert report.success
    assert {
        "file-write",
        "file-delete",
        "file-rename",
        "directory",
        "network",
        "subprocess",
        "thread",
        "environment",
        "cwd",
        "logging",
        "sys-path",
        "warnings",
    } <= kinds
    assert all("secret-value-never-reported" not in effect.detail for effect in report.effects)
    assert any(effect.source == "effects_package" for effect in report.effects)


def test_broken_import_is_reported_and_redacted() -> None:
    report = inspect_import("broken_package")
    assert not report.success
    assert report.exception_type == "RuntimeError"
    assert report.exception_message == "broken import with token=<redacted>"


def test_missing_import_is_reported() -> None:
    report = inspect_import("module_that_does_not_exist_anywhere")
    assert not report.success
    assert report.exception_type == "ModuleNotFoundError"


def test_timeout_terminates_child_quickly() -> None:
    report = inspect_import("slow_package", timeout=0.1)
    assert report.timed_out
    assert not report.success
    assert report.exception_type == "TimeoutExpired"


def test_target_output_does_not_corrupt_report() -> None:
    report = inspect_import("output_package")
    assert report.success
    assert report.child_stdout == "hello from target\n"


def test_rejects_invalid_module_and_timeout() -> None:
    with pytest.raises(ValueError, match="Invalid module"):
        inspect_import("not a module; rm -rf x")
    with pytest.raises(ValueError, match="greater than zero"):
        inspect_import("clean_package", timeout=0)


def test_reports_internal_child_failure() -> None:
    with pytest.raises(InspectionError, match="Could not start"):
        inspect_import("clean_package", python_executable=sys.executable + "-missing")


def test_assertion_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMPORT_EFFECTS_FIXTURE_DIR", os.fspath(tmp_path))
    report = assert_no_effects("clean_package")
    assert report.success
    with pytest.raises(AssertionError, match="forbidden effects"):
        assert_no_effects("effects_package", forbidden=("network",))
    with pytest.raises(AssertionError, match="failed"):
        assert_no_effects("broken_package")
