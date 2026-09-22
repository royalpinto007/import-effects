from __future__ import annotations

import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def fixture_import_path(monkeypatch: pytest.MonkeyPatch) -> None:
    current = os.environ.get("PYTHONPATH", "")
    value = os.fspath(FIXTURES) + (os.pathsep + current if current else "")
    monkeypatch.setenv("PYTHONPATH", value)
