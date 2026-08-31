from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ...models import RuntimeSettings
from .records import load_records


def read_runtime_settings(input_dir: Path, test_duration_seconds: int | None = None) -> tuple[RuntimeSettings, list[str]]:
    warnings: list[str] = []
    records = load_records(input_dir, "DEFRUN", {"FLTM"})

    if not records:
        warnings.append("No FLTM runtime record found in DEFRUN.*. Using one-day default period.")
        refdate = datetime(2000, 1, 1)
        return RuntimeSettings(refdate=refdate, tstart_seconds=0, tstop_seconds=86400), warnings

    attrs = records[0].attrs
    bt = _parse_time(attrs.get("bt"))
    et = _parse_time(attrs.get("et"))

    if bt is None or et is None:
        warnings.append("Could not parse FLTM bt/et values. Using one-day default period.")
        refdate = datetime(2000, 1, 1)
        return RuntimeSettings(refdate=refdate, tstart_seconds=0, tstop_seconds=86400), warnings

    duration_seconds = int((et - bt).total_seconds())
    if duration_seconds <= 0:
        warnings.append("Non-positive runtime duration parsed from FLTM; using one-day default period.")
        duration_seconds = 86400

    if test_duration_seconds is not None and test_duration_seconds > 0 and duration_seconds > test_duration_seconds:
        warnings.append(
            f"Runtime truncated from {duration_seconds}s to {test_duration_seconds}s for test execution."
        )
        duration_seconds = test_duration_seconds

    runtime = RuntimeSettings(refdate=bt.replace(hour=0, minute=0, second=0), tstart_seconds=0, tstop_seconds=duration_seconds)
    return runtime, warnings


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y/%m/%d;%H:%M:%S")
    except ValueError:
        return None
