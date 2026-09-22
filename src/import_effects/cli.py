from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace

from . import __version__
from .inspector import InspectionError, inspect_import
from .models import EffectKind, ImportReport

_KINDS: tuple[EffectKind, ...] = (
    "file-write",
    "file-delete",
    "file-rename",
    "directory",
    "network",
    "subprocess",
    "thread",
    "multiprocessing",
    "environment",
    "cwd",
    "logging",
    "sys-path",
    "warnings",
    "signal",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="import-effects",
        description="See what Python does when you import.",
        epilog=(
            "Warning: the target module executes with your normal OS permissions. "
            "This is not a sandbox."
        ),
    )
    parser.add_argument("module", nargs="?", help="already-importable module or package")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    parser.add_argument("--quiet", action="store_true", help="show only the summary or error")
    parser.add_argument(
        "--verbose", action="store_true", help="show attribution and imported modules"
    )
    parser.add_argument("--timeout", type=float, default=10.0, metavar="SECONDS")
    parser.add_argument(
        "--fail-on",
        default="",
        metavar="KINDS",
        help="comma-separated effect kinds that should exit 1",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="GLOB",
        help="ignore matching effect details; may be repeated",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if not arguments.module:
        parser.error("the following arguments are required: module")
    if arguments.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    try:
        fail_on = _parse_fail_on(arguments.fail_on)
    except ValueError as error:
        parser.error(str(error))
    try:
        report = inspect_import(arguments.module, timeout=arguments.timeout)
    except ValueError as error:
        parser.error(str(error))
    except InspectionError as error:
        print(f"import-effects: internal inspection failure: {error}", file=sys.stderr)
        return 4
    report = _apply_ignores(report, arguments.ignore)
    if arguments.json:
        _print_safe(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        _print_safe(_format_text(report, quiet=arguments.quiet, verbose=arguments.verbose))
    if not report.success:
        return 3
    if any(effect.kind in fail_on for effect in report.effects):
        return 1
    return 0


def _parse_fail_on(value: str) -> set[EffectKind]:
    if not value:
        return set()
    result: set[EffectKind] = set()
    for raw in value.split(","):
        kind = raw.strip()
        if kind not in _KINDS:
            choices = ", ".join(_KINDS)
            raise ValueError(f"unknown --fail-on kind {kind!r}; choose from: {choices}")
        result.add(kind)
    return result


def _apply_ignores(report: ImportReport, patterns: Sequence[str]) -> ImportReport:
    expanded = [os.path.expanduser(pattern) for pattern in patterns]
    if not expanded:
        return report
    effects = tuple(
        effect
        for effect in report.effects
        if not any(fnmatch.fnmatch(effect.detail, pattern) for pattern in expanded)
    )
    return replace(report, effects=effects)


def _format_text(report: ImportReport, *, quiet: bool, verbose: bool) -> str:
    lines = [f"import {report.module}", ""]
    if report.timed_out:
        lines.append(f"✗ timed out after {report.duration_ms / 1000:g} s")
    elif report.success:
        lines.append(f"✓ imported in {report.duration_ms:.0f} ms")
    else:
        detail = report.exception_message or "unknown error"
        lines.append(f"✗ {report.exception_type or 'ImportError'}: {detail}")
    if quiet:
        lines.extend(["", _summary(report)])
        return "\n".join(lines)
    if report.effects:
        lines.extend(["", "SIDE EFFECTS"])
        for effect in report.effects:
            lines.extend(["", f"⚠ {effect.kind.upper().replace('-', ' ')}", f"  {effect.detail}"])
            if verbose:
                source = effect.source or "unknown source"
                lines.append(
                    f"  {effect.attribution}; {effect.confidence} confidence; source: {source}"
                )
    if verbose and report.imported_modules:
        lines.extend(["", f"IMPORTED MODULES ({len(report.imported_modules)})"])
        lines.append("  " + ", ".join(report.imported_modules))
    if report.child_stdout:
        lines.extend(["", "TARGET STDOUT", _indent(report.child_stdout.rstrip())])
    if report.child_stderr:
        lines.extend(["", "TARGET STDERR", _indent(report.child_stderr.rstrip())])
    lines.extend(["", _summary(report)])
    return "\n".join(lines)


def _summary(report: ImportReport) -> str:
    count = len(report.effects)
    if count == 0:
        return "No side effects detected"
    counts = Counter(effect.kind for effect in report.effects)
    kinds = " · ".join(f"{amount} {kind}" for kind, amount in sorted(counts.items()))
    noun = "effect" if count == 1 else "effects"
    return f"{count} side {noun} detected · {kinds}"


def _indent(value: str) -> str:
    return "\n".join(f"  {line}" for line in value.splitlines())


def _print_safe(value: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    printable = value.encode(encoding, errors="replace").decode(encoding)
    print(printable)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
