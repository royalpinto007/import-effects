from import_effects import Effect, ImportReport


def test_report_round_trip_and_filter() -> None:
    report = ImportReport(
        module="example",
        duration_ms=12.5,
        effects=(Effect(kind="network", detail="example.com:443"),),
        imported_modules=("example",),
    )
    restored = ImportReport.from_dict(report.to_dict())
    assert restored == report
    assert restored.effects_of("network") == restored.effects
    assert restored.effects_of("thread") == ()
