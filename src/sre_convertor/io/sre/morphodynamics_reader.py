from __future__ import annotations

from pathlib import Path
import statistics

from ...models import MorphodynamicsSummary
from .records import load_records


def read_morphodynamics_summary(input_dir: Path) -> tuple[MorphodynamicsSummary, list[str]]:
    warnings: list[str] = []

    mpin_records = load_records(input_dir, "DEFICN", {"MPIN"})
    sbst_records = load_records(input_dir, "DEFSUB", {"SBST"})

    branch_ids = {
        record.attrs.get("ci", "")
        for record in mpin_records
        if record.attrs.get("ci") and record.attrs.get("ci") != "-1"
    }
    has_morphology_switch = any(record.attrs.get("md") == "1" for record in sbst_records)
    representative_d50_m = _extract_representative_d50(mpin_records)

    if branch_ids and not has_morphology_switch:
        warnings.append("MPIN grain-size initialization found, but DEFSUB does not indicate active morphology switch.")

    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=len(branch_ids),
        has_morphology_switch=has_morphology_switch,
        representative_d50_m=representative_d50_m,
    )
    return summary, warnings


def _extract_representative_d50(mpin_records: list) -> float | None:
    d50_values: list[float] = []
    for record in mpin_records:
        raw = record.attrs.get("c5")
        if raw is None:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value <= 0.0 or value >= 1.0e8:
            continue
        d50_values.append(value)

    if not d50_values:
        return None
    return statistics.median(d50_values)
