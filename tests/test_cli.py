from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from import_effects import Effect, ImportReport
from import_effects import cli as cli_module
from import_effects.cli import main
from import_effects.inspector import InspectionError


def test_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["clean_package", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["module"] == "clean_package"
    assert report["success"] is True


def test_fail_on_and_ignore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMPORT_EFFECTS_FIXTURE_DIR", os.fspath(tmp_path))
    assert main(["effects_package", "--fail-on", "network", "--quiet"]) == 1
    assert (
        main(
            [
                "effects_package",
                "--fail-on",
                "file-write",
                "--ignore",
                f"{tmp_path}/**",
                "--ignore",
                os.devnull,
                "--quiet",
            ]
        )
        == 0
    )


def test_import_failure_exit(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["broken_package"]) == 3
    assert "token=<redacted>" in capsys.readouterr().out


def test_quiet_and_verbose_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["clean_package", "--quiet"]) == 0
    assert "SIDE EFFECTS" not in capsys.readouterr().out
    assert main(["clean_package", "--verbose"]) == 0
    assert "IMPORTED MODULES" in capsys.readouterr().out


def test_invalid_cli_inputs() -> None:
    with pytest.raises(SystemExit) as error:
        main(["clean_package", "--timeout", "0"])
    assert error.value.code == 2
    with pytest.raises(SystemExit) as error:
        main(["clean_package", "--fail-on", "made-up"])
    assert error.value.code == 2


def test_module_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "import_effects", "clean_package", "--quiet"],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert result.returncode == 0
    assert "import clean_package" in result.stdout


def test_verbose_effect_and_target_output(capsys: pytest.CaptureFixture[str], monkeypatch) -> None:  # type: ignore[no-untyped-def]
    report = ImportReport(
        module="example",
        duration_ms=12,
        effects=(
            Effect(
                kind="network",
                detail="example.com:443",
                source="example",
                attribution="target",
            ),
        ),
        imported_modules=("example",),
        child_stdout="hello",
        child_stderr="warning",
    )
    monkeypatch.setattr(cli_module, "inspect_import", lambda *_args, **_kwargs: report)
    assert main(["example", "--verbose"]) == 0
    output = capsys.readouterr().out
    assert "SIDE EFFECTS" in output
    assert "target; high confidence" in output
    assert "TARGET STDOUT" in output
    assert "TARGET STDERR" in output


def test_internal_failure_exit(capsys: pytest.CaptureFixture[str], monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fail(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise InspectionError("probe failed")

    monkeypatch.setattr(cli_module, "inspect_import", fail)
    assert main(["example"]) == 4
    assert "internal inspection failure" in capsys.readouterr().err
