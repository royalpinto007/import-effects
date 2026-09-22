from __future__ import annotations

import importlib
import inspect
import json
import logging
import multiprocessing
import os
import platform
import re
import signal
import sys
import threading
import time
import warnings
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import Attribution, Confidence, Effect, EffectKind, ImportReport

_SECRET_RE = re.compile(
    r"(?i)(token|secret|password|passwd|api[-_]?key|authorization)(=|:)([^\s]+)"
)
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


@dataclass(frozen=True)
class _Snapshot:
    cwd: str
    environment: dict[str, str]
    sys_path: tuple[str, ...]
    warning_filters: tuple[str, ...]
    logging_handlers: tuple[tuple[str, str], ...]
    signal_handlers: dict[int, str]
    modules: frozenset[str]


class _Observer:
    def __init__(self, target: str, report_path: Path) -> None:
        self.target = target
        self.report_path = report_path.resolve()
        self.effects: list[Effect] = []
        self.active = False
        self._keys: set[tuple[str, str]] = set()

    def add(
        self,
        kind: EffectKind,
        detail: str,
        *,
        confidence: Confidence = "high",
        source: str | None = None,
        attribution: Attribution | None = None,
        metadata: Mapping[str, str | int | float | bool | None] | None = None,
    ) -> None:
        if not self.active:
            return
        clean_detail = _redact(detail)
        key = (kind, clean_detail)
        if key in self._keys:
            return
        self._keys.add(key)
        inferred_source, inferred_attribution = self._infer_source()
        self.effects.append(
            Effect(
                kind=kind,
                detail=clean_detail,
                source=source or inferred_source,
                confidence=confidence,
                attribution=attribution or inferred_attribution,
                metadata=metadata or {},
            )
        )

    def _infer_source(self) -> tuple[str | None, Attribution]:
        frame = inspect.currentframe()
        try:
            while frame:
                name = str(frame.f_globals.get("__name__", ""))
                if name == self.target or name.startswith(self.target + "."):
                    return name, "target"
                if name and not name.startswith(("import_effects", "importlib", "threading")):
                    path = frame.f_globals.get("__file__")
                    if path and "site-packages" in os.fspath(path):
                        return name, "dependency"
                frame = frame.f_back
        finally:
            del frame
        return None, "observed-during-import"

    def audit(self, event: str, args: tuple[Any, ...]) -> None:
        if not self.active:
            return
        try:
            if event == "open":
                self._audit_open(args)
            elif event in {"os.remove", "os.unlink"}:
                path = _path(args[0])
                if not _is_runtime_path(path):
                    self.add("file-delete", path)
            elif event in {"os.rename", "os.replace"}:
                source, destination = _path(args[0]), _path(args[1])
                if not (_is_runtime_path(source) or _is_runtime_path(destination)):
                    self.add("file-rename", f"{source} -> {destination}")
            elif event in {"os.mkdir", "os.rmdir"}:
                path = _path(args[0])
                if not _is_runtime_path(path):
                    action = "mkdir" if event == "os.mkdir" else "rmdir"
                    self.add("directory", f"{action} {path}")
            elif event == "socket.connect":
                self.add("network", _address(args[-1]), metadata={"operation": "connect"})
            elif event == "socket.bind":
                self.add("network", f"bind {_address(args[-1])}", metadata={"operation": "bind"})
            elif event == "socket.getaddrinfo":
                host = args[0] if args else "unknown"
                port = args[1] if len(args) > 1 else None
                self.add(
                    "network",
                    _address((host, port)),
                    confidence="medium",
                    metadata={"operation": "dns"},
                )
            elif event == "subprocess.Popen":
                executable = args[0] if args else "unknown"
                arguments = args[1] if len(args) > 1 else ()
                self.add("subprocess", _command(executable, arguments))
            elif event in {"os.system", "os.posix_spawn", "os.posix_spawnp"}:
                self.add("subprocess", _command(args[0] if args else "unknown", ()))
            elif event in {"os.fork", "os.forkpty"}:
                self.add("multiprocessing", "forked child process")
        except Exception:
            # Audit hooks must never break the target import.
            return

    def _audit_open(self, args: tuple[Any, ...]) -> None:
        if not args:
            return
        if isinstance(args[0], int):
            return
        path = _path(args[0])
        if _is_internal_write(path, self.report_path):
            return
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        writes = isinstance(mode, str) and any(character in mode for character in "wax+")
        writes = writes or (isinstance(flags, int) and bool(flags & _WRITE_FLAGS))
        if writes:
            self.add("file-write", path)


def _snapshot() -> _Snapshot:
    return _Snapshot(
        cwd=os.getcwd(),
        environment=dict(os.environ),
        sys_path=tuple(sys.path),
        warning_filters=tuple(repr(item) for item in warnings.filters),
        logging_handlers=tuple(
            sorted(
                (logger_name or "root", type(handler).__name__)
                for logger_name, logger in [
                    ("", logging.getLogger()),
                    *logging.Logger.manager.loggerDict.items(),
                ]
                if isinstance(logger, logging.Logger)
                for handler in logger.handlers
            )
        ),
        signal_handlers={
            number: _handler_name(signal.getsignal(number)) for number in _available_signals()
        },
        modules=frozenset(sys.modules),
    )


def _compare(observer: _Observer, before: _Snapshot, after: _Snapshot) -> None:
    if before.cwd != after.cwd:
        observer.add("cwd", f"{before.cwd} -> {after.cwd}", confidence="high")
    before_keys, after_keys = set(before.environment), set(after.environment)
    for key in sorted(after_keys - before_keys):
        observer.add("environment", f"added {key}", confidence="high")
    for key in sorted(before_keys - after_keys):
        observer.add("environment", f"removed {key}", confidence="high")
    for key in sorted(before_keys & after_keys):
        if before.environment[key] != after.environment[key]:
            observer.add("environment", f"changed {key}", confidence="high")
    if before.sys_path != after.sys_path:
        observer.add("sys-path", "sys.path changed", confidence="medium")
    if before.warning_filters != after.warning_filters:
        observer.add("warnings", "warnings filters changed", confidence="medium")
    added_handlers = list(after.logging_handlers)
    for original_handler in before.logging_handlers:
        if original_handler in added_handlers:
            added_handlers.remove(original_handler)
    for logger_name, handler_name in added_handlers:
        observer.add("logging", f"added {handler_name} handler to {logger_name}")
    for number, signal_handler in after.signal_handlers.items():
        if before.signal_handlers.get(number) != signal_handler:
            observer.add("signal", f"{_signal_name(number)} handler changed", confidence="medium")


def run_probe(module: str, report_path: Path) -> int:
    observer = _Observer(module, report_path)
    sys.addaudithook(observer.audit)
    original_thread_start = threading.Thread.start
    original_process_start = multiprocessing.process.BaseProcess.start

    def thread_start(thread: threading.Thread, *args: Any, **kwargs: Any) -> Any:
        observer.add("thread", thread.name or type(thread).__name__)
        return original_thread_start(thread, *args, **kwargs)

    def process_start(
        process: multiprocessing.process.BaseProcess, *args: Any, **kwargs: Any
    ) -> Any:
        observer.add("multiprocessing", process.name or type(process).__name__)
        return original_process_start(process, *args, **kwargs)

    threading.Thread.start = thread_start  # type: ignore[assignment]
    multiprocessing.process.BaseProcess.start = process_start  # type: ignore[assignment]
    before = _snapshot()
    observer.active = True
    started = time.perf_counter()
    success = True
    exception_type: str | None = None
    exception_message: str | None = None
    try:
        importlib.import_module(module)
    except BaseException as error:
        success = False
        exception_type = type(error).__name__
        exception_message = _redact(str(error))[:1000]
    duration_ms = (time.perf_counter() - started) * 1000
    after = _snapshot()
    _compare(observer, before, after)
    observer.active = False
    threading.Thread.start = original_thread_start  # type: ignore[method-assign]
    multiprocessing.process.BaseProcess.start = original_process_start  # type: ignore[method-assign]
    imported_modules = tuple(sorted(after.modules - before.modules))
    report = ImportReport(
        module=module,
        duration_ms=duration_ms,
        effects=tuple(observer.effects),
        imported_modules=imported_modules,
        success=success,
        exception_type=exception_type,
        exception_message=exception_message,
        platform=platform.platform(),
        python_version=platform.python_version(),
    )
    report_path.write_text(json.dumps(asdict(report), sort_keys=True), encoding="utf-8")
    return 0


def _path(value: Any) -> str:
    try:
        return os.path.abspath(os.fsdecode(value))
    except (TypeError, ValueError):
        return "<unprintable path>"


def _address(value: Any) -> str:
    if isinstance(value, tuple) and len(value) >= 2:
        return f"{value[0]}:{value[1]}"
    return str(value)


def _command(executable: Any, arguments: Any) -> str:
    if isinstance(arguments, (list, tuple)):
        rendered = " ".join(str(item) for item in arguments[:12])
        return rendered or str(executable)
    if isinstance(arguments, (str, bytes)):
        return os.fsdecode(arguments)
    return str(executable)


def _redact(value: str) -> str:
    return _SECRET_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", value)


def _is_internal_write(path: str, report_path: Path) -> bool:
    return Path(path) == report_path or _is_runtime_path(path)


def _is_runtime_path(path: str) -> bool:
    return path.endswith((".pyc", ".pyo")) or "__pycache__" in path


def _available_signals() -> list[int]:
    values: list[int] = []
    for member in signal.Signals:
        try:
            signal.getsignal(member.value)
        except (OSError, RuntimeError, ValueError):
            continue
        values.append(member.value)
    return values


def _handler_name(handler: Any) -> str:
    if handler in {signal.SIG_DFL, signal.SIG_IGN, None}:
        return str(handler)
    return getattr(handler, "__qualname__", type(handler).__name__)


def _signal_name(number: int) -> str:
    try:
        return signal.Signals(number).name
    except ValueError:
        return str(number)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 2:
        return 2
    return run_probe(arguments[0], Path(arguments[1]))


if __name__ == "__main__":
    raise SystemExit(main())
