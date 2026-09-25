from __future__ import annotations

from pathlib import Path

from ...models import InputReadDiagnostic


_RECORD_KEYS = {
    "NODE", "BRCH", "GRID", "CRSN", "CRDS", "FLBO", "FLBR", "FLBX", "FLDI", "FLNO", "FLNX",
    "FLTM", "BDFR", "FLIN", "MPIN", "SBST", "TRNS", "STRU", "STCM", "STDS", "DEFS", "TRIG",
}


def collect_input_diagnostics(input_dir: Path) -> tuple[InputReadDiagnostic, ...]:
    diagnostics: list[InputReadDiagnostic] = []
    for path in sorted(item for item in input_dir.rglob("*") if item.is_file()):
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        records: list[tuple[str, int, int]] = []
        current_key: str | None = None
        current_start = 0

        for line_number, line in enumerate(lines, start=1):
            token = line.strip().split(maxsplit=1)
            key = token[0].upper() if token else ""
            if key not in _RECORD_KEYS:
                continue
            if current_key is not None:
                records.append((current_key, current_start, line_number - 1))
            current_key = key
            current_start = line_number

        if current_key is not None:
            records.append((current_key, current_start, len(lines)))

        diagnostics.append(
            InputReadDiagnostic(
                source_file=path.relative_to(input_dir),
                line_count=len(lines),
                records=tuple(records),
            )
        )

    return tuple(diagnostics)