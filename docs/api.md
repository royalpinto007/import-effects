# API reference

## `inspect_import`

```python
inspect_import(module: str, *, timeout: float = 10.0, python_executable: str | PathLike | None = None) -> ImportReport
```

Runs the import in a fresh child interpreter. Invalid module names and timeouts less than or equal to zero raise `ValueError`. Failure to start or decode the child raises `InspectionError`. A target import exception is returned as a normal unsuccessful report.

## `assert_no_effects`

```python
assert_no_effects(module: str, *, forbidden=("network", "subprocess", "file-write"), timeout=10.0) -> ImportReport
```

Raises `AssertionError` when the import fails or a forbidden effect is observed. This helper works naturally in pytest, unittest, and other test runners without a plugin.

## Models

`ImportReport` and `Effect` are frozen dataclasses. `ImportReport.to_dict()` returns JSON-compatible data, `ImportReport.from_dict()` reconstructs a report, and `effects_of(*kinds)` filters effects.

An effect includes `kind`, redacted `detail`, optional `source`, `confidence`, `attribution`, and small non-sensitive metadata. Environment values are never included.

