from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EffectKind = Literal[
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
]
Confidence = Literal["high", "medium", "low"]
Attribution = Literal["target", "dependency", "observed-during-import", "runtime"]


@dataclass(frozen=True, slots=True)
class Effect:
    kind: EffectKind
    detail: str
    source: str | None = None
    confidence: Confidence = "high"
    attribution: Attribution = "observed-during-import"
    metadata: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Effect:
        return cls(
            kind=value["kind"],
            detail=str(value["detail"]),
            source=value.get("source"),
            confidence=value.get("confidence", "high"),
            attribution=value.get("attribution", "observed-during-import"),
            metadata=value.get("metadata", {}),
        )


@dataclass(frozen=True, slots=True)
class ImportReport:
    module: str
    duration_ms: float
    effects: tuple[Effect, ...] = ()
    imported_modules: tuple[str, ...] = ()
    success: bool = True
    exception_type: str | None = None
    exception_message: str | None = None
    timed_out: bool = False
    child_stdout: str = ""
    child_stderr: str = ""
    platform: str = ""
    python_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ImportReport:
        return cls(
            module=str(value["module"]),
            duration_ms=float(value.get("duration_ms", 0)),
            effects=tuple(Effect.from_dict(item) for item in value.get("effects", [])),
            imported_modules=tuple(value.get("imported_modules", [])),
            success=bool(value.get("success", False)),
            exception_type=value.get("exception_type"),
            exception_message=value.get("exception_message"),
            timed_out=bool(value.get("timed_out", False)),
            child_stdout=str(value.get("child_stdout", "")),
            child_stderr=str(value.get("child_stderr", "")),
            platform=str(value.get("platform", "")),
            python_version=str(value.get("python_version", "")),
        )

    def effects_of(self, *kinds: EffectKind) -> tuple[Effect, ...]:
        wanted = set(kinds)
        return tuple(effect for effect in self.effects if effect.kind in wanted)
