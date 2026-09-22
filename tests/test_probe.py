from __future__ import annotations

import logging
import os
import signal
from pathlib import Path

from import_effects import _probe


def test_audit_event_mapping(tmp_path: Path) -> None:
    observer = _probe._Observer("target", tmp_path / "report.json")
    observer.active = True
    observer.audit("open", (tmp_path / "written.txt", "w", 0))
    observer.audit("open", (tmp_path / "flags.txt", None, os.O_CREAT | os.O_WRONLY))
    observer.audit("open", (tmp_path / "read.txt", "r", 0))
    observer.audit("os.remove", (tmp_path / "removed.txt",))
    observer.audit("os.rename", (tmp_path / "before.txt", tmp_path / "after.txt"))
    observer.audit("os.mkdir", (tmp_path / "directory",))
    observer.audit("os.rmdir", (tmp_path / "directory",))
    observer.audit("socket.connect", (object(), ("example.com", 443)))
    observer.audit("socket.bind", (object(), ("127.0.0.1", 8080)))
    observer.audit("socket.getaddrinfo", ("example.com", 443))
    observer.audit("subprocess.Popen", ("git", ["git", "--version"]))
    observer.audit("os.system", ("echo token=private",))
    observer.audit("os.fork", ())
    observer.audit("open", ())
    observer.audit("unrelated.event", ())
    kinds = {effect.kind for effect in observer.effects}
    assert {
        "file-write",
        "file-delete",
        "file-rename",
        "directory",
        "network",
        "subprocess",
        "multiprocessing",
    } <= kinds
    assert all("private" not in effect.detail for effect in observer.effects)
    assert any(effect.detail == "git --version" for effect in observer.effects)


def test_snapshot_comparison_reports_only_names(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    observer = _probe._Observer("target", tmp_path / "report.json")
    observer.active = True
    before = _probe._Snapshot(
        cwd="/before",
        environment={"CHANGED": "old", "REMOVED": "private"},
        sys_path=("before",),
        warning_filters=("before",),
        logging_handlers=(("root", "NullHandler"),),
        signal_handlers={1: "before"},
        modules=frozenset(),
    )
    after = _probe._Snapshot(
        cwd="/after",
        environment={"CHANGED": "new", "ADDED": "private"},
        sys_path=("after",),
        warning_filters=("after",),
        logging_handlers=(("root", "StreamHandler"),),
        signal_handlers={1: "after"},
        modules=frozenset(),
    )
    _probe._compare(observer, before, after)
    details = {effect.detail for effect in observer.effects}
    assert "added ADDED" in details
    assert "removed REMOVED" in details
    assert "changed CHANGED" in details
    assert all("private" not in detail for detail in details)


def test_probe_helpers(tmp_path: Path) -> None:
    assert _probe._address(("host", 123)) == "host:123"
    assert _probe._address("socket") == "socket"
    assert _probe._command("git", ()) == "git"
    assert _probe._command("shell", "echo ok") == "echo ok"
    assert _probe._command("tool", object()) == "tool"
    assert _probe._redact("password:hunter2") == "password:<redacted>"
    assert _probe._is_internal_write("thing.pyc", tmp_path / "report.json")
    assert _probe._is_internal_write(os.fspath(tmp_path / "report.json"), tmp_path / "report.json")
    assert not _probe._is_internal_write("normal.txt", tmp_path / "report.json")
    assert _probe._handler_name(signal.SIG_DFL) == str(signal.SIG_DFL)
    assert _probe._handler_name(logging.info).endswith("info")
    assert _probe._signal_name(signal.SIGINT) == "SIGINT"
    assert _probe._signal_name(99999) == "99999"


def test_probe_main_rejects_wrong_arity() -> None:
    assert _probe.main([]) == 2
